"""Country discovery: finding a regulator's catalogue for a country nobody seeded.

Until now the watch list was hand-written. `SEED_SOURCES` holds four addresses
that a person found, fetched, and checked from the deployed service before
writing them down. That is honest but it does not scale past the two markets the
demo ships with: a user importing into Japan gets no monitoring at all, because
nobody typed a Japanese address into the source list.

This module closes that gap, and the shape of the solution is dictated by one
measured fact.

**A model cannot tell you a URL that exists.** Measured against gemma-4-31b on
31 Aug 2026, over six countries: regulator names 6/6 correct, root domains 6/6
correct (`mhlw.go.jp`, `fssai.gov.in`, `sfa.gov.sg`, `moh.gov.my`, …), and
*every single URL carrying a path* wrong — 0 of 14 resolved. Not "sometimes
stale": the model reconstructs a plausible path from the shape of paths it has
seen, and regulators rewrite paths constantly. No prompt fixes this. Asking a
model for `https://www.mhlw.go.jp/stf/seisakunits03_00001.html` is asking it to
guess a hash.

So the model is never asked for a path. It is asked for the two things it gets
right, and everything deeper is read off pages we actually fetched:

    hop 0  model: country -> regulator name + root URL
    hop 1  we fetch the root and extract its real link inventory
    hop 2  model: pick the regulations index FROM THAT INVENTORY
    hop 3  we fetch the pick and derive the link pattern from its real paths
    commit an ordinary LISTING source, exactly like the BPOM JDIH seed

Hop 2 is grounded by construction: the model chooses from a list we hand it, and
a pick that is not in the list is dropped rather than trusted. It cannot
hallucinate a URL because it is not producing URLs, it is selecting them.

**Why a listing and not a document.** The same reason `SEED_SOURCES` watches
`jdih.pom.go.id/` rather than one BPOM decree: a watched document only ever
tells you a rule you already know about was edited, while the regulation
published next month appears at an address nobody has seen. The regulator's own
index is where it shows up first. Discovery therefore looks for the index — the
thing the existing `_check_listing` path already knows how to read.

**What this refuses to do.** It does not invent a regulator, it does not commit
an address it could not read, and it does not report success when it found the
site but not the rules. Every rejection carries the reason a user sees. A
country whose regulator publishes through a JavaScript application returns "the
index has no links we can follow", which is true and useful, rather than an
empty success.
"""

from __future__ import annotations

import functools
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core import fetching, markets, sources
from app.core.fetching import FetchError
from app.models import SourceKind, SourceType, WatchedSourceIn
from app.observability import get_trace_id, log
from app.settings import get_settings

logger = logging.getLogger(__name__)

COLLECTION = "discovery_jobs"
DATA_FILE = Path(__file__).parent / "data" / "countries.json"

# How many index pages one country may commit. Two is enough for a regulator
# that splits acts from standards (Singapore does), and small enough that a
# discovery run stays inside one worker request.
MAX_CANDIDATES = 2

# Links handed to the model in hop 2. The free tier that makes Gemma free also
# caps input at 16,000 tokens per minute per model — measured, not documented:
# a 220-link inventory returns RESOURCE_EXHAUSTED with
# `GenerateContentInputTokensPerModelPerMinute-FreeTier`. Eighty links with
# short titles is roughly 2,000 tokens and leaves headroom for a retry.
MAX_INVENTORY_LINKS = 80
MAX_TITLE_CHARS = 70

# A pattern that selects fewer links than this is not a regulations index; it is
# a coincidence. Three is the smallest number that distinguishes "these pages
# share a shape" from "two links happen to rhyme".
MIN_PATTERN_MATCHES = 3

# And a group this large is the site's own menu. Measured against
# `mhlw.go.jp/shokanhourei`, whose biggest family was 55 links covering every
# policy area the ministry runs.
MAX_PATTERN_MATCHES = 40

# Anchor text and paths that mark a regulations index rather than a news page.
# Used to rank candidates, never to invent one.
_INDEX_HINTS = re.compile(
    r"(?i)legislat|regulat|legal|law|act\b|standard|circular|gazette|"
    r"decree|statut|rule|jdih|peraturan|通知"
)

# What this product is actually about. Used to rank one cluster of links against
# another on the same page: a regulator publishes novel-food rules, labelling
# rules and additive rules side by side, and only one of them answers the
# question a user asked when they typed their country in.
_TOPIC_HINTS = re.compile(
    r"(?i)additive|preservative|colour|color|sweetener|antioxidant|"
    r"food safety|permitted|maximum level|regulatory limit|contaminant|"
    r"bahan tambahan|添加物"
)

