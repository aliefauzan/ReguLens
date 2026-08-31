"""Watched sources — the parts that decide whether a regulation changed.

These tests carry the reasoning that is easy to lose. The load-bearing claim of
the whole feature is "we noticed a change", and every way of getting that wrong
is quiet: a hash over bytes cries wolf every night, a feed with no baseline
ingests its own archive on adoption, a lock that never expires strands a source
forever. None of those raise; they just make the app dishonest.

No network and no Firestore here. Everything below is the deterministic layer,
which is exactly where the decisions live.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core import fetching, sources
from app.core.fetching import FetchError
from app.models import (
    SourceCheckStatus,
    SourceKind,
    SourceType,
    WatchedSource,
    WatchedSourceIn,
)

# ---------------------------------------------------------------------------
# Markup to words
# ---------------------------------------------------------------------------


def test_script_and_style_bodies_are_dropped_whole():
    """Removing only the tags would leave a page of JavaScript in the middle of
    the regulation, and the model would read it."""
    markup = "<p>Benzoic acid</p><script>var limit = 999;</script><style>p{color:red}</style>"
    text = fetching.html_to_text(markup)
    assert "Benzoic acid" in text
    assert "999" not in text
    assert "color" not in text


def test_row_ends_become_line_breaks():
    """A limit table read as one long line loses the pairing between a substance
    and its number, which is the only thing the table is for."""
    markup = "<table><tr><td>E 210</td><td>150</td></tr><tr><td>E 200</td><td>300</td></tr></table>"
    lines = [line for line in fetching.html_to_text(markup).split("\n") if line.strip()]
    assert len(lines) == 2
    assert "E 210" in lines[0] and "150" in lines[0]
    assert "E 200" in lines[1] and "300" in lines[1]


def test_entities_are_unescaped():
    assert "150 mg/kg & up" in fetching.html_to_text("<p>150&nbsp;mg/kg &amp; up</p>")


def test_the_content_region_wins_when_the_page_names_one():
    markup = (
        "<body><nav>" + "menu " * 200 + "</nav>"
        "<main><p>Maximum level 150 mg/kg</p>" + "body text " * 200 + "</main></body>"
    )
    text = fetching.html_to_text(markup)
    assert "150 mg/kg" in text
    assert "menu" not in text


def test_a_page_with_no_content_region_is_read_whole():
    """EUR-Lex is pre-`<main>` markup with the regulation sitting in the body.
    A stricter rule would return nothing for the source that matters most."""
    markup = "<body><p>COMMISSION REGULATION (EU) 2023/2108</p></body>"
    assert "2023/2108" in fetching.html_to_text(markup)


def test_a_tiny_content_region_does_not_swallow_the_page():
    """A teaser `<article>` on a long page is a widget, not the page. Better to
    over-read than to silently drop the regulation."""
    markup = "<body>" + "<p>Maximum level 150 mg/kg</p>" * 200 + "<article>Related</article></body>"
    text = fetching.html_to_text(markup)
    assert "150 mg/kg" in text


# ---------------------------------------------------------------------------
# What kind of thing came back
# ---------------------------------------------------------------------------


def test_plain_text_is_left_alone():
    result = fetching.to_text(b"Batas Maksimal 400 mg/kg", "text/plain; charset=utf-8")
    assert result.method == "plain"
    assert result.text == "Batas Maksimal 400 mg/kg"


def test_html_is_recognised_without_a_content_type():
    """Some servers send no content type at all, or the wrong one."""
    result = fetching.to_text(b"<html><body><p>150 mg/kg</p></body></html>", "")
    assert result.method == "html"
    assert "150 mg/kg" in result.text


def test_a_pdf_is_recognised_by_its_magic_bytes():
    assert fetching.looks_like_pdf(b"%PDF-1.7 ...", "")
    assert fetching.looks_like_pdf(b"anything", "application/pdf")
    assert not fetching.looks_like_pdf(b"<html>", "text/html")


def test_xml_is_not_mistaken_for_html():
    """A feed body must not be run through the markup stripper — the entries
    would survive as prose and the entry ids would be gone."""
    assert not fetching.looks_like_html(b"<?xml version='1.0'?><rss></rss>", "application/rss+xml")


# ---------------------------------------------------------------------------
# The change signal
# ---------------------------------------------------------------------------


def test_the_same_wording_hashes_the_same_through_different_bytes():
    """This is the whole reason the text hash exists. EUR-Lex stamps a fresh
    session id into every response, so the raw bytes differ on every fetch while
    the regulation has not moved. Hashing bytes would report a change — and a
    model run — every single night."""
    page = "<html><body><p>Maximum level 150 mg/kg</p><!--{token}--></body></html>"
    first = fetching.to_text(page.format(token="session-abc").encode(), "text/html")
    second = fetching.to_text(page.format(token="session-xyz").encode(), "text/html")
    assert first.sha256 == second.sha256


def test_changed_wording_changes_the_hash():
    a = fetching.to_text(b"<p>Maximum level 150 mg/kg</p>", "text/html")
    b = fetching.to_text(b"<p>Maximum level 200 mg/kg</p>", "text/html")
    assert a.sha256 != b.sha256


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------

RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <title>Food Safety</title>
  <item>
    <title>New additive limits</title>
    <link>https://example.test/a</link>
    <guid isPermaLink="false">urn:item:1</guid>
    <pubDate>Tue, 26 Aug 2026 09:00:00 +0000</pubDate>
  </item>
  <item>
    <title>Consultation opened</title>
    <link>https://example.test/b</link>
  </item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Official Journal</title>
  <entry>
    <id>urn:oj:1</id>
    <title>Regulation 2026/1</title>
    <link rel="self" href="https://example.test/self"/>
    <link rel="alternate" href="https://example.test/read"/>
    <updated>2026-08-26T09:00:00Z</updated>
  </entry>
</feed>"""


