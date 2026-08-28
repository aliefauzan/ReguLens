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


_VERDICTS = ("supersedes", "conflicts", "distinct_scope", "ambiguous")


async def run_judge_agent(a: dict, b: dict) -> dict | None:
    """Run the agent over one pair and return its verdict, or None.

    Called from `reconciliation.judge_ambiguous_pair`, which is reached only for
    a pair the deterministic classification could not settle — same
    jurisdiction, dates that do not decide. Everything else never gets here, so
    the agent costs nothing on the path a normal document takes.

    Returning None rather than guessing is the point: the caller falls back to
    the direct judge call, and typed code still owns the mutation either way.
    """
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=build_reconciliation_agent(), app_name="regulens")
    session = await runner.session_service.create_session(
        app_name="regulens", user_id="reconciler"
    )
    prompt = (
        "Decide the relationship between these two clauses. Check comparability "
        "first, then classify, and only judge if the classification is ambiguous. "
        "Answer with one word from "
        f"{', '.join(_VERDICTS)} and one sentence of rationale.\n\n"
        f"Clause A: {_describe(a)}\n\nClause B: {_describe(b)}"
    )

    parts: list[str] = []
    judged: dict | None = None
    tool_calls: list[str] = []
    async for event in runner.run_async(
        user_id="reconciler",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        content = getattr(event, "content", None)
        for part in getattr(content, "parts", None) or []:
            call = getattr(part, "function_call", None)
            if call is not None:
                tool_calls.append(call.name)
            response = getattr(part, "function_response", None)
            if response is not None and getattr(response, "name", "") == "judge_ambiguous_pair_tool":
                payload = getattr(response, "response", None)
                if isinstance(payload, dict) and payload.get("verdict") in _VERDICTS:
                    judged = {
                        "verdict": payload["verdict"],
                        "rationale": str(payload.get("rationale", ""))[:300],
                    }
            if getattr(part, "text", None):
                parts.append(part.text)

    if judged is None:
        # The agent settled it without the judge tool — read its own word, and
        # only a word from the enum.
        spoken = " ".join(parts).lower()
        for verdict in _VERDICTS:
            if verdict in spoken:
                judged = {"verdict": verdict, "rationale": " ".join(parts).strip()[:300]}
                break

    log(
        logger, logging.INFO, "judge agent complete",
        tool_calls=tool_calls, verdict=(judged or {}).get("verdict"),
    )
    return judged


def _describe(clause: dict) -> str:
    return (
        f"{clause.get('text')}\n(id={clause.get('id')}, substance={clause.get('substance')}, "
        f"limit={clause.get('limit_value')} {clause.get('unit')}, "
        f"jurisdiction={clause.get('jurisdiction')}, effective={clause.get('effective_date')}, "
        f"document={clause.get('document_id')})"
    )


def run_reconciliation(clause_id: str) -> dict:
    """The demo path calls the plain pipeline directly — the ADK agent advises
    on the one ambiguous decision and never owns a mutation. See
    01-architecture.md rule 1."""
    from app.core.reconciliation import reconcile_clause

    result = reconcile_clause(clause_id)
    log(logger, logging.INFO, "reconciliation complete", clause_id=clause_id, **result)
    return result
