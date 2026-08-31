"""Country discovery.

The tests that matter here are the refusals. Discovery commits an address the
nightly sweep will read unattended, so the interesting question is never "does
the happy path work" but "what does it decline to write down". Each refusal
below stands for a failure measured against real regulator sites on 31 Aug 2026:
a model that invents a path, a government site that answers a robot with 403,
and a portal whose links are all navigation.
"""

from __future__ import annotations

import json

import pytest

from app.core import discovery
from app.core.fetching import FeedEntry, FetchError
from app.models import SourceKind


def _entries(*urls: str) -> list[FeedEntry]:
    return [FeedEntry(key=u, title=u.rsplit("/", 1)[-1] or u, link=u) for u in urls]


# ---------------------------------------------------------------------------
# The country list
# ---------------------------------------------------------------------------


def test_country_list_is_iso_and_sorted() -> None:
    countries = discovery.list_supported_countries()
    assert len(countries) > 200
    codes = [c["code"] for c in countries]
    assert len(set(codes)) == len(codes)
    assert all(len(c) == 2 and c.isupper() for c in codes)
    assert [c["name"] for c in countries] == sorted(c["name"] for c in countries)


def test_country_list_carries_no_invented_fields() -> None:
    """Code and name only. A bundled `regulator` per country would be 249
    hand-written facts nobody verified, and the model names it correctly."""
    assert all(set(c) == {"code", "name"} for c in discovery.list_supported_countries())


def test_find_country_is_case_insensitive() -> None:
    assert discovery.find_country("jp").name == "Japan"
    assert discovery.find_country("JP").name == "Japan"
    assert discovery.find_country("ZZ") is None


# ---------------------------------------------------------------------------
# Hop 0 — the model proposes a root, and only a root
# ---------------------------------------------------------------------------


def _stub_model(monkeypatch, payload: object) -> None:
    def fake(**_kwargs):
        return json.dumps(payload)

    monkeypatch.setattr("app.core.extraction.llm.generate_structured", fake)


def test_propose_root_keeps_only_the_origin(monkeypatch) -> None:
    """The measured failure: paths from memory are wrong 14 times out of 14.

    A model that answers with a path has ignored the instruction, so the path is
    discarded rather than fetched.
    """
    _stub_model(monkeypatch, {"regulator": "MHLW", "root_url": "https://www.mhlw.go.jp/stf/x.html"})
    proposal = discovery.propose_root(discovery.find_country("JP"))
    assert proposal.root_url == "https://www.mhlw.go.jp"
    assert proposal.regulator == "MHLW"


def test_propose_root_declines_rather_than_guesses(monkeypatch) -> None:
    _stub_model(monkeypatch, {"regulator": "Unknown", "root_url": ""})
    assert discovery.propose_root(discovery.find_country("AQ")) is None


def test_propose_root_rejects_a_non_http_scheme(monkeypatch) -> None:
    _stub_model(monkeypatch, {"regulator": "X", "root_url": "ftp://files.example.gov"})
    assert discovery.propose_root(discovery.find_country("JP")) is None


def test_model_output_survives_a_code_fence(monkeypatch) -> None:
    """Gemma wraps JSON in a fence even when asked for `application/json`.

    Measured, not hypothetical: `gemma-4-31b-it` with a response schema still
    returns a trailing ```` ``` ````.
    """
    monkeypatch.setattr(
        "app.core.extraction.llm.generate_structured",
        lambda **_k: '```json\n{"regulator": "SFA", "root_url": "https://www.sfa.gov.sg"}\n```',
    )
    proposal = discovery.propose_root(discovery.find_country("SG"))
    assert proposal.root_url == "https://www.sfa.gov.sg"


def test_a_non_json_answer_is_an_error_not_a_guess(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.extraction.llm.generate_structured", lambda **_k: "I'm not sure!"
    )
    with pytest.raises(discovery.DiscoveryError):
        discovery.propose_root(discovery.find_country("JP"))


# ---------------------------------------------------------------------------
# Hop 2 — the model selects, it does not write
# ---------------------------------------------------------------------------