_DIGIT_RUN = re.compile(r"\d+")
_SEPARATORS = re.compile(r"[-_/]+")
_FENCE_OPEN = re.compile(r"^```(?:json)?\s*")
_FENCE_CLOSE = re.compile(r"```\s*$")


class DiscoveryError(RuntimeError):
    """Discovery failed in a way the user is told about verbatim."""


class TransientDiscoveryError(RuntimeError):
    """Discovery failed in a way that retrying later fixes.

    Exactly one case today: the free tier's 16,000-input-tokens-per-minute
    ceiling. That quota refills on its own, so the message is nacked and Pub/Sub
    brings it back with backoff — the one failure here worth a redelivery, as
    against a regulator's 403, which would be a 403 four more times.
    """


@dataclass(frozen=True)
class Country:
    code: str
    name: str


@dataclass
class RootProposal:
    """Hop 0. The only thing the model is trusted to produce from memory."""

    regulator: str
    root_url: str


@dataclass
class CandidateSource:
    """A real address, read off a page we fetched. Not yet proven readable."""

    url: str
    label: str
    reason: str
    kind: SourceKind = SourceKind.LISTING
    link_pattern: str | None = None


@dataclass
class VerifiedSource:
    """A candidate that answered, and whose links we can actually follow."""

    url: str
    label: str
    reason: str
    link_pattern: str
    match_count: int
    kind: SourceKind = SourceKind.LISTING
    sample_links: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# The country list
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def load_countries() -> tuple[Country, ...]:
    """ISO 3166-1 alpha-2, bundled. No network at request time.

    Code and name only. An earlier draft of this file carried a `regulator` and
    an `authority_url` per country as a hint for the prompt; 249 hand-written
    regulator names is 249 chances to ship a wrong fact, and the measurement
    above says the model names the regulator correctly anyway. The data file
    holds what ISO publishes and nothing invented on top of it.
    """
    rows = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    countries = tuple(Country(code=r["code"], name=r["name"]) for r in rows)
    return tuple(sorted(countries, key=lambda c: c.name))


def list_supported_countries() -> list[dict[str, str]]:
    return [{"code": c.code, "name": c.name} for c in load_countries()]


def find_country(code: str) -> Country | None:
    wanted = (code or "").strip().upper()
    return next((c for c in load_countries() if c.code == wanted), None)


# ---------------------------------------------------------------------------
# The model calls. Two prompts, both small.
# ---------------------------------------------------------------------------

_ROOT_SYSTEM = """You name the national authority that publishes FOOD ADDITIVE regulations \
for a country, and its official website.

Return the authority's official site as scheme and host only — no path, no query. \
Return the regulator's usual English name.
Return an empty root_url only if you genuinely do not know the authority's website. \
Never assemble a domain out of the country name — give one you have seen."""

_ROOT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "regulator": {"type": "string"},
        "root_url": {"type": "string"},
    },
    "required": ["regulator", "root_url"],
}

_INDEX_SYSTEM = """You are given the real link inventory of a food regulator's website, \
already fetched. Choose the links most likely to be an INDEX OF PUBLISHED REGULATIONS: \
a legal-documentation portal, a legislation page, a standards list, circulars, or a gazette.

Rules:
- Choose ONLY from the supplied links. Copy each url exactly as given.
- Prefer an index of legal documents over news, tenders, careers or training pages.
- Return an empty list if none of the supplied links is a regulations index.
- Never write a url that is not in the list."""

_INDEX_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["url", "reason"],
            },
        }
    },
    "required": ["picks"],
}


def _strip_fences(text: str) -> str:
    """Gemma wraps JSON in a code fence even when asked for `application/json`.

    Measured: `gemma-4-31b-it` with `response_mime_type="application/json"` and
    a response schema still returns `[ "Apple" ]\\n```'. The schema shapes the
    content, it does not clean the envelope, so the envelope is removed here and
    the shape is enforced by the validators below rather than by trust.
    """
    stripped = (text or "").strip()
    stripped = _FENCE_OPEN.sub("", stripped)
    return _FENCE_CLOSE.sub("", stripped.strip()).strip()


