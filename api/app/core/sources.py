"""Watched sources: re-reading a regulator's own page, on a schedule.

Until now nothing entered the graph unless a person uploaded it. That makes the
honest description of the product "a compliance checker", not "a regulatory
monitor" — the app could only ever know what somebody had already noticed and
gone to fetch. A watched source closes that gap: an address is registered once,
re-read on a schedule, and when the *wording* changes the new version goes in
through the ordinary ingestion path.

Three rules hold this together.

**No back door.** A change is ingested by calling `documents.create_document`,
exactly as an upload does — same hash, same Pub/Sub message, same extraction,
same guardrail, same reconciliation. There is no path here that writes a clause.
A scheduled read of a news site is a `news_article` with authority tier 0.35 and
lands in the review queue; it does not silently move a limit.

**A check that finds nothing costs nothing.** Conditional GET when the server
supports it, a text-hash comparison when it does not, and `create_document`'s
own content hash behind both. The expensive thing is the model, and none of
these paths reach it.

**A source that breaks says so.** A 403, a login wall, a PDF with no text layer:
each is recorded on the source and rendered in the UI. Silence would be a lie —
the whole point of this feature is that "we found nothing" means something.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from google.cloud import firestore

from app.core import fetching
from app.core.fetching import FetchError
from app.core.repository import new_id, write_with_event
from app.db import get_db
from app.models import (
    WORKSPACE_ID,
    DocumentIn,
    EventType,
    SourceCheckStatus,
    SourceKind,
    SourceType,
    WatchedSource,
    WatchedSourceIn,
    WatchedSourcePatch,
)
from app.observability import get_trace_id, log
from app.settings import get_settings

logger = logging.getLogger(__name__)

COLLECTION = "watched_sources"


# The addresses the app watches out of the box. Both were fetched and checked
# from the deployed service before being written down here: reachable without a
# session, stable in their *text* across repeat reads, and small enough to read
# in one piece.
#
# The EU regulation is watched through CELLAR, the Publications Office's own
# machine-readable endpoint, and not through the EUR-Lex web page. That is not a
# preference. EUR-Lex answers a datacentre address with `202 Accepted` and a
# two-kilobyte challenge page, so the exact URL that works from a laptop returns
# nothing at all from Cloud Run — verified, in production, after it failed there
# once. CELLAR serves the same text (48,417 characters, the same document), and
# it sends an `ETag`, so the daily check is a conditional GET that transfers
# nothing when nothing has changed.
#
# Deliberately not seeded: Regulation 1129/2011 itself. It is ~800,000
# characters — four times `MAX_FETCH_CHARS`. The app already carries verbatim
# excerpts of it, and watching the whole thing would spend a model pass on the
# entire annex to notice a typo fix. A user who wants it can add it and see the
# size refusal for themselves.
SEED_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "url": "https://publications.europa.eu/resource/celex/32023R2108",
        "label": "EU 2023/2108 — amendment to the food additives annex",
        "kind": SourceKind.DOCUMENT,
        "source_type": SourceType.OFFICIAL_REGULATION,
        "jurisdiction": "EU",
    },
    {
        "url": "https://food.ec.europa.eu/node/2/rss_en",
        "label": "European Commission — food safety news",
        "kind": SourceKind.FEED,
        # A news item is not a regulation and is not treated as one: tier 0.35
        # means anything read here needs a human before it counts.
        "source_type": SourceType.NEWS_ARTICLE,
        "jurisdiction": "EU",
    },
    {
        # EU discovery. The counterpart to the BPOM listing below, and the
        # reason it is a query rather than an index page: EUR-Lex's own web
        # pages answer a datacentre address with a challenge page, while the
        # Publications Office's catalogue answers anyone. Asking it is also
        # better than scraping would have been — the filter is the EU's own
        # classification of its own acts, not a regex over a layout.
        #
        # `?celex` is what makes each row fetchable: the identifier expands to
        # `publications.europa.eu/resource/celex/<id>`, the same address shape
        # already proven to serve the regulation text from Cloud Run.
        #
        # The CELEX pattern is the type filter. `3` is the legislation sector
        # and `R` is a regulation, so `^3\d{4}R\d{4}$` keeps acts and drops
        # merger notices (`52026M...`), proposals (`52026PC...`) and the
        # corrigendum notices that carry an `R(01)` suffix. Measured against the
        # live endpoint: 133 works a year carry the food-additive concept, of
        # which this leaves roughly a dozen — a real regulation every few weeks,
        # which is the rate a daily check is built for.
        "url": "https://publications.europa.eu/webapi/rdf/sparql",
        "label": "EU catalogue — new food-additive regulations",
        "kind": SourceKind.SPARQL,
        "sparql_query": (
            "PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>\n"
            "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
            "SELECT DISTINCT ?celex ?date WHERE {\n"
            "  ?work cdm:work_is_about_concept_eurovoc"
            " <http://eurovoc.europa.eu/6052> ;\n"
            "        cdm:work_date_document ?date ;\n"
            "        cdm:resource_legal_id_celex ?celex .\n"
            '  FILTER(?date > "{since}"^^xsd:date)\n'
            '  FILTER(REGEX(STR(?celex), "^3[0-9]{4}R[0-9]{4}$"))\n'
            "} ORDER BY DESC(?date) LIMIT 40"
        ),
        "source_type": SourceType.OFFICIAL_REGULATION,
        "jurisdiction": "EU",
    },
    {
        # Discovery, not change-watching. A watched document can only ever tell
        # you that a rule you already know about was edited; a regulation
        # published *tomorrow* arrives at an address nobody has seen yet, and
        # the regulator's own index is where it appears first. JDIH is BPOM's
        # legal-documentation portal and its download links carry the
        # regulation number, the year and the full title in the path.
        "url": "https://jdih.pom.go.id/",
        "label": "BPOM JDIH — newly published regulations",
        "kind": SourceKind.LISTING,
        "link_pattern": r"/download/rule/\d+/",
        "source_type": SourceType.OFFICIAL_REGULATION,
        "jurisdiction": "ID_BPOM",
    },
)


# ---------------------------------------------------------------------------
# Reading and writing the registry
# ---------------------------------------------------------------------------


def _to_source(doc_id: str, data: dict[str, Any]) -> WatchedSource:
    return WatchedSource.model_validate({**data, "id": doc_id})


def get_source(source_id: str) -> WatchedSource | None:
    snapshot = get_db().collection(COLLECTION).document(source_id).get()
    if not snapshot.exists:
        return None
    return _to_source(snapshot.id, snapshot.to_dict() or {})


def list_sources() -> list[WatchedSource]:
    snapshots = (
        get_db()
        .collection(COLLECTION)
        .where(filter=firestore.FieldFilter("workspace_id", "==", WORKSPACE_ID))
        .limit(200)
        .stream()
    )
    sources = [_to_source(s.id, s.to_dict() or {}) for s in snapshots]
    sources.sort(key=lambda s: (not s.enabled, s.label.lower()))
    return sources


def find_by_url(url: str) -> WatchedSource | None:
    snapshots = (
        get_db()
        .collection(COLLECTION)
        .where(filter=firestore.FieldFilter("workspace_id", "==", WORKSPACE_ID))
        .where(filter=firestore.FieldFilter("url", "==", url))
        .limit(1)
        .stream()
    )
    for snapshot in snapshots:
        return _to_source(snapshot.id, snapshot.to_dict() or {})
    return None


def add_source(meta: WatchedSourceIn) -> tuple[WatchedSource, bool]:
    """Register an address. Returns `(source, created)`; an address already
    watched is returned as it stands rather than duplicated — two rows for one
    URL would double every check and every ingestion."""
    existing = find_by_url(meta.url)
    if existing is not None:
        return existing, False

    source_id = new_id("src")
    record = meta.model_dump(mode="json") | {
        "workspace_id": WORKSPACE_ID,
        "last_status": str(SourceCheckStatus.NEVER_CHECKED),
        "last_error": None,
        "last_checked_at": None,
        "last_changed_at": None,
        "last_etag": None,
        "last_modified": None,
        "last_text_sha": None,
        "seen_entry_ids": [],
        "document_ids": [],
        "checks": 0,
        "changes": 0,
        "check_lock_at": None,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    write_with_event(
        COLLECTION,
        source_id,
        record,
        event_type=EventType.SOURCE_ADDED,
        entity_type="watched_source",
        after=meta.model_dump(mode="json"),
    )
    created = get_source(source_id)
    assert created is not None  # just written
    log(logger, logging.INFO, "source added", source_id=source_id, url=meta.url)
    return created, True


def patch_source(source_id: str, patch: WatchedSourcePatch) -> WatchedSource | None:
    existing = get_source(source_id)
    if existing is None:
        return None
    changes = {k: v for k, v in patch.model_dump(mode="json").items() if v is not None}
    if not changes:
        return existing
    write_with_event(
        COLLECTION,
        source_id,
        changes | {"updated_at": firestore.SERVER_TIMESTAMP},
        event_type=EventType.SOURCE_UPDATED,
        entity_type="watched_source",
        before=existing.model_dump(mode="json"),
        after=changes,
        merge=True,
    )
    return get_source(source_id)


def delete_source(source_id: str) -> bool:
    """Stop watching an address.

    Documents already ingested from it are left alone on purpose. They are real
    regulations that real verdicts cite; deleting them because nobody wants the
    reminder any more would silently change what every product is checked
    against. Removing a document is its own, separate decision.
    """
    from app.core.repository import delete_with_event

    existing = get_source(source_id)
    if existing is None:
        return False
    delete_with_event(
        COLLECTION,
        source_id,
        event_type=EventType.SOURCE_REMOVED,
        entity_type="watched_source",
        before=existing.model_dump(mode="json"),
    )
    log(logger, logging.INFO, "source removed", source_id=source_id, url=existing.url)
    return True


def seed_sources() -> list[dict[str, Any]]:
    """Register the built-in watch list. Idempotent — an address already
    watched is left exactly as it is, keeping its history."""
    results = []
    for spec in SEED_SOURCES:
        source, created = add_source(WatchedSourceIn(**spec))
        results.append({"id": source.id, "url": source.url, "created": created})
    return results


# ---------------------------------------------------------------------------
# Scheduling arithmetic — pure, so it is testable without a clock or a database
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    """Firestore hands back timezone-aware datetimes; a locally-built one may
    not be. Comparing the two raises, which would break a check on the one path
    nobody exercises locally."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def is_due(source: WatchedSource, now: datetime | None = None) -> bool:
    """Has enough time passed to read this address again?"""
    if not source.enabled:
        return False
    last = _aware(source.last_checked_at)
    if last is None:
        return True
    now = now or _now()
    return now - last >= timedelta(hours=source.check_interval_hours)