def test_rss_entries_prefer_the_guid_as_identity():
    """A link can be rewritten — a tracking parameter, http to https — without
    the item being new. The guid is the publisher saying which item this is."""
    feed = fetching.parse_feed(RSS)
    assert feed.title == "Food Safety"
    assert [e.key for e in feed.entries] == ["urn:item:1", "https://example.test/b"]
    assert feed.entries[0].link == "https://example.test/a"
    assert feed.entries[0].published


def test_atom_takes_the_alternate_link_not_the_self_link():
    """`rel="self"` points back at the feed entry, not at the thing to read."""
    feed = fetching.parse_feed(ATOM)
    assert feed.entries[0].key == "urn:oj:1"
    assert feed.entries[0].link == "https://example.test/read"


def test_an_empty_feed_is_not_an_error():
    """A quiet week is a real answer. Treating it as a failure would light up
    the UI for nothing."""
    feed = fetching.parse_feed(b"<rss version='2.0'><channel><title>x</title></channel></rss>")
    assert feed.entries == []


def test_a_feed_carrying_a_doctype_is_refused():
    """Entity expansion in XML from an address a user typed is a denial of
    service against the nightly job. No real feed needs a DOCTYPE."""
    bomb = (
        b"<?xml version='1.0'?><!DOCTYPE rss [<!ENTITY a 'aa'><!ENTITY b '&a;&a;'>]>"
        b"<rss version='2.0'><channel><title>&b;</title></channel></rss>"
    )
    with pytest.raises(FetchError, match="document type declaration"):
        fetching.parse_feed(bomb)


def test_html_served_at_a_feed_address_is_refused_clearly():
    with pytest.raises(FetchError):
        fetching.parse_feed(b"<html><body>not a feed</body></html>")


# ---------------------------------------------------------------------------
# Scheduling arithmetic
# ---------------------------------------------------------------------------


def _source(**overrides) -> WatchedSource:
    base = {
        "id": "src_test",
        "url": "https://example.test/rule",
        "label": "Test rule",
        "kind": SourceKind.DOCUMENT,
        "source_type": SourceType.OFFICIAL_REGULATION,
        "jurisdiction": "EU",
    }
    return WatchedSource(**(base | overrides))


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def test_a_source_never_checked_is_due():
    assert sources.is_due(_source(), NOW)


def test_a_source_checked_within_its_interval_is_not_due():
    recent = _source(last_checked_at=NOW - timedelta(hours=3), check_interval_hours=24)
    assert not sources.is_due(recent, NOW)


def test_a_source_past_its_interval_is_due():
    stale = _source(last_checked_at=NOW - timedelta(hours=25), check_interval_hours=24)
    assert sources.is_due(stale, NOW)


def test_a_disabled_source_is_never_due():
    assert not sources.is_due(_source(enabled=False), NOW)


def test_a_naive_timestamp_does_not_crash_the_sweep():
    """Firestore returns aware datetimes and a locally-built record may not.
    Comparing the two raises, and it would raise on the one path nobody
    exercises locally — the scheduled one."""
    naive = _source(last_checked_at=datetime(2026, 8, 20, 12, 0))
    assert sources.is_due(naive, NOW)


def test_a_fresh_lock_blocks_a_second_check():
    assert sources.is_locked(_source(check_lock_at=NOW - timedelta(seconds=30)), NOW)


def test_a_stale_lock_is_ignored():
    """A lock belonging to a process that died must not strand the source
    forever — nothing would ever release it."""
    assert not sources.is_locked(_source(check_lock_at=NOW - timedelta(hours=6)), NOW)


def test_no_lock_is_not_locked():
    assert not sources.is_locked(_source(), NOW)


def test_seen_entry_ids_are_capped():
    """An unbounded list eventually exceeds Firestore's document limit and takes
    the source down with it. The newest ids are the ones worth keeping."""
    from app.settings import get_settings

    cap = get_settings().source_seen_entry_cap
    capped = sources._cap_seen([f"id-{i}" for i in range(cap + 50)])
    assert len(capped) == cap
    assert capped[-1] == f"id-{cap + 49}"


# ---------------------------------------------------------------------------
# The registry itself
# ---------------------------------------------------------------------------


def test_a_watched_source_must_be_an_http_address():
    """`file:///etc/passwd` reaching a fetcher that runs on a schedule with the
    worker's credentials is not a hypothetical."""
    with pytest.raises(ValueError, match="http"):
        WatchedSourceIn(
            url="file:///etc/passwd",
            label="local",
            source_type=SourceType.OFFICIAL_REGULATION,
            jurisdiction="EU",
        )


@pytest.mark.parametrize("spec", sources.SEED_SOURCES, ids=lambda s: s["label"][:30])
def test_every_seeded_source_is_valid(spec):
    """A seed that fails validation breaks the button that installs it."""
    source = WatchedSourceIn(**spec)
    assert source.url.startswith("https://")
    assert source.jurisdiction in {"EU", "ID_BPOM"}


def test_a_news_feed_is_seeded_as_news_not_as_regulation():
    """Authority tier caps what a clause may do. A news item registered as an
    official regulation would let a headline move a limit."""
    feeds = [s for s in sources.SEED_SOURCES if s["kind"] == SourceKind.FEED]
    assert feeds, "the watch list has no feed in it"
    for spec in feeds:
        assert spec["source_type"] == SourceType.NEWS_ARTICLE


