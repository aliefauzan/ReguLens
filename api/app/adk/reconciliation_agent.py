"""ADK Reconciliation Agent — thin wrapper over plain tool bodies.

The tool order IS the architecture: `find_similar_clauses` → `check_comparability`
→ `classify_relationship` → `judge_ambiguous_pair`. The judge tool's input is the
comparability tool's output, so the agent cannot reach the judge without passing
the guardrail — enforced by types, not by prompt instructions.
"""

from __future__ import annotations

import logging

from app.core.guardrail import comparability
from app.observability import log

logger = logging.getLogger(__name__)

RECONCILIATION_AGENT_NAME = "regulens_reconciliation"

_INSTRUCTION = """You are ReguLens's reconciliation engine. For a newly extracted
clause you decide its relationship to existing knowledge, in strict order:

1. find_similar_clauses(clause_id) — retrieval, deterministic.
2. For each candidate: check_comparability(a, b) — the guardrail. Pairs it
   rejects are final; you may not send them onward.
3. classify_relationship(a, b, value_a, value_b) — deterministic classification.
4. Only a genuinely ambiguous comparable pair reaches judge_ambiguous_pair(a, b).

You never write to the database. You return verdicts; typed code decides."""


def find_similar_clauses_tool(clause_id: str) -> dict:
    from app.core.reconciliation import find_similar
    from app.db import get_db

    snapshot = get_db().collection("clauses").document(clause_id).get()
    if not snapshot.exists:
        return {"found": False, "candidates": []}
    clause = snapshot.to_dict() | {"id": snapshot.id}
    return {
        "found": True,
        "candidates": [{"id": c["id"], "text": (c.get("text") or "")[:400]} for c in find_similar(clause)],
    }


def check_comparability_tool(a: dict, b: dict) -> dict:
    guard = comparability(a, b)
    from app.core.guardrail import ComparablePair

    if isinstance(guard, ComparablePair):
        return {"comparable": True, "value_a": guard.value_a, "value_b": guard.value_b,
                "basis_unit": guard.basis_unit}
    return {"comparable": False, "reason": guard.reason}


def classify_relationship_tool(a: dict, b: dict, value_a: float, value_b: float) -> dict:
    from app.core.guardrail import relationship_class

    cls = relationship_class(a, b, values=(value_a, value_b))
    return {"relationship": cls}


def judge_ambiguous_pair_tool(a: dict, b: dict) -> dict:
    from app.core.reconciliation import judge_pair

    return judge_pair(a, b)


def build_reconciliation_agent():
    from google.adk.agents import Agent

    from app.settings import get_settings

    return Agent(
        name=RECONCILIATION_AGENT_NAME,
        model=get_settings().gemini_model,
        instruction=_INSTRUCTION,
        tools=[
            find_similar_clauses_tool,
            check_comparability_tool,
            classify_relationship_tool,
            judge_ambiguous_pair_tool,
        ],
    )


def run_reconciliation(clause_id: str) -> dict:
    """The demo path calls the plain pipeline directly — the ADK agent is the
    wrapper, not a dependency of correctness. See 01-architecture.md rule 1."""
    from app.core.reconciliation import reconcile_clause

    result = reconcile_clause(clause_id)
    log(logger, logging.INFO, "reconciliation complete", clause_id=clause_id, **result)
    return result