def is_locked(source: WatchedSource, now: datetime | None = None) -> bool:
    """Is another check already running? A lock older than the configured
    lifetime belongs to a process that died, and is ignored rather than
    stranding the source forever."""
    locked_at = _aware(source.check_lock_at)
    if locked_at is None:
        return False
    now = now or _now()
    return (now - locked_at).total_seconds() < get_settings().source_check_lock_seconds


def _cap_seen(seen: list[str]) -> list[str]:
    cap = get_settings().source_seen_entry_cap
    return seen[-cap:] if len(seen) > cap else seen


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------


def _claim(source_id: str) -> bool:
    """Take the check lock for one source, atomically.

    Cloud Scheduler retries, and a user pressing "Check now" while the nightly
    sweep is running is not exotic. Two checks of one address at the same time
    would both see "no stored hash" and both ingest, so the claim is a
    transaction rather than a read followed by a write.
    """
    db = get_db()
    reference = db.collection(COLLECTION).document(source_id)

    @firestore.transactional
    def claim(transaction: firestore.Transaction) -> bool:
        snapshot = reference.get(transaction=transaction)
        if not snapshot.exists:
            return False
        source = _to_source(snapshot.id, snapshot.to_dict() or {})
        if is_locked(source):
            return False
        transaction.update(reference, {"check_lock_at": firestore.SERVER_TIMESTAMP})
        return True

    return claim(db.transaction())


