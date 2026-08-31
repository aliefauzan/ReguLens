"""The query path may not present an ungrounded answer as a grounded one.

Wiring the ADK Query Agent in broke exactly this, and the deployed E2E caught
it: asked about a country with no ingested regulation, the agent wrote "there is
no information available" **and cited the clauses it had looked at anyway**, so
the answer came back with `refusal: false` and a stack of citation cards under a
sentence saying there was nothing. These tests pin the two halves of the fix.
"""

from __future__ import annotations

from app.core import query


def _bundle(*ids: str) -> dict:
    return {
        "clauses": [{"id": i, "text": f"text of {i}"} for i in ids],
        "requirements": [],
        "conflicts": [],
    }


def test_citations_must_name_a_clause_this_process_read():
    bundle = _bundle("clause_aaa", "clause_bbb")
    assert query._validate_citations("see [clause_aaa]", bundle) == ["clause_aaa"]
    assert query._validate_citations("see [clause_zzz]", bundle) == []


def test_agent_served_ids_count_as_evidence():
    """The agent chooses its own retrieval, so the ids its tools read are as real
    as the pre-retrieved bundle — this process fetched them from Firestore."""
    bundle = _bundle("clause_aaa")
    assert query._validate_citations("see [clause_ccc]", bundle) == []
    assert query._validate_citations(
        "see [clause_ccc]", bundle, extra_ids={"clause_ccc"}
    ) == ["clause_ccc"]


def test_an_invented_id_is_never_evidence_even_with_served_ids():
    bundle = _bundle("clause_aaa")
    assert query._validate_citations(
        "see [clause_made_up]", bundle, extra_ids={"clause_ccc"}
    ) == []


def test_insufficient_marker_yields_no_citations(monkeypatch):
    """The regression. The agent declaring emptiness must reach the caller as
    zero citations — which is what `refusal` is computed from — no matter what
    ids its tools happened to serve on the way."""
    from app.adk import query_agent

    seen = {}

    async def fake_run(question, product_id, evidence=None):
        seen["evidence"] = evidence
        return (query_agent.INSUFFICIENT, ["clause_aaa", "clause_bbb"])

    monkeypatch.setattr(query_agent, "run_query_agent", fake_run)

    answer, cited = query._synthesize_via_agent(
        "What are the Japan requirements?", _bundle("clause_aaa"), None
    )
    assert cited == [], "an insufficient answer must never arrive with citations"
    assert answer == ""
    # And prove the call actually reached the fake rather than raising on its
    # way in: a TypeError here would be swallowed by the fallback and the
    # assertions above would pass for the wrong reason.
    assert seen["evidence"] == [{"id": "clause_aaa", "text": "text of clause_aaa"}]


def test_agent_failure_falls_through_rather_than_answering(monkeypatch):
    from app.adk import query_agent

    async def boom(question, product_id, evidence=None):
        raise RuntimeError("agent unavailable")

    monkeypatch.setattr(query_agent, "run_query_agent", boom)

    assert query._synthesize_via_agent("why?", _bundle("clause_aaa"), None) == ("", [])


# ---------------------------------------------------------------------------
# Retrieval hints: what the question named


class TestSubstanceHint:
    """The hint decides whether retrieval filters by substance family at all.

    The previous matcher fed whole runs of letters and spaces to the strict
    normalizer, so "what is the nitrite limit for cured meat in germany" was
    offered as a substance name, matched nothing, and every question fell back
    to embedding rank alone.
    """

    def test_a_substance_inside_a_sentence_is_found(self):
        from app.core.query import _substance_of

        assert _substance_of("What is the nitrite limit for cured meat in Germany?") == (
            "nitrites"
        )

    def test_a_two_word_name_is_found(self):
        """The dictionary holds both shapes; the scan has to try both."""
        from app.core.query import _substance_of

        assert _substance_of("how much sodium benzoate may I use") == "sodium_benzoate"

    def test_a_question_naming_no_substance_says_so(self):
        from app.core.query import _substance_of

        assert _substance_of("what changed last week") is None