def test_seeded_urls_are_unique():
    urls = [spec["url"] for spec in sources.SEED_SOURCES]
    assert len(urls) == len(set(urls))


def test_a_feed_that_has_never_been_checked_starts_from_never_checked():
    """`_check_feed` branches on exactly this value to decide whether to
    baseline. A different default would make adoption ingest the archive."""
    assert _source(kind=SourceKind.FEED).last_status == SourceCheckStatus.NEVER_CHECKED


# ---------------------------------------------------------------------------
# The check flow
#
# Firestore and the network are replaced, and nothing else is. What is under
# test is which branch a check takes and what it writes back — the part where a
# mistake is silent rather than loud.
# ---------------------------------------------------------------------------


class _Recorder:
    """Stands in for the three functions that touch Firestore or the graph."""

    def __init__(self, source: WatchedSource, *, claimable: bool = True):
        self.source = source
        self.claimable = claimable
        self.released: dict = {}
        self.ingested: list[str] = []

    def install(self, monkeypatch, *, fetches: dict[str, fetching.Fetched]):
        monkeypatch.setattr(sources, "get_source", lambda _id: self.source)
        monkeypatch.setattr(sources, "_claim", lambda _id: self.claimable)
        monkeypatch.setattr(
            sources,
            "_release",
            lambda _id, updates: self.released.update(sources._release_payload(updates)),
        )

        def fake_ingest(source, text, *, fetched_url, title=None):
            self.ingested.append(title or fetched_url)
            return {
                "document_id": f"doc_{len(self.ingested)}",
                "cached": False,
                "source_name": title or "read",
                "url": fetched_url,
                "chars": text.char_count,
            }

        monkeypatch.setattr(sources, "_ingest", fake_ingest)

        def fake_fetch(url, **kwargs):
            if url not in fetches:
                raise FetchError(f"no stub for {url}")
            stub = fetches[url]
            # Honour the conditional request the way a real server would.
            if stub.not_modified and not (kwargs.get("etag") or kwargs.get("last_modified")):
                return fetching.Fetched(url=url, status=200, content_type="text/html", raw=b"<p>x</p>")
            return stub

        monkeypatch.setattr(sources.fetching, "fetch", fake_fetch)


def _html(body: str) -> fetching.Fetched:
    return fetching.Fetched(
        url="https://example.test/rule", status=200, content_type="text/html", raw=body.encode()
    )


def test_a_document_whose_wording_is_unchanged_ingests_nothing(monkeypatch):
    body = "<p>Maximum level 150 mg/kg</p>"
    known = fetching.to_text(body.encode(), "text/html").sha256
    recorder = _Recorder(_source(last_text_sha=known, last_status=SourceCheckStatus.UNCHANGED))
    recorder.install(monkeypatch, fetches={"https://example.test/rule": _html(body)})

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.UNCHANGED)
    assert result["reason"] == "same_text"
    assert recorder.ingested == []
    assert "last_text_sha" not in recorder.released


def test_a_document_whose_wording_changed_is_ingested(monkeypatch):
    old = fetching.to_text(b"<p>Maximum level 150 mg/kg</p>", "text/html").sha256
    recorder = _Recorder(_source(last_text_sha=old, last_status=SourceCheckStatus.UNCHANGED))
    new_body = "<p>Maximum level 200 mg/kg</p>" + "padding text " * 40
    recorder.install(monkeypatch, fetches={"https://example.test/rule": _html(new_body)})

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.CHANGED)
    assert result["first_read"] is False
    assert len(recorder.ingested) == 1
    assert recorder.released["last_text_sha"] != old
    assert recorder.released["changes"] == 1
    assert recorder.released["document_ids"] == ["doc_1"]


def test_a_304_answer_skips_reading_the_body_entirely(monkeypatch):
    recorder = _Recorder(_source(last_etag='W/"v1"', last_text_sha="whatever"))
    recorder.install(
        monkeypatch,
        fetches={
            "https://example.test/rule": fetching.Fetched(
                url="https://example.test/rule", status=304, etag='W/"v1"', not_modified=True
            )
        },
    )

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.UNCHANGED)
    assert result["reason"] == "not_modified"
    assert recorder.ingested == []


def test_a_first_read_of_a_document_source_is_ingested(monkeypatch):
    """Adopting a regulation means read it and keep watching. A first read that
    ingested nothing would leave the source watched but the rule absent."""
    recorder = _Recorder(_source(last_text_sha=None))
    recorder.install(
        monkeypatch,
        fetches={"https://example.test/rule": _html("<p>150 mg/kg</p>" + "text " * 60)},
    )

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.CHANGED)
    assert result["first_read"] is True
    assert len(recorder.ingested) == 1


def test_a_page_that_is_almost_all_navigation_is_refused_not_ingested(monkeypatch):
    """A login wall and an expired link both come back as a short page. Reading
    one as a regulation would put navigation text in front of the model."""
    recorder = _Recorder(_source())
    recorder.install(monkeypatch, fetches={"https://example.test/rule": _html("<p>Sign in</p>")})

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.ERROR)
    assert "almost no text" in result["error"]
    assert recorder.ingested == []
    # The lock is released even on the failure path, or the source is stranded.
    assert recorder.released["check_lock_at"] is None
    assert recorder.released["last_status"] == str(SourceCheckStatus.ERROR)