def test_a_pick_outside_the_inventory_is_dropped(monkeypatch) -> None:
    """The guarantee that makes this flow safe.

    The model is handed real links and told to choose. A url it produced instead
    of selecting is exactly the hallucination this design exists to prevent, so
    it is discarded — never fetched, never committed.
    """
    inventory = _entries(
        "https://www.sfa.gov.sg/legislation",
        "https://www.sfa.gov.sg/careers",
    )
    _stub_model(
        monkeypatch,
        {
            "picks": [
                {"url": "https://www.sfa.gov.sg/invented-by-the-model", "reason": "made up"},
                {"url": "https://www.sfa.gov.sg/legislation", "reason": "real"},
            ]
        },
    )
    picked = discovery.choose_indexes(discovery.find_country("SG"), inventory)
    assert [c.url for c in picked] == ["https://www.sfa.gov.sg/legislation"]


def test_no_index_is_an_empty_answer(monkeypatch) -> None:
    _stub_model(monkeypatch, {"picks": []})
    assert discovery.choose_indexes(discovery.find_country("SG"), _entries("https://x.gov/news")) == []


def test_an_empty_inventory_never_reaches_the_model(monkeypatch) -> None:
    def explode(**_kwargs):
        raise AssertionError("the model must not be asked about an empty page")

    monkeypatch.setattr("app.core.extraction.llm.generate_structured", explode)
    assert discovery.choose_indexes(discovery.find_country("SG"), []) == []


def test_picks_are_capped(monkeypatch) -> None:
    inventory = _entries(*[f"https://x.gov/legislation/{i}" for i in range(6)])
    _stub_model(monkeypatch, {"picks": [{"url": e.link, "reason": "r"} for e in inventory]})
    picked = discovery.choose_indexes(discovery.find_country("SG"), inventory)
    assert len(picked) == discovery.MAX_CANDIDATES


def test_inventory_handed_to_the_model_is_capped(monkeypatch) -> None:
    """The free tier that makes Gemma free caps input at 16,000 tokens/minute.

    Measured: a 220-link inventory returns RESOURCE_EXHAUSTED. The cap is not
    tidiness, it is the difference between a working call and a 429.
    """
    seen: dict = {}

    def capture(**kwargs):
        seen["links"] = json.loads(kwargs["contents"])["links"]
        return json.dumps({"picks": []})

    monkeypatch.setattr("app.core.extraction.llm.generate_structured", capture)
    inventory = _entries(*[f"https://x.gov/p/{i}" for i in range(300)])
    discovery.choose_indexes(discovery.find_country("SG"), inventory)
    assert len(seen["links"]) == discovery.MAX_INVENTORY_LINKS


# ---------------------------------------------------------------------------
# Hop 3 — the pattern is derived, never asked for
# ---------------------------------------------------------------------------


def test_pattern_generalises_document_ids() -> None:
    """The BPOM shape: `/download/rule/<n>/<title>` is a family, and the number
    is the only part that varies."""
    links = _entries(
        "https://jdih.pom.go.id/download/rule/101/peraturan-a",
        "https://jdih.pom.go.id/download/rule/102/peraturan-b",
        "https://jdih.pom.go.id/download/rule/103/peraturan-c",
        "https://jdih.pom.go.id/tentang-kami",
    )
    pattern, count, samples = discovery.derive_pattern(links)
    assert count == 3
    assert len(samples) == 3

    import re

    compiled = re.compile(pattern)
    assert compiled.search("https://jdih.pom.go.id/download/rule/999/peraturan-baru")
    assert not compiled.search("https://jdih.pom.go.id/tentang-kami")


def test_a_page_of_navigation_is_refused() -> None:
    """Two links that rhyme are a coincidence, not a document family. Committing
    this source would point the nightly sweep at a menu."""
    links = _entries("https://x.gov/about", "https://x.gov/contact")
    with pytest.raises(discovery.DiscoveryError) as exc:
        discovery.derive_pattern(links)
    assert "shape" in str(exc.value)