class TestJurisdictionHint:
    """A question that names a market retrieves that market's rules."""

    def _markets(self, monkeypatch, rows):
        from app.core import markets as markets_core

        monkeypatch.setattr(markets_core, "list_markets", lambda: rows)

    def test_a_country_name_resolves_to_its_jurisdiction(self, monkeypatch):
        from app.core.query import _jurisdictions_of

        self._markets(monkeypatch, [
            {"id": "market_de", "country": "Germany", "jurisdictions": ["EU"]},
            {"id": "market_id", "country": "Indonesia", "jurisdictions": ["ID_BPOM"]},
        ])
        assert _jurisdictions_of("nitrite limit for cured meat in Germany") == ["EU"]

    def test_a_regulator_name_resolves_too(self, monkeypatch):
        from app.core.query import _jurisdictions_of

        self._markets(monkeypatch, [
            {"id": "market_id", "country": "Indonesia", "regulator": "BPOM",
             "jurisdictions": ["ID_BPOM"]},
        ])
        assert _jurisdictions_of("what does BPOM allow") == ["ID_BPOM"]

    def test_a_question_naming_no_market_names_no_jurisdiction(self, monkeypatch):
        from app.core.query import _jurisdictions_of

        self._markets(monkeypatch, [
            {"id": "market_de", "country": "Germany", "jurisdictions": ["EU"]},
        ])
        assert _jurisdictions_of("how much sodium benzoate is allowed") == []

    def test_the_list_comes_from_stored_markets_not_a_table_here(self, monkeypatch):
        """A market added by country discovery has to be answerable the day it
        is added."""
        from app.core.query import _jurisdictions_of

        self._markets(monkeypatch, [
            {"id": "market_jp", "country": "Japan", "jurisdictions": ["JP_MHLW"]},
        ])
        assert _jurisdictions_of("additive rules in Japan") == ["JP_MHLW"]


class _EmptyQuery:
    """Firestore stand-in: these tests are about retrieval inputs, not storage."""

    def collection(self, _name):
        return self

    def where(self, **_kwargs):
        return self

    def limit(self, _n):
        return self

    def order_by(self, *_a, **_k):
        return self

    def document(self, _id):
        return self

    def get(self):
        return self

    @property
    def exists(self):
        return False

    def stream(self):
        return iter(())


def _no_firestore():
    return _EmptyQuery()


def test_the_question_is_embedded_before_similarity_ranking(monkeypatch) -> None:
    """Otherwise `find_similar` scores every candidate -1.0, they all tie, and
    the sort returns whichever five Firestore listed first — retrieval by
    listing order wearing the name of similarity. Measured on the deployed
    corpus: one substance answered with five citations and another refused,
    though both were held."""
    from app.core import query as query_module

    seen: dict = {}

    def fake_embed(texts):
        seen["texts"] = texts
        return [[0.5] * 8 for _ in texts]

    def fake_find_similar(clause, k=5):
        seen["clause"] = clause
        return []

    monkeypatch.setattr("app.core.reconciliation.embed_texts", fake_embed)
    monkeypatch.setattr(query_module, "find_similar", fake_find_similar)
    monkeypatch.setattr(query_module, "get_db", _no_firestore)
    monkeypatch.setattr("app.db.get_db", _no_firestore)
    monkeypatch.setattr(query_module, "_clauses_in", lambda *_a, **_k: [])
    monkeypatch.setattr(query_module, "_jurisdictions_of", lambda *_a, **_k: [])
    query_module._retrieve("limits for benzoic acid?", None)

    assert seen["texts"] == ["limits for benzoic acid?"]
    assert seen["clause"]["embedding"] == [0.5] * 8


def test_retrieval_survives_an_embedding_failure(monkeypatch) -> None:
    """A quota failure must degrade to the substance filter, not be mistaken for
    a corpus that holds nothing."""
    from app.core import query as query_module

    def boom(_texts):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    seen: dict = {}

    def fake_find_similar(clause, k=5):
        seen["clause"] = clause
        return []

    monkeypatch.setattr("app.core.reconciliation.embed_texts", boom)
    monkeypatch.setattr(query_module, "find_similar", fake_find_similar)
    monkeypatch.setattr(query_module, "get_db", _no_firestore)
    monkeypatch.setattr("app.db.get_db", _no_firestore)
    monkeypatch.setattr(query_module, "_clauses_in", lambda *_a, **_k: [])
    monkeypatch.setattr(query_module, "_jurisdictions_of", lambda *_a, **_k: [])
    query_module._retrieve("limits for benzoic acid?", None)

    assert "embedding" not in seen["clause"]
    assert seen["clause"]["substance_normalized"] == "benzoic_acid"