def _release_payload(updates: dict[str, Any]) -> dict[str, Any]:
    """Whatever a check concluded, plus the two fields every release must write.

    Split out from `_release` so the "the lock is always cleared" property is
    checkable without a Firestore client — it is the property that decides
    whether a crashed check strands a source until someone notices."""
    return updates | {"check_lock_at": None, "updated_at": firestore.SERVER_TIMESTAMP}


def _release(source_id: str, updates: dict[str, Any]) -> None:
    get_db().collection(COLLECTION).document(source_id).set(
        _release_payload(updates), merge=True
    )


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


def _guard_size(text: fetching.SourceText, url: str) -> None:
    """Refuse what we cannot read honestly, before it costs a model call."""
    settings = get_settings()
    if text.char_count < settings.min_fetch_chars:
        # Deliberately NOT permanent. An empty page is as often a temporary
        # interstitial as a real one — EUR-Lex serves exactly this to a
        # datacentre address — and giving up on a regulation because it was
        # behind a challenge page one night is the worse mistake.
        raise FetchError(
            "That address returned almost no text. It is probably a login page, a "
            "listing, or a scan with no text layer in it."
        )
    # Size, by contrast, is a property of the document. It will be the same
    # tomorrow, so retrying nightly buys nothing and costs a slot in the cap.
    if text.char_count > settings.max_fetch_chars:
        raise FetchError(
            f"That document is {text.char_count:,} characters and we read up to "
            f"{settings.max_fetch_chars:,} in one piece. Point at the specific annex.",
            permanent=True,
        )
    if text.page_count and text.page_count > settings.max_document_pages:
        raise FetchError(
            f"That PDF has {text.page_count} pages and we read up to "
            f"{settings.max_document_pages}. Point at the specific annex.",
            permanent=True,
        )
    log(logger, logging.DEBUG, "source size accepted", url=url, chars=text.char_count)