def test_an_empty_page_says_so() -> None:
    with pytest.raises(discovery.DiscoveryError) as exc:
        discovery.derive_pattern([])
    assert "no links" in str(exc.value)


def test_verify_refuses_plain_http(monkeypatch) -> None:
    candidate = discovery.CandidateSource(url="http://x.gov/legislation", label="x", reason="r")
    with pytest.raises(discovery.DiscoveryError) as exc:
        discovery.verify_candidate(candidate)
    assert "https" in str(exc.value)


# ---------------------------------------------------------------------------
# The whole run
# ---------------------------------------------------------------------------


def _run(monkeypatch, *, root, inventory, index_links, picks=None):
    """Drive `run_discovery` with a stubbed model and fetcher."""
    monkeypatch.setattr(
        discovery, "propose_root", lambda _c: discovery.RootProposal("Reg", root) if root else None
    )
    monkeypatch.setattr(
        discovery,
        "link_inventory",
        lambda url, timeout=None: index_links if url != root else inventory,
    )
    if picks is not None:
        monkeypatch.setattr(discovery, "choose_indexes", lambda _c, _i: picks)
    country = discovery.find_country("SG")
    return discovery.run_discovery("SG", discovery.new_job(country, "trace"))


def test_a_run_that_commits(monkeypatch) -> None:
    committed: list = []
    monkeypatch.setattr(
        discovery,
        "commit_verified",
        lambda country, regulator, verified: (committed.append(verified) or ("src_1", True)),
    )
    job = _run(
        monkeypatch,
        root="https://www.sfa.gov.sg",
        inventory=_entries("https://www.sfa.gov.sg/legislation"),
        index_links=_entries(
            "https://www.sfa.gov.sg/legislation/act/1",
            "https://www.sfa.gov.sg/legislation/act/2",
            "https://www.sfa.gov.sg/legislation/act/3",
        ),
        picks=[
            discovery.CandidateSource(
                url="https://www.sfa.gov.sg/legislation", label="SG index", reason="r"
            )
        ],
    )
    assert job["status"] == "done"
    assert job["committed"] == 1
    assert job["candidates"][0]["source_id"] == "src_1"
    assert job["candidates"][0]["match_count"] == 3
    assert committed[0].kind is SourceKind.LISTING


def test_an_unreadable_regulator_site_is_a_result_not_a_crash(monkeypatch) -> None:
    """moh.gov.my answered 403 and fssai.gov.in timed out, both measured.

    A government site that refuses robots is the ordinary case, and it must
    produce a sentence a user reads rather than an exception Pub/Sub retries
    four more times at two model calls apiece.
    """

    def refuse(url, timeout=None):
        raise FetchError("The source answered 403.")

    monkeypatch.setattr(
        discovery, "propose_root", lambda _c: discovery.RootProposal("MOH", "https://moh.gov.my")
    )
    monkeypatch.setattr(discovery, "link_inventory", refuse)
    job = discovery.run_discovery("MY", discovery.new_job(discovery.find_country("MY"), "t"))
    assert job["status"] == "failed"
    assert "403" in job["error"]
    assert "moh.gov.my" in job["error"]


def test_a_javascript_site_says_what_is_wrong(monkeypatch) -> None:
    """fda.ph answered 200 with zero anchors. "No links" is the true reason and
    the user is told it, rather than being shown an empty success."""
    job = _run(monkeypatch, root="https://www.fda.ph", inventory=[], index_links=[])
    assert job["status"] == "failed"
    assert "rendered in the browser" in job["error"]


def test_a_country_with_no_known_regulator_is_named(monkeypatch) -> None:
    job = _run(monkeypatch, root=None, inventory=[], index_links=[])
    assert job["status"] == "failed"
    assert "Singapore" in job["error"]


def test_an_index_that_cannot_be_read_is_rejected_with_its_reason(monkeypatch) -> None:
    job = _run(
        monkeypatch,
        root="https://www.sfa.gov.sg",
        inventory=_entries("https://www.sfa.gov.sg/legislation"),
        index_links=_entries("https://www.sfa.gov.sg/about"),
        picks=[
            discovery.CandidateSource(
                url="https://www.sfa.gov.sg/legislation", label="SG", reason="r"
            )
        ],
    )
    assert job["status"] == "failed"
    assert job["candidates"][0]["status"] == "rejected"
    assert job["candidates"][0]["error"]
    assert job["committed"] == 0


