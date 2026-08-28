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

    async def fake_run(question, product_id):
        return (query_agent.INSUFFICIENT, ["clause_aaa", "clause_bbb"])

    monkeypatch.setattr(query_agent, "run_query_agent", fake_run)

    answer, cited = query._synthesize_via_agent(
        "What are the Japan requirements?", _bundle("clause_aaa"), None
    )
    assert cited == [], "an insufficient answer must never arrive with citations"
    assert answer == ""


def test_agent_failure_falls_through_rather_than_answering(monkeypatch):
    from app.adk import query_agent

    async def boom(question, product_id):
        raise RuntimeError("agent unavailable")

    monkeypatch.setattr(query_agent, "run_query_agent", boom)

    assert query._synthesize_via_agent("why?", _bundle("clause_aaa"), None) == ("", [])