def _ask(system: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    from app.core.extraction import llm

    settings = get_settings()
    try:
        raw = llm.generate_structured(
            model=settings.discovery_model,
            contents=json.dumps(payload, ensure_ascii=False)[: settings.discovery_prompt_chars],
            system_instruction=system,
            response_schema=schema,
        )
    except Exception as exc:  # noqa: BLE001 - the SDK raises its own error types
        # An error out of the SDK must not leave this module as itself. Uncaught
        # it reaches the worker as a 500, Pub/Sub nacks, and the same failing
        # country is retried five times — five more model calls to reach the
        # same 404. Only the refillable quota earns a redelivery.
        message = str(exc)
        if "RESOURCE_EXHAUSTED" in message or "429" in message:
            raise TransientDiscoveryError(
                f"the free tier for {settings.discovery_model} is exhausted; "
                "it refills within a minute"
            ) from exc
        if "NOT_FOUND" in message and "ublisher model" in message:
            # Gemma is served by the Gemini Developer API, not by Vertex. This
            # is what a missing GEMINI_API_KEY looks like from in here.
            raise DiscoveryError(
                f"{settings.discovery_model} is not available on this deployment "
                "— Gemma needs a Gemini API key, Vertex does not serve it"
            ) from exc
        raise DiscoveryError(f"the model call failed: {message[:200]}") from exc
    try:
        parsed = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as exc:
        raise DiscoveryError(f"the model did not return JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise DiscoveryError("the model returned JSON that is not an object")
    return parsed


def propose_root(country: Country) -> RootProposal | None:
    """Hop 0. Regulator and root domain, or nothing.

    Returns `None` rather than a guess when the model declines or hands back
    something that is not an https origin — a path here means the model ignored
    the instruction, and the measurement says a path from memory is wrong.
    """
    settings = get_settings()
    if settings.fake_discovery:
        return _FAKE_ROOTS.get(country.code)

    answer = _ask(_ROOT_SYSTEM, {"country": country.name, "code": country.code}, _ROOT_SCHEMA)
    regulator = str(answer.get("regulator") or "").strip()
    root = str(answer.get("root_url") or "").strip()
    if not regulator or not root:
        return None

    parsed = urlparse(root)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    # A path from memory is the failure mode this module exists to avoid. Keep
    # the origin, throw the rest away.
    return RootProposal(regulator=regulator[:200], root_url=f"{parsed.scheme}://{parsed.netloc}")


def link_inventory(url: str, *, timeout: float | None = None) -> list[fetching.FeedEntry]:
    """Hop 1. Every link on a page, as the page really serves it.

    Raises `FetchError` — the caller turns it into the sentence a user reads.
    """
    fetched = fetching.fetch(url, timeout=timeout)
    markup = fetched.raw.decode("utf-8", "ignore")
    return fetching.extract_links(markup, fetched.url, r".")


def choose_indexes(country: Country, inventory: list[fetching.FeedEntry]) -> list[CandidateSource]:
    """Hop 2. Which of these real links is the regulations index.

    Every pick is checked against the inventory it was chosen from. A url the
    model wrote rather than selected is dropped and logged: the whole point of
    handing it a list is that a pick outside the list is a defect, not an idea.
    """
    if not inventory:
        return []

    ranked = sorted(
        inventory,
        key=lambda e: (
            not _INDEX_HINTS.search(f"{e.title} {e.link}"),
            len(urlparse(e.link).path),
        ),
    )[:MAX_INVENTORY_LINKS]
    by_url = {e.link: e for e in ranked}

    settings = get_settings()
    if settings.fake_discovery:
        picks = [{"url": e.link, "reason": "fake"} for e in ranked[:MAX_CANDIDATES]]
    else:
        answer = _ask(
            _INDEX_SYSTEM,
            {
                "country": country.name,
                "links": [
                    {"url": e.link, "title": e.title[:MAX_TITLE_CHARS]} for e in ranked
                ],
            },
            _INDEX_SCHEMA,
        )
        picks = answer.get("picks") or []
        if not isinstance(picks, list):
            raise DiscoveryError("the model returned picks that are not a list")

    candidates: list[CandidateSource] = []
    for pick in picks[: MAX_CANDIDATES * 2]:
        if not isinstance(pick, dict):
            continue
        url = str(pick.get("url") or "").strip()
        entry = by_url.get(url)
        if entry is None:
            log(
                logger,
                logging.WARNING,
                "discovery pick was not in the inventory",
                country=country.code,
                url=url[:200],
            )
            continue
        candidates.append(
            CandidateSource(
                url=entry.link,
                label=f"{country.name} — {entry.title or 'regulations index'}"[:200],
                reason=str(pick.get("reason") or "")[:300],
            )
        )
        if len(candidates) >= MAX_CANDIDATES:
            break
    return candidates


# ---------------------------------------------------------------------------
# Deriving the link pattern — deterministic, from real paths
# ---------------------------------------------------------------------------


def _shape(url: str, depth: int) -> str | None:
    """The regex shape of a path's first `depth` segments.

    `/download/rule/123/title` at depth 2 is `/download/rule`. Digit runs
    generalise because that is what a document id looks like; the literal
    segments stay literal because that is what separates a document link from
    the navigation around it.

    A path with fewer segments than `depth` returns `None` rather than a shorter
    shape — a two-segment path is not evidence of a three-segment family, and
    letting it match would put whole sections of a site under one pattern.
    """
    segments = [s for s in urlparse(url).path.split("/") if s]
    if len(segments) < depth:
        return None
    generalised = [_DIGIT_RUN.sub(r"\\d+", re.escape(s)) for s in segments[:depth]]
    return "/" + "/".join(generalised)


def derive_pattern(links: list[fetching.FeedEntry]) -> tuple[str, int, list[str]]:
    """Hop 3. The `link_pattern` for a listing source, read off its own links.

    Returns `(pattern, match_count, samples)`. Raises `DiscoveryError` when no
    shape on the page is shared by enough links to be a document family — which
    is the honest answer for a page that is all navigation.

    The pattern is never asked of the model. A regex is exactly the kind of
    detail a model produces confidently and wrongly, and here it decides which
    addresses the nightly check will ingest.
    """
    if not links:
        raise DiscoveryError("the index has no links we can follow")

    def score(item: tuple[str, list[fetching.FeedEntry]]) -> tuple[int, int, int]:
        """Topic first, shape second, size last.

        Size alone is the wrong ranking, and it was wrong in a way that only
        showed up against a real site: `sfa.gov.sg` has six links under
        `novel-food-framework` and four under `food-safety-regulatory-limits`,
        so the larger group won and discovery committed a novel-food page for a
        food-additive product. The titles say which cluster is on topic —
        "Regulatory Limits for Food Additives" against "Novel Food Regulatory
        Framework" — so they are what decides.
        """
        shape, entries = item
        # Hyphens and underscores are word separators in a URL path, so
        # `food-safety-regulatory-limits` has to read as the phrase it is before
        # either vocabulary can match it.
        text = _SEPARATORS.sub(" ", " ".join(f"{e.title} {e.link}" for e in entries))
        return (
            len(_TOPIC_HINTS.findall(text)),
            1 if _INDEX_HINTS.search(f"{_SEPARATORS.sub(' ', shape)} {text}") else 0,
            len(entries),
        )

    # Two granularities, most specific first. A regulator that files documents
    # under `/download/rule/<id>/<title>` is a two-segment family; one that
    # publishes `/legislation/<act-name>` is a one-segment family, and grouping
    # only at two segments would give every act its own cluster and refuse a
    # perfectly good index.
    best: tuple[str, list[fetching.FeedEntry]] | None = None
    for depth in (2, 1):
        clusters: dict[str, list[fetching.FeedEntry]] = {}
        for entry in links:
            shape = _shape(entry.link, depth)
            if shape is None:
                continue
            clusters.setdefault(shape, []).append(entry)
        if not clusters:
            continue
        candidate = max(clusters.items(), key=score)
        if len(candidate[1]) >= MIN_PATTERN_MATCHES:
            best = candidate
            break
        best = best or candidate

    if best is None:
        raise DiscoveryError("the index has no links we can follow")

    shape, entries = best
    if len(entries) < MIN_PATTERN_MATCHES:
        raise DiscoveryError(
            f"no group of links on that page shares a shape "
            f"({len(entries)} of {len(links)} at best, {MIN_PATTERN_MATCHES} needed)"
        )

    topical, indexish, _ = score(best)
    # A cluster that swallows the page is the site's own navigation. Measured on
    # `mhlw.go.jp/shokanhourei`: the largest family was 55 links under
    # `/stf/seisakunitsuite`, which is every policy area the ministry has —
    # pensions, long-term care, employment. Committing it would have pointed the
    # nightly sweep at the whole ministry.
    if len(entries) > MAX_PATTERN_MATCHES:
        raise DiscoveryError(
            f"the largest group on that page holds {len(entries)} links — "
            "that is the site's navigation, not a set of regulations"
        )
    if not topical and not indexish:
        raise DiscoveryError(
            "nothing in those links names a regulation, a standard or an additive"
        )
    return shape, len(entries), [e.link for e in entries[:3]]


def verify_candidate(candidate: CandidateSource) -> VerifiedSource:
    """Fetch the candidate and prove its links can be followed.

    Refuses, with the reason, on: a fetch that fails or is refused, a page whose
    links do not form a family, and a body too small to be an index. Refusal is
    the point — a source committed here is one the nightly sweep will read
    unattended, and "it returned 200" is not evidence it holds regulations.

    Note the standing rule: a URL that answers a laptop may answer a datacentre
    with a challenge page. This runs on the worker, so the verification and the
    nightly check see the same internet.
    """
    if urlparse(candidate.url).scheme != "https":
        raise DiscoveryError("that address is not https")

    links = link_inventory(candidate.url)
    pattern, count, samples = derive_pattern(links)
    return VerifiedSource(
        url=candidate.url,
        label=candidate.label,
        reason=candidate.reason,
        link_pattern=pattern,
        match_count=count,
        sample_links=samples,
    )


# ---------------------------------------------------------------------------
# Committing
# ---------------------------------------------------------------------------


def commit_verified(country: Country, regulator: str, verified: VerifiedSource) -> tuple[str, bool]:
    """Register the source and make sure a market speaks for it.

    Both halves matter. `impact.py` skips any clause whose jurisdiction is not
    listed by some market, so a source committed without its market ingests
    regulations that never reach a verdict — the user would see a green row and
    no answer, which is the worst outcome this module could produce.

    The write itself goes through `sources.add_source`, the same call the manual
    form uses, which already returns an existing row rather than duplicating a
    URL. Idempotency is inherited, not reimplemented.
    """
    markets.ensure_market(
        country_code=country.code, country_name=country.name, regulator=regulator
    )
    source, created = sources.add_source(
        WatchedSourceIn(
            url=verified.url,
            label=verified.label,
            kind=verified.kind,
            source_type=SourceType.OFFICIAL_REGULATION,
            jurisdiction=country.code,
            link_pattern=verified.link_pattern,
        )
    )
    return source.id, created


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def new_job(country: Country, trace_id: str) -> dict[str, Any]:
    return {
        "country_code": country.code,
        "country_name": country.name,
        "status": "queued",
        "regulator": None,
        "root_url": None,
        "candidates": [],
        "error": None,
        "model": get_settings().discovery_model,
        "trace_id": trace_id,
        "started_at": _now().isoformat(),
        "finished_at": None,
    }


def run_discovery(country_code: str, job: dict[str, Any]) -> dict[str, Any]:
    """The whole flow, as a pure-ish function over one job dict.

    Returns the finished job. Never raises for an ordinary failure: a country
    whose regulator cannot be read is a *result*, recorded with its reason, not
    an exception that a retry will repeat five times.
    """
    country = find_country(country_code)
    if country is None:
        return job | {"status": "failed", "error": f"unknown country code {country_code!r}",
                      "finished_at": _now().isoformat()}

    job = job | {"status": "proposing"}
    try:
        proposal = propose_root(country)
    except DiscoveryError as exc:
        return job | {"status": "failed", "error": str(exc), "finished_at": _now().isoformat()}

    if proposal is None:
        return job | {
            "status": "failed",
            "error": f"no official food regulator site is known for {country.name}",
            "finished_at": _now().isoformat(),
        }

    job = job | {"status": "reading", "regulator": proposal.regulator,
                 "root_url": proposal.root_url}

    try:
        inventory = link_inventory(proposal.root_url)
    except FetchError as exc:
        return job | {
            "status": "failed",
            "error": f"{proposal.root_url} could not be read: {exc}",
            "finished_at": _now().isoformat(),
        }
    if not inventory:
        return job | {
            "status": "failed",
            "error": (
                f"{proposal.root_url} answered but carries no links we can follow "
                "— the site is probably rendered in the browser"
            ),
            "finished_at": _now().isoformat(),
        }

    try:
        candidates = choose_indexes(country, inventory)
    except DiscoveryError as exc:
        return job | {"status": "failed", "error": str(exc), "finished_at": _now().isoformat()}

    if not candidates:
        return job | {
            "status": "failed",
            "error": f"nothing on {proposal.root_url} looks like an index of regulations",
            "finished_at": _now().isoformat(),
        }

    rows: list[dict[str, Any]] = []
    seen_patterns: set[str] = set()
    committed = 0
    for candidate in candidates:
        row: dict[str, Any] = {
            "url": candidate.url,
            "label": candidate.label,
            "reason": candidate.reason,
            "status": "validating",
            "source_id": None,
            "link_pattern": None,
            "match_count": 0,
            "error": None,
        }
        try:
            verified = verify_candidate(candidate)
        except (DiscoveryError, FetchError) as exc:
            row |= {"status": "rejected", "error": str(exc)}
            rows.append(row)
            continue

        if verified.link_pattern in seen_patterns:
            # Two index pages that select the same documents are one source
            # with extra steps: the nightly sweep would fetch both and ingest
            # the same regulations twice.
            row |= {
                "status": "rejected",
                "error": "this page leads to the same documents as the one above",
            }
            rows.append(row)
            continue
        seen_patterns.add(verified.link_pattern)

        source_id, created = commit_verified(country, proposal.regulator, verified)
        committed += 1
        row |= {
            "status": "committed",
            "source_id": source_id,
            "link_pattern": verified.link_pattern,
            "match_count": verified.match_count,
            "created": created,
        }
        rows.append(row)

    status = "done" if committed == len(rows) else ("partial" if committed else "failed")
    error = None
    if committed == 0:
        error = f"found {proposal.regulator} but none of its index pages could be read"
    return job | {
        "status": status,
        "candidates": rows,
        "committed": committed,
        "error": error,
        "finished_at": _now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Firestore
# ---------------------------------------------------------------------------


def save_job(job_id: str, job: dict[str, Any]) -> None:
    from app.db import get_db
    from app.models import WORKSPACE_ID

    get_db().collection(COLLECTION).document(job_id).set(
        job | {"workspace_id": WORKSPACE_ID}, merge=True
    )


def get_job(job_id: str) -> dict[str, Any] | None:
    from app.db import get_db

    snapshot = get_db().collection(COLLECTION).document(job_id).get()
    if not snapshot.exists:
        return None
    return (snapshot.to_dict() or {}) | {"id": snapshot.id}


def active_job_for(country_code: str) -> dict[str, Any] | None:
    """A job for this country that has not finished.

    Re-pressing Discover while one is running joins the run in progress instead
    of starting a second — the same idempotency the upload path has, for the
    same reason: the expensive thing must not happen twice because a user
    clicked twice.
    """
    from google.cloud import firestore

    from app.db import get_db
    from app.models import WORKSPACE_ID

    snapshots = (
        get_db()
        .collection(COLLECTION)
        .where(filter=firestore.FieldFilter("workspace_id", "==", WORKSPACE_ID))
        .where(filter=firestore.FieldFilter("country_code", "==", country_code.upper()))
        .where(
            filter=firestore.FieldFilter(
                "status", "in", ["queued", "proposing", "reading", "validating"]
            )
        )
        .limit(1)
        .stream()
    )
    for snapshot in snapshots:
        return (snapshot.to_dict() or {}) | {"id": snapshot.id}
    return None


def discover(job_id: str, country_code: str) -> dict[str, Any]:
    """Run one job to completion and store every state it passes through."""
    existing = get_job(job_id) or {}
    country = find_country(country_code)
    job = existing or new_job(
        country or Country(code=country_code, name=country_code), get_trace_id()
    )
    finished = run_discovery(country_code, job)
    save_job(job_id, finished)
    log(
        logger,
        logging.INFO,
        "discovery finished",
        job_id=job_id,
        country=country_code,
        status=finished.get("status"),
        committed=finished.get("committed", 0),
        model=finished.get("model"),
    )
    return finished | {"id": job_id}


# ---------------------------------------------------------------------------
# Fixtures for the offline stack
# ---------------------------------------------------------------------------

# `FAKE_DISCOVERY=1` stands in for the model only. The fetch is real in the
# local drill too, against the stub regulator served by the compose stack, so
# the pattern derivation is exercised rather than mocked away.
_FAKE_ROOTS: dict[str, RootProposal] = {
    "JP": RootProposal(regulator="Ministry of Health, Labour and Welfare",
                       root_url="https://www.mhlw.go.jp"),
    "SG": RootProposal(regulator="Singapore Food Agency", root_url="https://www.sfa.gov.sg"),
}