def test_an_oversized_document_is_refused_rather_than_truncated(monkeypatch):
    """Half a regulation read confidently is worse than a regulation refused."""
    from app.settings import get_settings

    huge = "<p>" + ("Maximum level 150 mg/kg. " * 20_000) + "</p>"
    assert len(huge) > get_settings().max_fetch_chars
    recorder = _Recorder(_source())
    recorder.install(monkeypatch, fetches={"https://example.test/rule": _html(huge)})

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.ERROR)
    assert "we read up to" in result["error"]
    assert recorder.ingested == []


def test_a_locked_source_reports_busy_and_does_nothing(monkeypatch):
    recorder = _Recorder(_source(), claimable=False)
    recorder.install(monkeypatch, fetches={})

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.BUSY)
    assert recorder.ingested == []
    assert recorder.released == {}


def test_a_source_that_is_not_due_is_left_alone(monkeypatch):
    recorder = _Recorder(_source(last_checked_at=NOW))
    recorder.install(monkeypatch, fetches={})

    result = sources.check_source("src_test", force=False)

    assert result["status"] == "not_due"
    assert recorder.released == {}


def _feed_source(**overrides) -> WatchedSource:
    return _source(
        url="https://example.test/feed",
        kind=SourceKind.FEED,
        source_type=SourceType.NEWS_ARTICLE,
        **overrides,
    )


def _feed_fetch(body: bytes) -> fetching.Fetched:
    return fetching.Fetched(
        url="https://example.test/feed", status=200, content_type="application/rss+xml", raw=body
    )


def test_adopting_a_feed_remembers_its_entries_and_reads_none_of_them(monkeypatch):
    """Otherwise the first check of a news feed is twenty extraction runs for
    twenty things that already happened."""
    recorder = _Recorder(_feed_source())
    recorder.install(monkeypatch, fetches={"https://example.test/feed": _feed_fetch(RSS)})

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.BASELINED)
    assert result["entries_seen"] == 2
    assert recorder.ingested == []
    assert recorder.released["seen_entry_ids"] == ["urn:item:1", "https://example.test/b"]


def test_a_feed_with_nothing_new_ingests_nothing(monkeypatch):
    recorder = _Recorder(
        _feed_source(
            last_status=SourceCheckStatus.UNCHANGED,
            seen_entry_ids=["urn:item:1", "https://example.test/b"],
        )
    )
    recorder.install(monkeypatch, fetches={"https://example.test/feed": _feed_fetch(RSS)})

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.UNCHANGED)
    assert result["reason"] == "no_new_entries"
    assert recorder.ingested == []


def test_only_the_new_entries_of_a_feed_are_read(monkeypatch):
    recorder = _Recorder(
        _feed_source(last_status=SourceCheckStatus.UNCHANGED, seen_entry_ids=["urn:item:1"])
    )
    recorder.install(
        monkeypatch,
        fetches={
            "https://example.test/feed": _feed_fetch(RSS),
            "https://example.test/b": _html("<p>Consultation opened. 150 mg/kg</p>" + "x " * 200),
        },
    )

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.CHANGED)
    assert result["new_entries"] == 1
    assert recorder.ingested == ["Consultation opened"]
    assert recorder.released["seen_entry_ids"] == ["urn:item:1", "https://example.test/b"]


def test_a_feed_burst_is_capped_and_the_rest_come_back_next_time(monkeypatch):
    """A regulator publishing ten things overnight must not become ten model
    runs before anyone is awake to see the bill."""
    from app.settings import get_settings

    cap = get_settings().source_max_new_per_check
    items = "".join(
        f"<item><title>Item {i}</title><link>https://example.test/i{i}</link></item>"
        for i in range(cap + 4)
    )
    body = f"<rss version='2.0'><channel><title>f</title>{items}</channel></rss>".encode()
    recorder = _Recorder(_feed_source(last_status=SourceCheckStatus.UNCHANGED, seen_entry_ids=["x"]))
    recorder.install(
        monkeypatch,
        fetches={"https://example.test/feed": _feed_fetch(body)}
        | {
            f"https://example.test/i{i}": _html(f"<p>Item {i} says 150 mg/kg</p>" + "y " * 200)
            for i in range(cap + 4)
        },
    )

    result = sources.check_source("src_test", force=True)

    assert result["new_entries"] == cap + 4
    assert len(recorder.ingested) == cap
    # Only what was read is remembered; the rest are still new next run.
    assert len(recorder.released["seen_entry_ids"]) == 1 + cap


def test_an_unreadable_feed_entry_stays_new_so_the_next_run_retries_it(monkeypatch):
    """A regulation that was briefly unreachable must not be silently skipped
    forever."""
    recorder = _Recorder(
        _feed_source(last_status=SourceCheckStatus.UNCHANGED, seen_entry_ids=["urn:item:1"])
    )
    # No stub for the entry link, so fetching it raises FetchError.
    recorder.install(monkeypatch, fetches={"https://example.test/feed": _feed_fetch(RSS)})

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.UNCHANGED)
    assert len(result["failed"]) == 1
    assert recorder.ingested == []
    assert recorder.released["seen_entry_ids"] == ["urn:item:1"]
    assert recorder.released["last_error"]


# ---------------------------------------------------------------------------
# The HTTP layer
#
# httpx is driven through a mock transport rather than the network, so the
# answers a real regulator gives — a 404, a 304, and EUR-Lex's empty `202` to
# datacentre addresses — are pinned as behaviour instead of as anecdotes.
# ---------------------------------------------------------------------------


