"""Reading a regulator's own page over HTTP, and turning it into text.

Everything here is deterministic and has no Firestore in it, so the awkward
parts — what counts as a change, what an RSS entry is called — are testable
without a network or a database.

Two facts learned from the real sites drove the shape of this module:

1. **The bytes change even when the regulation does not.** EUR-Lex sets a fresh
   session cookie and stamps a request id into every response, so hashing the
   raw body reports a change on every single fetch. Hashing the *extracted
   text* reports a change only when the words changed, which is the question
   actually being asked. Both hashes are kept; only the text one decides.

2. **Conditional GET is a bonus, not the mechanism.** The Publications Office's
   CELLAR endpoint sends an `ETag`; the EUR-Lex web page sends neither `ETag`
   nor `Last-Modified`. When a server sends them we use them and skip the
   download entirely; when it does not, we download and compare text. The
   download is cheap. The model call it prevents is not.

3. **What works from a laptop may not work from Cloud Run.** EUR-Lex answers a
   datacentre address with `202 Accepted` and a challenge page instead of the
   regulation. So an empty 2xx body is its own named failure, `Accept` is sent
   explicitly, and the seeded EU source points at the publisher's
   machine-readable endpoint rather than the page a human would open.
"""

from __future__ import annotations

import hashlib
import html as html_module
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from app.observability import log
from app.settings import get_settings

logger = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """The source could not be read. Carries a sentence fit to show a user.

    `permanent` says whether trying again tomorrow could plausibly work. It
    exists because of what a listing does with a failure: an item that failed
    is normally left unseen so the next run retries it, which is right for a
    timeout and wrong for a 308-page annex. Without the distinction the same
    oversized PDF is downloaded and refused every night forever, and it holds a
    slot in the per-run cap that a readable new regulation needed.
    """

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


@dataclass
class Fetched:
    """One HTTP read. `not_modified` means the server answered 304 and there is
    no body to look at — which is the cheapest possible answer."""

    url: str
    status: int
    content_type: str = ""
    raw: bytes = b""
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False

    @property
    def raw_sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()


@dataclass
class SourceText:
    """What a fetched body says, once the markup is gone."""

    text: str
    method: str  # pdfplumber | html | plain
    page_count: int | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass
class FeedEntry:
    """One item out of a feed, an index page, or a query result."""

    key: str  # guid/id when the source gives one, else the link
    title: str
    link: str
    published: str | None = None
    # Set when the title here is an identifier rather than a name — a CELEX id
    # says which act this is but is not what anyone wants to read on a row. The
    # ingester then takes the title off the document itself, which it can read
    # perfectly well ("COMMISSION REGULATION (EU) 2023/2108").
    prefer_detected_title: bool = False