def test_an_unknown_country_code_fails_cleanly() -> None:
    job = discovery.run_discovery("ZZ", {"status": "queued"})
    assert job["status"] == "failed"
    assert "ZZ" in job["error"]


# ---------------------------------------------------------------------------
# The market, without which none of this is visible
# ---------------------------------------------------------------------------


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _FakeRef:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def get(self):
        return _FakeSnapshot(self.store.get(self.key))

    def set(self, record, merge=False):
        self.store[self.key] = {**(self.store.get(self.key) or {}), **record} if merge else record


class _FakeCollection:
    def __init__(self, store):
        self.store = store

    def document(self, key):
        return _FakeRef(self.store, key)


class _FakeDb:
    def __init__(self, store):
        self.store = store

    def collection(self, _name):
        return _FakeCollection(self.store)


def test_a_discovered_country_gets_a_market(monkeypatch) -> None:
    """`impact.evaluate` skips any clause whose jurisdiction no market lists.

    Without this the feature commits a source, ingests its regulations
    perfectly, and produces no verdict anywhere: a green row and silence.
    """
    from app.core import markets

    store: dict = {}
    monkeypatch.setattr(markets, "get_db", lambda: _FakeDb(store))
    market_id, created = markets.ensure_market(
        country_code="jp", country_name="Japan", regulator="MHLW"
    )
    assert (market_id, created) == ("market_jp", True)
    assert store["market_jp"]["jurisdictions"] == ["JP"]
    assert store["market_jp"]["country_code"] == "JP"


def test_ensuring_a_market_twice_changes_nothing(monkeypatch) -> None:
    from app.core import markets

    store: dict = {}
    monkeypatch.setattr(markets, "get_db", lambda: _FakeDb(store))
    markets.ensure_market(country_code="JP", country_name="Japan", regulator="MHLW")
    _, created = markets.ensure_market(country_code="JP", country_name="Japan", regulator="MHLW")
    assert created is False
    assert store["market_jp"]["jurisdictions"] == ["JP"]


def test_a_seeded_market_keeps_the_regime_it_shipped_with(monkeypatch) -> None:
    """Indonesia ships as `jurisdictions: ["ID_BPOM"]`. Discovering ID must add
    to that list, not replace it — the BPOM clauses already in the graph are
    matched through it."""
    from app.core import markets

    store = {
        "market_id": {
            "country": "Indonesia",
            "country_code": "ID",
            "jurisdictions": ["ID_BPOM"],
            "label": "Indonesia — BPOM",
            "regulator": "Badan Pengawas Obat dan Makanan",
        }
    }
    monkeypatch.setattr(markets, "get_db", lambda: _FakeDb(store))
    markets.ensure_market(country_code="ID", country_name="Indonesia", regulator="Something else")
    assert store["market_id"]["jurisdictions"] == ["ID_BPOM", "ID"]
    assert store["market_id"]["label"] == "Indonesia — BPOM"
    assert store["market_id"]["regulator"] == "Badan Pengawas Obat dan Makanan"


def test_commit_registers_the_market_before_the_source(monkeypatch) -> None:
    order: list = []
    monkeypatch.setattr(
        "app.core.markets.ensure_market",
        lambda **kwargs: order.append(("market", kwargs["country_code"])) or ("market_sg", True),
    )

    class _Source:
        id = "src_9"

    monkeypatch.setattr(
        "app.core.sources.add_source",
        lambda meta: order.append(("source", meta.jurisdiction, meta.link_pattern)) or (_Source(), True),
    )
    verified = discovery.VerifiedSource(
        url="https://www.sfa.gov.sg/legislation",
        label="SG",
        reason="r",
        link_pattern="/legislation",
        match_count=4,
    )
    source_id, created = discovery.commit_verified(
        discovery.find_country("SG"), "Singapore Food Agency", verified
    )
    assert (source_id, created) == ("src_9", True)
    assert order == [("market", "SG"), ("source", "SG", "/legislation")]