def _serve(monkeypatch, handler):
    """Point `fetching.fetch` at an in-process responder."""
    import functools

    import httpx

    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        functools.partial(real_client, transport=httpx.MockTransport(handler)),
    )


def test_a_404_is_reported_as_a_moved_or_refused_address(monkeypatch):
    _serve(monkeypatch, lambda request: __import__("httpx").Response(404))
    with pytest.raises(FetchError, match="answered 404"):
        fetching.fetch("https://example.test/gone")


def test_an_empty_2xx_body_gets_its_own_sentence(monkeypatch):
    """EUR-Lex answers a Cloud Run address with `202 Accepted` and no body. That
    is bot mitigation, and calling it 'a login page or a scan with no text
    layer' sends whoever reads it looking in entirely the wrong place."""
    import httpx

    _serve(monkeypatch, lambda request: httpx.Response(202, content=b""))
    with pytest.raises(FetchError, match="sent nothing back"):
        fetching.fetch("https://example.test/blocked")


def test_a_304_returns_without_a_body(monkeypatch):
    import httpx

    _serve(monkeypatch, lambda request: httpx.Response(304, headers={"etag": 'W/"v2"'}))
    result = fetching.fetch("https://example.test/rule", etag='W/"v1"')
    assert result.not_modified
    assert result.etag == 'W/"v2"'
    assert result.raw == b""


def test_the_validators_we_hold_are_sent_back(monkeypatch):
    """Without these headers the server has no way to answer 304, and the
    cheapest possible check never happens."""
    import httpx

    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, content=b"<p>ok</p>")

    _serve(monkeypatch, handler)
    fetching.fetch("https://example.test/rule", etag='W/"v1"', last_modified="Wed, 27 Aug 2026 10:00:00 GMT")
    assert seen["if-none-match"] == 'W/"v1"'
    assert seen["if-modified-since"] == "Wed, 27 Aug 2026 10:00:00 GMT"


def test_a_document_fetch_asks_for_a_document_not_metadata(monkeypatch):
    """The EU Publications Office content-negotiates: a request with no `Accept`
    is answered with RDF *about* the regulation rather than the regulation. That
    reached extraction once and failed there."""
    import httpx

    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, content=b"<p>ok</p>")

    _serve(monkeypatch, handler)
    fetching.fetch("https://example.test/rule")
    assert seen["accept"].startswith("text/html")
    assert "application/pdf" in seen["accept"]


def test_a_feed_fetch_asks_for_a_feed():
    assert fetching.ACCEPT_FEED.startswith("application/rss+xml")
    assert "application/atom+xml" in fetching.ACCEPT_FEED


def test_an_oversized_download_is_cut_off_mid_stream(monkeypatch):
    """The cap has to bite while the body is arriving. Reading it all first and
    then measuring is the same failure it exists to prevent."""
    import httpx

    from app.settings import get_settings

    too_big = b"x" * (get_settings().max_fetch_mb * 1024 * 1024 + 1024)
    _serve(monkeypatch, lambda request: httpx.Response(200, content=too_big))
    with pytest.raises(FetchError, match="larger than"):
        fetching.fetch("https://example.test/huge")


# ---------------------------------------------------------------------------
# The closed-client fallback
#
# Not part of watched sources, but found by one: the first scheduled sweep in
# production ingested a real regulation and the document then failed
# extraction. It belongs with these tests because this is where the evidence is.
# ---------------------------------------------------------------------------


def test_a_closed_genai_client_is_rebuilt_once_and_the_call_succeeds(monkeypatch):
    """The ADK path emits nothing for one part, the pipeline degrades to the
    direct path on purpose — and the fallback used to die with "Cannot send a
    request, as the client has been closed", recording a document as failed
    when it still had a working path left."""
    from app.core.extraction import llm

    calls = {"built": 0, "sent": 0}

    class _Models:
        def generate_content(self, **kwargs):
            calls["sent"] += 1
            if calls["built"] == 1:
                raise RuntimeError("Cannot send a request, as the client has been closed.")
            return "a response"

    class _Client:
        models = _Models()

    def build():
        calls["built"] += 1
        return _Client()

    llm._client.cache_clear()
    monkeypatch.setattr(llm, "_client", __import__("functools").lru_cache(build))
    assert llm._generate(model="x") == "a response"
    assert calls["built"] == 2, "the client should have been rebuilt exactly once"
    assert calls["sent"] == 2


def test_a_second_closure_inside_one_call_is_a_real_fault(monkeypatch):
    """Retrying forever would turn a broken environment into a silent loop."""
    from app.core.extraction import llm

    class _Models:
        def generate_content(self, **kwargs):
            raise RuntimeError("Cannot send a request, as the client has been closed.")

    class _Client:
        models = _Models()

    llm._client.cache_clear()
    monkeypatch.setattr(llm, "_client", __import__("functools").lru_cache(lambda: _Client()))
    with pytest.raises(RuntimeError, match="client has been closed"):
        llm._generate(model="x")


def test_any_other_error_is_raised_untouched(monkeypatch):
    from app.core.extraction import llm

    class _Models:
        def generate_content(self, **kwargs):
            raise RuntimeError("429 quota exceeded")

    class _Client:
        models = _Models()

    llm._client.cache_clear()
    monkeypatch.setattr(llm, "_client", __import__("functools").lru_cache(lambda: _Client()))
    with pytest.raises(RuntimeError, match="quota"):
        llm._generate(model="x")