@dataclass
class FeedRead:
    title: str = ""
    entries: list[FeedEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


# What we are willing to read, in the order we would rather have it. This is not
# decoration: the EU Publications Office's CELLAR endpoint content-negotiates,
# and a request with no `Accept` gets RDF metadata about the regulation instead
# of the regulation. That reached extraction once and failed there, which is a
# slow and confusing way to find out you asked the wrong question.
ACCEPT_DOCUMENT = (
    "text/html,application/xhtml+xml,application/pdf;q=0.9,"
    "text/plain;q=0.8,application/xml;q=0.5,*/*;q=0.4"
)
ACCEPT_FEED = (
    "application/rss+xml,application/atom+xml,application/xml;q=0.9,text/xml;q=0.9,*/*;q=0.5"
)


def fetch(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    timeout: float | None = None,
    max_bytes: int | None = None,
    accept: str = ACCEPT_DOCUMENT,
) -> Fetched:
    """GET a URL, conditionally when the caller holds validators.

    Redirects are followed — a regulator moving a document behind a redirect is
    not a change of content, and refusing to follow would report every such move
    as a broken source.
    """
    import httpx

    settings = get_settings()
    timeout = timeout if timeout is not None else settings.fetch_timeout_seconds
    max_bytes = max_bytes if max_bytes is not None else settings.max_fetch_mb * 1024 * 1024

    headers = {
        "User-Agent": settings.source_user_agent,
        "Accept": accept,
        "Accept-Language": "en",
        # Servers that gzip by default still hand httpx decoded bytes, so this
        # only saves transfer.
        "Accept-Encoding": "gzip, deflate",
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
            with client.stream("GET", url) as response:
                if response.status_code == 304:
                    return Fetched(
                        url=str(response.url),
                        status=304,
                        etag=response.headers.get("etag", etag),
                        last_modified=response.headers.get("last-modified", last_modified),
                        not_modified=True,
                    )
                if response.status_code >= 400:
                    raise FetchError(
                        f"The source answered {response.status_code}. "
                        "Either the address moved or it is refusing automated reads."
                    )
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise FetchError(
                            f"The file is larger than {settings.max_fetch_mb} MB, which is more "
                            "than we read in one go. Point at the specific annex instead.",
                            permanent=True,
                        )
                    chunks.append(chunk)
                body = b"".join(chunks)
                if not body:
                    # A 2xx with nothing in it is its own failure and deserves
                    # its own sentence. EUR-Lex answers datacentre addresses
                    # with `202 Accepted` and an empty body — bot mitigation,
                    # not an error — and calling that "a login page or a scan"
                    # sends whoever reads it looking in the wrong place.
                    raise FetchError(
                        f"The source answered {response.status_code} and sent nothing back. "
                        "Some sites reply that way to automated readers; try the "
                        "publisher's machine-readable address instead."
                    )
                return Fetched(
                    url=str(response.url),
                    status=response.status_code,
                    content_type=response.headers.get("content-type", ""),
                    raw=body,
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                )
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001 - every transport failure reads the same to a user
        raise FetchError(f"We could not reach that address: {type(exc).__name__}") from exc


# ---------------------------------------------------------------------------
# Bytes to words
# ---------------------------------------------------------------------------

_PDF_MAGIC = b"%PDF"

# Anything inside these tags is machinery, not wording. Dropped whole, including
# the text between the tags — a stripper that only removed the tags would leave
# a page of JavaScript in the middle of the regulation.
_DROP_BLOCKS = re.compile(r"(?is)<(script|style|noscript|template|svg)\b.*?</\1\s*>")
# Tags whose end means "a line ended here". Without this every HTML table
# collapses into one line and the row structure a limit table depends on is gone.
_LINE_BREAKS = re.compile(r"(?is)<br\s*/?>|</(p|div|tr|li|h[1-6]|table|section|article)\s*>")
_TAGS = re.compile(r"(?s)<[^>]+>")
_INLINE_SPACE = re.compile(r"[ \t\xa0  ]+")
_BLANK_LINES = re.compile(r"\n\s*\n\s*")


# A modern government CMS wraps the actual page in five kilobytes of navigation
# and a language switcher listing twenty-four languages. Read whole, that
# boilerplate is what most of a news page turns out to be, and every character
# of it is sent to the model. `<main>` is where the page itself says its content
# starts, so when a page marks one, that is what gets read.
_MAIN_REGION = re.compile(r"(?is)<(main|article)\b[^>]*>(?P<body>.*?)</\1\s*>")


def _content_region(markup: str) -> str:
    """The page's own content region, when it names one.

    Falls back to the whole document, which is what EUR-Lex needs: its pages
    are pre-`<main>` markup with the regulation sitting directly in the body,
    and a stricter rule would return nothing at all for the source that matters
    most. Only the largest match is taken — a page with a `<main>` and three
    small `<article>` teasers should give up the main one.
    """
    matches = [m.group("body") for m in _MAIN_REGION.finditer(markup)]
    if not matches:
        return markup
    best = max(matches, key=len)
    # A "content region" holding less than a fifth of the page is a widget, not
    # the page. Better to over-read than to silently drop the regulation.
    return best if len(best) * 5 >= len(markup) else markup


def html_to_text(markup: str) -> str:
    """Markup to readable text, deterministically.

    Deliberately not an HTML parser dependency: the job is to get the wording
    and the row breaks out of a government page, and the failure mode of a
    regex here is a slightly untidy line, not a wrong limit. Extraction reads
    the wording; the guardrail rejects anything it cannot parse into a number
    with a unit.
    """
    text = _DROP_BLOCKS.sub(" ", _content_region(markup))
    text = _LINE_BREAKS.sub("\n", text)
    text = _TAGS.sub(" ", text)
    text = html_module.unescape(text)
    text = _INLINE_SPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def looks_like_pdf(raw: bytes, content_type: str = "") -> bool:
    return raw[:4] == _PDF_MAGIC or "pdf" in content_type.lower()


def looks_like_html(raw: bytes, content_type: str = "") -> bool:
    lowered = content_type.lower()
    if "html" in lowered:
        return True
    if "xml" in lowered or "json" in lowered or "text/plain" in lowered:
        return False
    head = raw[:2048].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<body" in head


def to_text(raw: bytes, content_type: str = "") -> SourceText:
    """Turn a fetched body into the text a clause could be read out of."""
    if looks_like_pdf(raw, content_type):
        from app.core.extraction.text import extract_pdf

        try:
            extracted = extract_pdf(raw)
        except Exception as exc:  # noqa: BLE001 - a broken PDF is the source's problem
            raise FetchError(
            f"That PDF could not be read: {type(exc).__name__}", permanent=True
        ) from exc
        return SourceText(
            text=extracted.text, method=extracted.method, page_count=extracted.page_count
        )

    decoded = raw.decode("utf-8", errors="replace")
    if looks_like_html(raw, content_type):
        return SourceText(text=html_to_text(decoded), method="html")
    return SourceText(text=decoded.strip(), method="plain")


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------

_ATOM = "{http://www.w3.org/2005/Atom}"


def _tag(element: ET.Element) -> str:
    """Local tag name, namespace stripped."""
    return element.tag.rsplit("}", 1)[-1]


def _child_text(parent: ET.Element, name: str) -> str:
    for child in parent:
        if _tag(child) == name and child.text:
            return child.text.strip()
    return ""


def _atom_link(entry: ET.Element) -> str:
    """Atom puts the URL in an attribute, and lists several kinds of link."""
    fallback = ""
    for child in entry:
        if _tag(child) != "link":
            continue
        href = (child.get("href") or "").strip()
        if not href:
            continue
        if (child.get("rel") or "alternate") == "alternate":
            return href
        fallback = fallback or href
    return fallback


# A feed is XML from a machine we do not control, so it is parsed defensively.
# `xml.etree` will not fetch an external entity, but it will happily expand a
# nested internal one until the process dies — the "billion laughs" attack, and
# a plain denial of service against a scheduled job that fetches whatever URL a
# user typed. No legitimate RSS or Atom feed needs a document type declaration,
# so the whole construct is refused before the parser ever sees it. That closes
# entity expansion and external-entity resolution together, without pulling in
# another dependency to do it.
_DOCTYPE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)\b", re.IGNORECASE)


def parse_feed(raw: bytes) -> FeedRead:
    """Read an RSS 2.0 or Atom feed into entries.

    Only the fields we act on are read: an identity, a title and a link. A feed
    that parses but names no entries is not an error — a quiet week is a real
    answer, and treating it as a failure would light up the UI for nothing.
    """
    if _DOCTYPE.search(raw[:8192]):
        raise FetchError(
            "That feed carries a document type declaration, which we refuse to expand. "
            "A regulator's feed does not need one.",
            permanent=True,
        )
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise FetchError(
            f"That address did not return a readable feed: {exc}", permanent=True
        ) from exc

    entries: list[FeedEntry] = []
    title = ""

    channel = next((c for c in root if _tag(c) == "channel"), None)
    if channel is not None:  # RSS 2.0
        title = _child_text(channel, "title")
        items = [c for c in channel if _tag(c) == "item"]
        for item in items:
            link = _child_text(item, "link")
            guid = _child_text(item, "guid")
            key = guid or link
            if not key:
                continue
            entries.append(
                FeedEntry(
                    key=key,
                    title=_child_text(item, "title") or key,
                    link=link or guid,
                    published=_child_text(item, "pubDate") or None,
                )
            )
        return FeedRead(title=title, entries=entries)

    if _tag(root) == "feed":  # Atom
        title = _child_text(root, "title")
        for entry in (c for c in root if _tag(c) == "entry"):
            link = _atom_link(entry)
            key = _child_text(entry, "id") or link
            if not key:
                continue
            entries.append(
                FeedEntry(
                    key=key,
                    title=_child_text(entry, "title") or key,
                    link=link or key,
                    published=_child_text(entry, "updated")
                    or _child_text(entry, "published")
                    or None,
                )
            )
        return FeedRead(title=title, entries=entries)

    raise FetchError("That address is neither an RSS nor an Atom feed.", permanent=True)


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

_ANCHOR = re.compile(r"(?is)<a\b[^>]*?href\s*=\s*[\"\'](?P<href>[^\"\']+)[\"\'][^>]*>(?P<label>.*?)</a\s*>")


def extract_links(markup: str, base_url: str, pattern: str) -> list[FeedEntry]:
    """Every link on a page whose address matches `pattern`, in page order.

    This is the answer to "what if the new rule is published at a different
    address?". A regulator's index page is where a new act first appears, and
    watching only the acts you already know about can never see one arrive.

    The pattern is required rather than defaulted, and that is deliberate. A
    listing page carries navigation, language switchers and social links; a
    watcher that followed every link would ingest the site. Making the caller
    say which shape of address is a document turns "read this page" into "read
    the things on this page that are regulations".

    Relative addresses are resolved against the page they were found on, and the
    fragment is dropped — `#section-2` on the same document is the same
    document, and treating it as a new one would ingest the act twice.
    """
    from urllib.parse import urldefrag, urljoin

    compiled = re.compile(pattern)
    seen: set[str] = set()
    entries: list[FeedEntry] = []
    for match in _ANCHOR.finditer(markup):
        href = html_module.unescape(match.group("href").strip())
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        absolute, _ = urldefrag(urljoin(base_url, href))
        if not compiled.search(absolute) or absolute in seen:
            continue
        seen.add(absolute)
        label = html_module.unescape(_TAGS.sub(" ", match.group("label")))
        label = _INLINE_SPACE.sub(" ", label).strip()
        entries.append(
            FeedEntry(key=absolute, title=(label or _title_from_url(absolute))[:200], link=absolute)
        )
    return entries


def _title_from_url(url: str) -> str:
    """A readable name when the link had none.

    BPOM's index links are icons — no text between the tags at all — but the
    address itself ends in the regulation's full title. Falling back to the raw
    URL would put a hundred characters of path into the document's name, where
    the name is what the user reads on the row.
    """
    from urllib.parse import unquote, urlparse

    tail = unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1])
    tail = _INLINE_SPACE.sub(" ", tail.replace("_", " ").replace("+", " ")).strip()
    return tail or url