# ---------------------------------------------------------------------------
# Errors out of the SDK
# ---------------------------------------------------------------------------


def _raise_from_model(monkeypatch, message: str) -> None:
    def boom(**_kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr("app.core.extraction.llm.generate_structured", boom)


def test_an_exhausted_quota_is_worth_retrying(monkeypatch) -> None:
    """The free tier refills within the minute, so this one earns a redelivery."""
    _raise_from_model(monkeypatch, "429 RESOURCE_EXHAUSTED. quota exceeded")
    with pytest.raises(discovery.TransientDiscoveryError):
        discovery.propose_root(discovery.find_country("JP"))


def test_gemma_missing_from_vertex_is_named(monkeypatch) -> None:
    """What a deployment with no Gemini API key looks like from in here: Gemma
    is a Developer API model and Vertex does not serve it."""
    _raise_from_model(
        monkeypatch, "404 NOT_FOUND. Publisher model .../gemma-4-31b-it was not found"
    )
    with pytest.raises(discovery.DiscoveryError) as exc:
        discovery.propose_root(discovery.find_country("JP"))
    assert "Gemini API key" in str(exc.value)


def test_any_other_model_error_stays_inside_the_module(monkeypatch) -> None:
    """Uncaught, an SDK error reaches the worker as a 500 and Pub/Sub retries the
    same failing country five times at two model calls apiece."""
    _raise_from_model(monkeypatch, "500 INTERNAL")
    with pytest.raises(discovery.DiscoveryError):
        discovery.propose_root(discovery.find_country("JP"))


def test_a_model_failure_becomes_a_recorded_result(monkeypatch) -> None:
    monkeypatch.setattr(
        discovery, "propose_root", lambda _c: (_ for _ in ()).throw(discovery.DiscoveryError("nope"))
    )
    job = discovery.run_discovery("SG", discovery.new_job(discovery.find_country("SG"), "t"))
    assert job["status"] == "failed"
    assert job["error"] == "nope"
    assert job["finished_at"]


def test_two_index_pages_reaching_the_same_documents_commit_once(monkeypatch) -> None:
    """Singapore's `/legislation` and `/regulatory-standards-...` both lead to
    the food-safety-limits family. Watching both would fetch and ingest the same
    regulations twice every night."""
    monkeypatch.setattr(
        discovery, "propose_root", lambda _c: discovery.RootProposal("SFA", "https://x.gov")
    )
    same = _entries(
        "https://x.gov/limits/additives",
        "https://x.gov/limits/colours",
        "https://x.gov/limits/sweeteners",
    )
    monkeypatch.setattr(discovery, "link_inventory", lambda url, timeout=None: same)
    monkeypatch.setattr(
        discovery,
        "choose_indexes",
        lambda _c, _i: [
            discovery.CandidateSource(url="https://x.gov/a", label="a", reason="r"),
            discovery.CandidateSource(url="https://x.gov/b", label="b", reason="r"),
        ],
    )
    monkeypatch.setattr(discovery, "commit_verified", lambda *_a: ("src_1", True))
    job = discovery.run_discovery("SG", discovery.new_job(discovery.find_country("SG"), "t"))
    assert job["committed"] == 1
    assert job["status"] == "partial"
    assert job["candidates"][1]["status"] == "rejected"
    assert "same documents" in job["candidates"][1]["error"]


def test_a_shallow_index_still_forms_a_family() -> None:
    """`/legislation/<act-name>` is a family even though nothing in it is a
    number. Grouping only at two segments gave every act its own cluster and
    refused the index."""
    links = _entries(
        "https://x.gov/legislation/food-act",
        "https://x.gov/legislation/hygiene-act",
        "https://x.gov/legislation/additives-order",
        "https://x.gov/contact",
    )
    pattern, count, _ = discovery.derive_pattern(links)
    assert count == 3

    import re

    assert re.search(pattern, "https://x.gov/legislation/new-act-2027")
    assert not re.search(pattern, "https://x.gov/contact")


def test_a_group_that_swallows_the_page_is_navigation() -> None:
    """Measured on `mhlw.go.jp/shokanhourei`: 55 links under
    `/stf/seisakunitsuite` — every policy area the ministry runs, from pensions
    to long-term care. Committing it points the nightly sweep at a ministry."""
    links = _entries(*[f"https://x.gov/stf/policy/area-{i}" for i in range(50)])
    with pytest.raises(discovery.DiscoveryError) as exc:
        discovery.derive_pattern(links)
    assert "navigation" in str(exc.value)


def test_a_family_that_names_nothing_regulatory_is_refused() -> None:
    links = _entries(*[f"https://x.gov/media/photo-{i}" for i in range(5)])
    with pytest.raises(discovery.DiscoveryError) as exc:
        discovery.derive_pattern(links)
    assert "names a regulation" in str(exc.value)


def test_hyphenated_paths_read_as_words() -> None:
    """`food-safety-regulatory-limits` has to match the phrase it spells, or the
    on-topic cluster loses to whichever one is larger."""
    links = _entries(
        "https://x.gov/limits/food-safety-regulatory-limits/additives",
        "https://x.gov/limits/food-safety-regulatory-limits/colours",
        "https://x.gov/limits/food-safety-regulatory-limits/sweeteners",
    )
    pattern, count, _ = discovery.derive_pattern(links)
    assert count == 3


def test_a_contact_page_is_not_a_legislation_index() -> None:
    """`act\\b` matched inside "cont-act-us", and the local drill duly committed
    `sfa.gov.sg/contact-us` as Singapore's regulations index."""
    assert discovery._INDEX_HINTS.search("https://x.gov/legislation/food-act")
    assert not discovery._INDEX_HINTS.search("https://www.sfa.gov.sg/contact-us")


def test_a_market_carries_the_field_it_is_ordered_by(monkeypatch) -> None:
    """`list_markets` orders by `id`, and Firestore omits documents missing the
    ordered field. A market written without it exists and is invisible — the
    same silence `ensure_market` was added to prevent."""
    from app.core import markets

    store: dict = {}
    monkeypatch.setattr(markets, "get_db", lambda: _FakeDb(store))
    market_id, _ = markets.ensure_market(
        country_code="SG", country_name="Singapore", regulator="SFA"
    )
    assert store[market_id]["id"] == market_id


# ---------------------------------------------------------------------------
# Which key discovery uses
# ---------------------------------------------------------------------------


def test_discovery_key_ignores_the_production_placeholder(monkeypatch) -> None:
    """Production ships `gemini-api-key` as `YOUR_KEY_HERE` on purpose, to force
    the Vertex path. Treating it as a credential would make every discovery run
    fail on authentication instead of saying it is not configured."""
    from app.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "discovery_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", "YOUR_KEY_HERE")
    assert settings.discovery_key is None
    assert settings.discovery_available is False


def test_discovery_uses_its_own_key_without_moving_the_rest_of_the_app(monkeypatch) -> None:
    """The whole reason for a second key: Developer API embeddings are not
    comparable with Vertex embeddings, so reusing GEMINI_API_KEY to enable
    discovery would silently stop every stored clause from matching."""
    from app.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "discovery_api_key", "A" * 40)
    monkeypatch.setattr(settings, "gemini_api_key", "YOUR_KEY_HERE")
    assert settings.discovery_key == "A" * 40
    assert settings.discovery_available is True
    # The app-wide switch stays where it was: still Vertex.
    assert settings.use_gemini_api is False


def test_the_discovery_call_is_handed_that_key(monkeypatch) -> None:
    seen: dict = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return json.dumps({"regulator": "X", "root_url": "https://x.gov"})

    monkeypatch.setattr("app.core.extraction.llm.generate_structured", capture)
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "discovery_api_key", "B" * 40)
    discovery.propose_root(discovery.find_country("JP"))
    assert seen["api_key"] == "B" * 40
    assert seen["model"] == get_settings().discovery_model