def test_both_genai_clients_are_handed_a_transport_we_own(monkeypatch):
    """The guard in the SDK is `if not self._http_options.httpx_client`. Passing
    one is the only thing that stops a finished object's garbage collection from
    closing the transport the next call needs, so this is pinned rather than
    left to a comment."""
    from google.genai import types

    from app.core import reconciliation
    from app.core.extraction import llm

    seen: list[types.HttpOptions | None] = []

    class _FakeClient:
        def __init__(self, **kwargs):
            seen.append(kwargs.get("http_options"))

    import google.genai

    monkeypatch.setattr(google.genai, "Client", _FakeClient)
    llm._client.cache_clear()
    reconciliation._embed_client.cache_clear()
    try:
        llm._client()
        reconciliation._embed_client()
        assert len(seen) == 2
        for options in seen:
            assert options is not None, "a client with no http_options gets a transport it will lose"
            assert options.httpx_client is not None
        # One transport, not two: the point is a single long-lived client.
        assert seen[0].httpx_client is seen[1].httpx_client
    finally:
        llm._client.cache_clear()
        reconciliation._embed_client.cache_clear()


# ---------------------------------------------------------------------------
# Listings — discovery, as opposed to change-watching
#
# A watched document can only report that a rule you already hold was edited.
# A regulation published tomorrow arrives at an address nobody has seen, and
# the regulator's index is where it turns up first.
# ---------------------------------------------------------------------------

LISTING_PAGE = """
<html><body>
  <nav><a href="/about">About us</a><a href="https://twitter.com/x">Follow</a></nav>
  <a href="/download/rule/1773/12/2026/Peraturan%20Nomor%2012%20Tahun%202026">
    <img src="/pdf.png">
  </a>
  <a href="/download/rule/1774/13/2026/Peraturan%20Nomor%2013%20Tahun%202026">Nomor 13</a>
  <a href="#top">Back to top</a>
  <a href="/download/rule/1773/12/2026/Peraturan%20Nomor%2012%20Tahun%202026#page2">same doc</a>
  <a href="mailto:x@y.test">Mail us</a>
</body></html>
"""


def test_only_links_matching_the_pattern_are_followed():
    """A listing page carries navigation, a language switcher and social links.
    A watcher that followed every link would ingest the website."""
    links = fetching.extract_links(LISTING_PAGE, "https://jdih.test/", r"/download/rule/\d+/")
    assert [link.link for link in links] == [
        "https://jdih.test/download/rule/1773/12/2026/Peraturan%20Nomor%2012%20Tahun%202026",
        "https://jdih.test/download/rule/1774/13/2026/Peraturan%20Nomor%2013%20Tahun%202026",
    ]


def test_a_fragment_is_not_a_different_document():
    """`#page2` on an act already read is the same act. Treating it as new would
    ingest the regulation twice and bill two extraction runs for it."""
    links = fetching.extract_links(LISTING_PAGE, "https://jdih.test/", r"/download/rule/\d+/")
    assert len(links) == 2, "the #page2 link is the first document again"


def test_a_relative_link_is_resolved_against_the_page_it_was_found_on():
    links = fetching.extract_links(
        '<a href="rule/9/">nine</a>', "https://jdih.test/produk/index.html", r"rule/"
    )
    assert links[0].link == "https://jdih.test/produk/rule/9/"


def test_a_link_with_no_text_is_named_from_its_address():
    """BPOM's index links are icons — nothing between the tags. Falling back to
    the raw URL would put a hundred characters of path where the user reads the
    document's name."""
    links = fetching.extract_links(LISTING_PAGE, "https://jdih.test/", r"/download/rule/1773/")
    assert links[0].title == "Peraturan Nomor 12 Tahun 2026"


def test_a_link_whose_text_is_real_keeps_it():
    links = fetching.extract_links(LISTING_PAGE, "https://jdih.test/", r"/download/rule/1774/")
    assert links[0].title == "Nomor 13"


def test_a_listing_needs_a_pattern():
    with pytest.raises(ValueError, match="link_pattern"):
        WatchedSourceIn(
            url="https://jdih.test/",
            label="index",
            kind=SourceKind.LISTING,
            source_type=SourceType.OFFICIAL_REGULATION,
            jurisdiction="ID_BPOM",
        )


def test_an_uncompilable_pattern_is_refused_when_it_is_typed(monkeypatch):
    """Not at fetch time. A pattern that cannot compile would otherwise fail
    every night at 06:00, in a log nobody is reading."""
    with pytest.raises(ValueError, match="not a valid expression"):
        WatchedSourceIn(
            url="https://jdih.test/",
            label="index",
            kind=SourceKind.LISTING,
            link_pattern="[unclosed",
            source_type=SourceType.OFFICIAL_REGULATION,
            jurisdiction="ID_BPOM",
        )


def _listing_source(**overrides) -> WatchedSource:
    return _source(
        url="https://jdih.test/",
        kind=SourceKind.LISTING,
        link_pattern=r"/download/rule/\d+/",
        jurisdiction="ID_BPOM",
        **overrides,
    )


def _page(body: str, url: str = "https://jdih.test/") -> fetching.Fetched:
    return fetching.Fetched(url=url, status=200, content_type="text/html", raw=body.encode())


def test_adopting_a_listing_records_what_is_already_there(monkeypatch):
    recorder = _Recorder(_listing_source())
    recorder.install(monkeypatch, fetches={"https://jdih.test/": _page(LISTING_PAGE)})

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.BASELINED)
    assert result["entries_seen"] == 2
    assert recorder.ingested == []