def _ingest(
    source: WatchedSource,
    text: fetching.SourceText,
    *,
    fetched_url: str,
    title: str | None = None,
) -> dict[str, Any]:
    """Hand fetched wording to the ordinary ingestion path.

    The source's declared jurisdiction and source type win over whatever the
    document says about itself. That is not a shortcut: the source type caps
    what a clause is allowed to do downstream, and a person registering an
    address has said where it comes from. Detection still runs, so the title and
    the effective date are read from the document, and the reading is kept on
    the record either way.
    """
    from app.core import detection
    from app.core.documents import create_document

    found = detection.detect(text.text[:20_000], fetched_url)
    source_name = title or found.source_name.value or source.label

    document, cached = create_document(
        meta=DocumentIn(
            source_type=source.source_type,
            source_name=source_name[:200],
            jurisdiction=source.jurisdiction,
            declared_effective_date=found.effective_date.value,
            filename=fetched_url[-200:],
        ),
        text=text.text,
        page_count=text.page_count,
        text_preview=text.text[:500],
        char_count=text.char_count,
        trace_id=get_trace_id(),
        detection=found.to_dict(),
        # The address is the declaration. Recording it here is what lets the
        # document page say "read from eur-lex.europa.eu on 29 Aug", instead of
        # showing a pasted-text row that invites the reader to wonder who
        # pasted it.
        declared_fields=["source_type", "jurisdiction"],
        origin="watched_source",
    )
    return {
        "document_id": document.id,
        "cached": cached,
        "source_name": source_name,
        "url": fetched_url,
        "chars": text.char_count,
    }


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------


def _check_document(source: WatchedSource) -> tuple[dict[str, Any], dict[str, Any]]:
    """Re-read one regulation. Returns `(result, updates)`."""
    fetched = fetching.fetch(
        source.url, etag=source.last_etag, last_modified=source.last_modified
    )
    if fetched.not_modified:
        fetching.log_read(fetched, None, source_id=source.id)
        return (
            {"status": str(SourceCheckStatus.UNCHANGED), "reason": "not_modified"},
            {
                "last_status": str(SourceCheckStatus.UNCHANGED),
                "last_error": None,
                "last_etag": fetched.etag,
                "last_modified": fetched.last_modified,
            },
        )

    text = fetching.to_text(fetched.raw, fetched.content_type)
    fetching.log_read(fetched, text, source_id=source.id)

    if source.last_text_sha and text.sha256 == source.last_text_sha:
        return (
            {"status": str(SourceCheckStatus.UNCHANGED), "reason": "same_text"},
            {
                "last_status": str(SourceCheckStatus.UNCHANGED),
                "last_error": None,
                "last_etag": fetched.etag,
                "last_modified": fetched.last_modified,
            },
        )

    _guard_size(text, source.url)
    ingested = _ingest(source, text, fetched_url=fetched.url)
    log(
        logger,
        logging.INFO,
        "watched source changed",
        source_id=source.id,
        url=source.url,
        first_read=source.last_text_sha is None,
        document_id=ingested["document_id"],
        cached=ingested["cached"],
        chars=ingested["chars"],
    )
    return (
        {
            "status": str(SourceCheckStatus.CHANGED),
            "first_read": source.last_text_sha is None,
            "ingested": [ingested],
        },
        {
            "last_status": str(SourceCheckStatus.CHANGED),
            "last_error": None,
            "last_etag": fetched.etag,
            "last_modified": fetched.last_modified,
            "last_text_sha": text.sha256,
            "last_changed_at": firestore.SERVER_TIMESTAMP,
            "changes": source.changes + 1,
            "document_ids": [ingested["document_id"], *source.document_ids][:50],
        },
    )