# ---------------------------------------------------------------------------
# SPARQL
# ---------------------------------------------------------------------------

ACCEPT_SPARQL = "application/sparql-results+json,application/json;q=0.9,*/*;q=0.5"

# Where a CELEX identifier is turned back into something readable. The same
# address shape the EU document source already uses, and already proven to
# answer a Cloud Run address — which the EUR-Lex web page does not.
CELEX_RESOURCE = "https://publications.europa.eu/resource/celex/{celex}"


def sparql_url(endpoint: str, query: str) -> str:
    """A GET address for one SPARQL query.

    GET rather than POST so the whole thing stays inside the ordinary fetch
    path: one code path for timeouts, size caps, redirects and logging, and a
    URL a human can paste into a browser when they want to know what the
    watcher is actually asking.
    """
    from urllib.parse import urlencode

    separator = "&" if "?" in endpoint else "?"
    return endpoint + separator + urlencode(
        {"query": query, "format": "application/sparql-results+json"}
    )


def parse_sparql_results(raw: bytes) -> list[FeedEntry]:
    """Turn SPARQL JSON results into items, one per row.

    Two shapes are understood, and nothing else is guessed at: a `celex`
    binding, which is expanded into a Publications Office address, or a `work`
    / `uri` binding that is already an address. A query selecting neither has
    nothing to fetch, and saying so is better than returning an empty list that
    reads as "no new regulations".
    """
    import json

    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        rows = payload["results"]["bindings"]
    except Exception as exc:  # noqa: BLE001 - anything unparseable is the same failure
        raise FetchError(
            f"That endpoint did not return SPARQL JSON results: {type(exc).__name__}",
            permanent=True,
        ) from exc

    entries: list[FeedEntry] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        celex = (row.get("celex") or {}).get("value")
        if celex:
            key, link = celex, CELEX_RESOURCE.format(celex=celex)
        else:
            uri = (row.get("work") or row.get("uri") or {}).get("value")
            if not uri:
                continue
            key = link = uri
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            FeedEntry(
                key=key,
                title=key,
                link=link,
                published=(row.get("date") or {}).get("value"),
                # The identifier is not the act's name; the act states its own.
                prefer_detected_title=True,
            )
        )
    if rows and not entries:
        raise FetchError(
            "That query returned rows but none of them named a document. Select a "
            "`celex`, `work` or `uri` column.",
            permanent=True,
        )
    return entries


def summarise(fetched: Fetched, text: SourceText | None) -> dict[str, Any]:
    """The fields worth putting on a log line about one read."""
    summary: dict[str, Any] = {
        "url": fetched.url,
        "http_status": fetched.status,
        "not_modified": fetched.not_modified,
        "bytes": len(fetched.raw),
    }
    if text is not None:
        summary |= {
            "method": text.method,
            "chars": text.char_count,
            "page_count": text.page_count,
            "text_sha256": text.sha256[:16],
        }
    return summary


def log_read(fetched: Fetched, text: SourceText | None, **extra: Any) -> None:
    log(logger, logging.INFO, "source read", **summarise(fetched, text), **extra)