def test_a_regulation_published_at_a_new_address_is_picked_up(monkeypatch):
    """The whole point. Nothing already watched mentions this act; it exists
    because a new link appeared on the index."""
    recorder = _Recorder(
        _listing_source(
            last_status=SourceCheckStatus.UNCHANGED,
            seen_entry_ids=[
                "https://jdih.test/download/rule/1773/12/2026/Peraturan%20Nomor%2012%20Tahun%202026"
            ],
        )
    )
    new_link = "https://jdih.test/download/rule/1774/13/2026/Peraturan%20Nomor%2013%20Tahun%202026"
    recorder.install(
        monkeypatch,
        fetches={
            "https://jdih.test/": _page(LISTING_PAGE),
            new_link: _page("<p>Batas maksimal 400 mg/kg</p>" + "isi " * 200, url=new_link),
        },
    )

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.CHANGED)
    assert result["new_entries"] == 1
    assert recorder.ingested == ["Nomor 13"]


def test_a_pattern_that_matches_nothing_is_an_error_not_a_quiet_pass(monkeypatch):
    """A redesigned page means nobody is watching this regulator any more.
    Reporting "no new regulations" would be indistinguishable from working."""
    recorder = _Recorder(_listing_source(last_status=SourceCheckStatus.UNCHANGED))
    recorder.install(
        monkeypatch, fetches={"https://jdih.test/": _page("<a href='/news'>News</a>")}
    )

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.ERROR)
    assert "nothing is being watched here" in result["error"]


def test_an_item_that_can_never_be_read_is_not_retried_forever(monkeypatch):
    """BPOM's Kategori Pangan annex is 308 pages and will be 308 pages tomorrow.
    Left unseen it would be downloaded and refused every night, holding a slot
    in the per-run cap that a readable new regulation needed."""
    recorder = _Recorder(
        _listing_source(
            last_status=SourceCheckStatus.UNCHANGED,
            seen_entry_ids=[
                "https://jdih.test/download/rule/1773/12/2026/Peraturan%20Nomor%2012%20Tahun%202026"
            ],
        )
    )
    new_link = "https://jdih.test/download/rule/1774/13/2026/Peraturan%20Nomor%2013%20Tahun%202026"
    huge = "<p>" + ("Batas maksimal 400 mg/kg. " * 20_000) + "</p>"
    recorder.install(
        monkeypatch,
        fetches={"https://jdih.test/": _page(LISTING_PAGE), new_link: _page(huge, url=new_link)},
    )

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.UNCHANGED)
    assert result["failed"][0]["permanent"] is True
    assert new_link in recorder.released["seen_entry_ids"], "a permanent refusal is remembered"


def test_a_transient_failure_still_comes_back_next_run(monkeypatch):
    """A regulation that was briefly unreachable must not be skipped forever."""
    recorder = _Recorder(
        _listing_source(
            last_status=SourceCheckStatus.UNCHANGED,
            seen_entry_ids=[
                "https://jdih.test/download/rule/1773/12/2026/Peraturan%20Nomor%2012%20Tahun%202026"
            ],
        )
    )
    # No stub for the new link, so fetching it raises a non-permanent FetchError.
    recorder.install(monkeypatch, fetches={"https://jdih.test/": _page(LISTING_PAGE)})

    result = sources.check_source("src_test", force=True)

    assert result["failed"][0]["permanent"] is False
    assert len(recorder.released["seen_entry_ids"]) == 1, "a transient failure stays new"


def test_a_size_refusal_is_permanent_and_a_timeout_is_not():
    from app.settings import get_settings

    huge = fetching.to_text(("x" * (get_settings().max_fetch_chars + 10)).encode(), "text/plain")
    with pytest.raises(FetchError) as refusal:
        sources._guard_size(huge, "https://x.test/")
    assert refusal.value.permanent is True

    assert FetchError("we could not reach that address").permanent is False


def test_the_seeded_listing_can_discover_a_new_regulation():
    """A watch list with no listing in it can only ever report edits to rules
    somebody already found."""
    listings = [s for s in sources.SEED_SOURCES if s["kind"] == SourceKind.LISTING]
    assert listings, "nothing in the watch list can discover a new regulation"
    for spec in listings:
        assert WatchedSourceIn(**spec).link_pattern


# ---------------------------------------------------------------------------
# Catalogue queries
#
# The EU's own web pages refuse a datacentre address, so its discovery has to be
# asked rather than scraped — and asking turns out to be the better instrument
# anyway: the filter is the publisher's classification of its own acts, not a
# regex over a layout a designer can rewrite.
# ---------------------------------------------------------------------------

SPARQL_JSON = b"""{
  "head": {"vars": ["celex", "date"]},
  "results": {"bindings": [
    {"celex": {"value": "32026R1860"}, "date": {"value": "2026-07-29"}},
    {"celex": {"value": "32026R1890"}, "date": {"value": "2026-07-29"}},
    {"celex": {"value": "32026R1860"}, "date": {"value": "2026-07-29"}}
  ]}
}"""


def test_a_celex_row_becomes_a_fetchable_address():
    entries = fetching.parse_sparql_results(SPARQL_JSON)
    assert entries[0].link == "https://publications.europa.eu/resource/celex/32026R1860"
    assert entries[0].key == "32026R1860"
    assert entries[0].published == "2026-07-29"


def test_the_same_act_twice_in_one_result_is_one_item():
    """A CELEX id repeats across language expressions. Ingesting the duplicate
    would spend a second extraction run on a regulation already read."""
    assert [e.key for e in fetching.parse_sparql_results(SPARQL_JSON)] == [
        "32026R1860",
        "32026R1890",
    ]