def _check_items(
    source: WatchedSource,
    fetched: fetching.Fetched,
    items: list[fetching.FeedEntry],
    *,
    collection_title: str,
    label: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Decide what to do with a list of things published over time.

    Shared by feeds and listings because the decision is identical: what is new,
    how much of it to read now, and which of the failures deserve another go.
    Only how the list was obtained differs — parsing XML, or reading the links
    off an index page.
    """
    settings = get_settings()
    seen = set(source.seen_entry_ids)
    new_items = [item for item in items if item.key not in seen]
    base_updates = {
        "last_error": None,
        "last_etag": fetched.etag,
        "last_modified": fetched.last_modified,
    }

    # First look: remember what is already there and read none of it. Adopting
    # a feed or an index is a request to be told what happens next, not to be
    # handed the archive — and the archive would be twenty extraction runs.
    if source.last_status == SourceCheckStatus.NEVER_CHECKED:
        keys = _cap_seen([item.key for item in items])
        log(
            logger, logging.INFO, f"{label} baselined",
            source_id=source.id, entries=len(keys), collection_title=collection_title,
        )
        return (
            {
                "status": str(SourceCheckStatus.BASELINED),
                "entries_seen": len(keys),
                "feed_title": collection_title,
            },
            base_updates | {"last_status": str(SourceCheckStatus.BASELINED), "seen_entry_ids": keys},
        )

    if not new_items:
        return (
            {"status": str(SourceCheckStatus.UNCHANGED), "reason": "no_new_entries"},
            base_updates | {"last_status": str(SourceCheckStatus.UNCHANGED)},
        )

    # Newest first; take the newest few and stop. The rest are deliberately left
    # unseen so they come back on the next run rather than turning one overnight
    # burst into an unbounded bill.
    take = new_items[: settings.source_max_new_per_check]
    ingested: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    # An item is marked seen when it was read — or when reading it can never
    # work. A timeout stays new so the next run retries it; a 308-page annex
    # does not, because retrying it nightly forever would burn the per-run cap
    # a readable new regulation needed.
    read_keys: list[str] = []
    for item in take:
        try:
            item_fetch = fetching.fetch(item.link)
            item_text = fetching.to_text(item_fetch.raw, item_fetch.content_type)
            _guard_size(item_text, item.link)
            ingested.append(
                _ingest(
                    source,
                    item_text,
                    fetched_url=item_fetch.url,
                    # A CELEX id names the act but is not its name. Where the
                    # item's "title" is really an identifier, the document is
                    # allowed to state its own title instead.
                    title=None if item.prefer_detected_title else item.title,
                )
            )
            read_keys.append(item.key)
        except FetchError as exc:
            failures.append(
                {
                    "title": item.title,
                    "link": item.link,
                    "error": str(exc),
                    "permanent": exc.permanent,
                }
            )
            if exc.permanent:
                read_keys.append(item.key)
            log(
                logger, logging.WARNING, f"{label} entry unreadable",
                source_id=source.id, link=item.link,
                permanent=exc.permanent, error=str(exc)[:200],
            )

    seen_after = _cap_seen([*source.seen_entry_ids, *read_keys])
    status = SourceCheckStatus.CHANGED if ingested else SourceCheckStatus.UNCHANGED
    log(
        logger, logging.INFO, f"{label} checked",
        source_id=source.id, new_entries=len(new_items),
        ingested=len(ingested), failed=len(failures),
    )
    updates = base_updates | {
        "last_status": str(status),
        "seen_entry_ids": seen_after,
    }
    if ingested:
        updates |= {
            "last_changed_at": firestore.SERVER_TIMESTAMP,
            "changes": source.changes + 1,
            "document_ids": ([i["document_id"] for i in ingested] + source.document_ids)[:50],
        }
    if failures and not ingested:
        updates["last_error"] = failures[0]["error"][:500]
    return (
        {
            "status": str(status),
            "new_entries": len(new_items),
            "ingested": ingested,
            "failed": failures,
            "feed_title": collection_title,
        },
        updates,
    )


def _not_modified(source: WatchedSource, fetched: fetching.Fetched) -> tuple[dict, dict]:
    fetching.log_read(fetched, None, source_id=source.id)
    return (
        {"status": str(SourceCheckStatus.UNCHANGED), "reason": "not_modified"},
        {
            "last_status": str(SourceCheckStatus.UNCHANGED),
            "last_error": None,
            "last_etag": fetched.etag,
            "last_modified": fetched.last_modified,
        },
    )


def _check_feed(source: WatchedSource) -> tuple[dict[str, Any], dict[str, Any]]:
    """Re-read a feed. A change here means a new entry, not a rewritten page."""
    fetched = fetching.fetch(
        source.url,
        etag=source.last_etag,
        last_modified=source.last_modified,
        accept=fetching.ACCEPT_FEED,
    )
    if fetched.not_modified:
        return _not_modified(source, fetched)
    feed = fetching.parse_feed(fetched.raw)
    return _check_items(
        source, fetched, feed.entries, collection_title=feed.title, label="feed"
    )


def _check_listing(source: WatchedSource) -> tuple[dict[str, Any], dict[str, Any]]:
    """Re-read an index page. A new link on it is a regulation we did not have.

    This is the case a watched document cannot cover: a regulator publishing a
    *new* act puts it at a new address, and something already being watched has
    no reason to mention it. The index is where it shows up first.
    """
    fetched = fetching.fetch(
        source.url, etag=source.last_etag, last_modified=source.last_modified
    )
    if fetched.not_modified:
        return _not_modified(source, fetched)

    markup = fetched.raw.decode("utf-8", errors="replace")
    links = fetching.extract_links(markup, fetched.url, source.link_pattern or "")
    fetching.log_read(
        fetched,
        None,
        source_id=source.id,
        links_matched=len(links),
        pattern=source.link_pattern,
    )
    if not links:
        # A pattern that matches nothing is almost always a redesigned page or a
        # wrong pattern, and either way nobody is watching this regulator any
        # more. Silence here would read exactly like "no new regulations".
        raise FetchError(
            "No links on that page matched the pattern. Either the site changed "
            "its layout or the pattern is wrong — nothing is being watched here.",
            permanent=True,
        )
    return _check_items(
        source, fetched, links, collection_title=source.label, label="listing"
    )


def _check_sparql(source: WatchedSource) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask a publisher's catalogue what it has published lately.

    The same discovery job a listing does, asked instead of scraped. A listing
    depends on a regex still matching a page a designer may rewrite; a query
    depends on the publisher's own classification of its own acts, which is what
    that classification is for. Where a publisher offers one, this is the better
    instrument — and the EU offers one precisely because its web page refuses
    automated readers.

    The window is a fixed lookback rather than "since the last check". A missed
    run, a clock skew or a restored backup would otherwise open a gap nobody
    notices, and re-asking for the same window costs nothing: everything already
    read is already remembered.
    """
    settings = get_settings()
    since = (_now() - timedelta(days=settings.source_sparql_lookback_days)).date().isoformat()
    query = (source.sparql_query or "").replace("{since}", since)
    fetched = fetching.fetch(
        fetching.sparql_url(source.url, query), accept=fetching.ACCEPT_SPARQL
    )
    items = fetching.parse_sparql_results(fetched.raw)
    fetching.log_read(
        fetched, None, source_id=source.id, rows=len(items), since=since
    )
    # No rows is a real answer here, unlike a listing whose pattern matched
    # nothing: a quiet four months in one subject area is ordinary, and the
    # query still ran and still returned a well-formed result.
    return _check_items(
        source, fetched, items, collection_title=source.label, label="catalogue"
    )


def check_source(source_id: str, *, force: bool = False) -> dict[str, Any]:
    """Read one watched source now and act on what came back.

    `force` skips the interval, not the lock — a user pressing the button wants
    an answer now, but two simultaneous reads of one address would ingest the
    same regulation twice.
    """
    source = get_source(source_id)
    if source is None:
        return {"source_id": source_id, "status": "not_found"}
    if not source.enabled and not force:
        return {"source_id": source_id, "status": "disabled", "url": source.url}
    if not force and not is_due(source):
        return {
            "source_id": source_id,
            "status": "not_due",
            "url": source.url,
            "last_checked_at": source.last_checked_at,
        }
    if not _claim(source_id):
        return {"source_id": source_id, "status": str(SourceCheckStatus.BUSY), "url": source.url}

    try:
        if source.kind == SourceKind.FEED:
            result, updates = _check_feed(source)
        elif source.kind == SourceKind.LISTING:
            result, updates = _check_listing(source)
        elif source.kind == SourceKind.SPARQL:
            result, updates = _check_sparql(source)
        else:
            result, updates = _check_document(source)
    except FetchError as exc:
        # A broken source is data, not an exception to swallow. It is recorded,
        # rendered, and the next run tries again.
        log(
            logger, logging.WARNING, "source check failed",
            source_id=source_id, url=source.url, error=str(exc)[:300],
        )
        _release(
            source_id,
            {
                "last_status": str(SourceCheckStatus.ERROR),
                "last_error": str(exc)[:500],
                "last_checked_at": firestore.SERVER_TIMESTAMP,
                "checks": source.checks + 1,
            },
        )
        return {
            "source_id": source_id,
            "url": source.url,
            "label": source.label,
            "status": str(SourceCheckStatus.ERROR),
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 - the lock must be released whatever happened
        log(
            logger, logging.ERROR, "source check crashed",
            source_id=source_id, url=source.url, error=str(exc)[:300],
        )
        _release(
            source_id,
            {
                "last_status": str(SourceCheckStatus.ERROR),
                "last_error": f"unexpected: {type(exc).__name__}",
                "last_checked_at": firestore.SERVER_TIMESTAMP,
                "checks": source.checks + 1,
            },
        )
        raise

    _release(
        source_id,
        updates | {"last_checked_at": firestore.SERVER_TIMESTAMP, "checks": source.checks + 1},
    )
    return {"source_id": source_id, "url": source.url, "label": source.label, **result}


def check_all(*, force: bool = False) -> dict[str, Any]:
    """The scheduled sweep. Every enabled source that is due, one at a time.

    Sequential on purpose: the fan-out that matters happens after ingestion, in
    Pub/Sub, where it is already idempotent and already bounded by max
    instances. Firing ten fetches at once here would only make the failure modes
    harder to read.
    """
    sources = [s for s in list_sources() if s.enabled]
    results: list[dict[str, Any]] = []
    for source in sources:
        if not force and not is_due(source):
            results.append(
                {"source_id": source.id, "url": source.url, "label": source.label, "status": "not_due"}
            )
            continue
        try:
            results.append(check_source(source.id, force=force))
        except Exception as exc:  # noqa: BLE001 - one bad source must not end the sweep
            log(
                logger, logging.ERROR, "sweep continued past a crash",
                source_id=source.id, error=str(exc)[:300],
            )
            results.append(
                {
                    "source_id": source.id,
                    "url": source.url,
                    "label": source.label,
                    "status": str(SourceCheckStatus.ERROR),
                    "error": f"unexpected: {type(exc).__name__}",
                }
            )

    def count(status: str) -> int:
        return sum(1 for r in results if r.get("status") == status)

    summary = {
        "checked": len(results),
        "changed": count(str(SourceCheckStatus.CHANGED)),
        "unchanged": count(str(SourceCheckStatus.UNCHANGED)),
        "baselined": count(str(SourceCheckStatus.BASELINED)),
        "errors": count(str(SourceCheckStatus.ERROR)),
        "documents_ingested": sum(len(r.get("ingested") or []) for r in results),
    }
    log(logger, logging.INFO, "source sweep complete", **summary)
    return {"summary": summary, "results": results}