def test_an_identifier_is_not_used_as_the_documents_name():
    """`32026R1860` says which act this is and is not what anyone wants to read.
    The act states its own title and detection can read it."""
    assert fetching.parse_sparql_results(SPARQL_JSON)[0].prefer_detected_title is True


def test_a_plain_uri_result_is_accepted_too():
    raw = b'{"results": {"bindings": [{"work": {"value": "https://x.test/act/1"}}]}}'
    entry = fetching.parse_sparql_results(raw)[0]
    assert entry.link == "https://x.test/act/1"
    assert entry.key == "https://x.test/act/1"


def test_rows_that_name_no_document_are_an_error_not_an_empty_answer():
    """Returning [] would read as "no new regulations" when the truth is that
    the query selected columns nothing can be fetched from."""
    raw = b'{"results": {"bindings": [{"count": {"value": "7"}}]}}'
    with pytest.raises(FetchError, match="named a document"):
        fetching.parse_sparql_results(raw)


def test_an_empty_result_set_is_a_real_answer():
    """Unlike a listing whose pattern matched nothing, a quiet four months in
    one subject area is ordinary. The query ran and answered."""
    assert fetching.parse_sparql_results(b'{"results": {"bindings": []}}') == []


def test_a_non_sparql_body_is_refused_permanently():
    with pytest.raises(FetchError) as exc:
        fetching.parse_sparql_results(b"<html>bot check</html>")
    assert exc.value.permanent is True


def test_the_query_url_is_something_a_human_can_paste():
    url = fetching.sparql_url("http://x.test/sparql", "SELECT * WHERE {}")
    assert url.startswith("http://x.test/sparql?")
    assert "format=application%2Fsparql-results%2Bjson" in url
    assert "query=SELECT" in url


def test_an_endpoint_that_already_has_a_query_string_keeps_it():
    assert fetching.sparql_url("http://x.test/s?a=1", "SELECT").startswith("http://x.test/s?a=1&")


def test_a_sparql_source_needs_a_query():
    with pytest.raises(ValueError, match="sparql_query"):
        WatchedSourceIn(
            url="http://x.test/sparql",
            label="catalogue",
            kind=SourceKind.SPARQL,
            source_type=SourceType.OFFICIAL_REGULATION,
            jurisdiction="EU",
        )


def test_a_query_selecting_nothing_fetchable_is_refused_when_it_is_typed():
    """Otherwise it reports "no new regulations" every night while watching
    nothing at all."""
    with pytest.raises(ValueError, match="naming each document"):
        WatchedSourceIn(
            url="http://x.test/sparql",
            label="catalogue",
            kind=SourceKind.SPARQL,
            sparql_query="SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }",
            source_type=SourceType.OFFICIAL_REGULATION,
            jurisdiction="EU",
        )


def test_the_seeded_eu_query_is_bounded_and_asks_for_regulations():
    """An unfiltered catalogue query returns every act the EU publishes. The
    subject concept and the CELEX shape are what keep this to roughly a dozen
    regulations a year instead of hundreds of documents a month."""
    spec = next(s for s in sources.SEED_SOURCES if s["kind"] == SourceKind.SPARQL)
    query = spec["sparql_query"]
    assert "{since}" in query, "the window has to move with the calendar"
    assert "eurovoc.europa.eu/6052" in query, "unfiltered by subject, this floods"
    assert "^3[0-9]{4}R[0-9]{4}$" in query, "without this it ingests merger notices"
    assert "LIMIT" in query
    WatchedSourceIn(**spec)


def test_every_market_can_discover_a_new_regulation():
    """The point of the whole exercise: watching a document you already hold can
    only report that it was edited."""
    discovering = {SourceKind.LISTING, SourceKind.SPARQL}
    covered = {s["jurisdiction"] for s in sources.SEED_SOURCES if s["kind"] in discovering}
    assert covered == {"EU", "ID_BPOM"}


def _sparql_source(**overrides) -> WatchedSource:
    return _source(
        url="http://x.test/sparql",
        kind=SourceKind.SPARQL,
        sparql_query='SELECT ?celex WHERE { FILTER(?d > "{since}") }',
        **overrides,
    )


def test_a_catalogue_check_substitutes_the_window_and_reads_new_acts(monkeypatch):
    asked: list[str] = []

    recorder = _Recorder(
        _sparql_source(last_status=SourceCheckStatus.UNCHANGED, seen_entry_ids=["32026R1890"])
    )
    act = "https://publications.europa.eu/resource/celex/32026R1860"

    def fake_fetch(url, **kwargs):
        if url.startswith("http://x.test/sparql"):
            asked.append(url)
            return fetching.Fetched(
                url=url, status=200, content_type="application/sparql-results+json",
                raw=SPARQL_JSON,
            )
        return fetching.Fetched(
            url=act, status=200, content_type="text/html",
            raw=("<p>Maximum level 150 mg/kg</p>" + "text " * 200).encode(),
        )

    recorder.install(monkeypatch, fetches={})
    monkeypatch.setattr(sources.fetching, "fetch", fake_fetch)

    result = sources.check_source("src_test", force=True)

    assert result["status"] == str(SourceCheckStatus.CHANGED)
    assert result["new_entries"] == 1, "the act already seen must not be read again"
    # The window was substituted, not sent literally.
    assert "%7Bsince%7D" not in asked[0] and "{since}" not in asked[0]
    # The document was left to name itself rather than being called '32026R1860'.
    assert recorder.ingested == [act]
