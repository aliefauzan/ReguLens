"""ADK Query Agent — the one agent that genuinely needs tool selection.

Tools are the retrieval functions from `core/`; the agent decides which to call
for an open-ended question. Grounding validation stays in `core/query.py` — the
agent proposes answers; typed code decides what may be returned to a user.

Every id a tool hands the agent is recorded on the way past. That record is what
the answer's citations are checked against, so a cited clause is one this process
actually read out of Firestore — grounding by construction rather than by
instruction, which is the only kind an instruction-following model cannot talk
its way around.
"""

from __future__ import annotations

import contextvars
import logging

from app.observability import log

logger = logging.getLogger(__name__)

# Ids served to the agent during one run. A ContextVar rather than a global:
# the worker and the API both run several requests at once, and one question's
# evidence must never validate another question's answer.
_served: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "regulens_query_served", default=None
)


# Searches already made during this run, keyed on the normalised query.
_searches: contextvars.ContextVar[dict[str, list[dict]] | None] = contextvars.ContextVar(
    "regulens_query_searches", default=None
)


def _serve(ids: list[str]) -> None:
    bucket = _served.get()
    if bucket is not None:
        bucket.extend(ids)

QUERY_AGENT_NAME = "regulens_query"

_INSTRUCTION = """You are ReguLens's compliance query agent. Answer the user's
question about their product and ingested regulations. Use the retrieval tools
to ground every claim:

- get_product_compliance(product_id) — current requirements and evaluations
- find_clauses(query) — clause search over ingested regulations
- get_events(entity_id) — what changed and when
- get_conflicts() — open cross-jurisdiction conflicts

Be economical. Two searches is almost always enough: rephrasing the same
question retrieves the same clauses, and every extra call is time the user
spends watching a spinner. When you have what you need, answer.

Cite stored clause IDs inline as [clause_id]. Never answer a compliance
question from general knowledge.

If the tools return nothing that actually covers what was asked — a country we
hold no regulation for, a substance nobody has ingested a rule about — reply
with exactly:

INSUFFICIENT_EVIDENCE

and nothing else. No explanation, no citations, no near-misses. A clause about
a different country is not evidence about this one, and citing it while saying
you have nothing is worse than saying nothing: it is an answer the system will
present as grounded."""

# The agent's own word for "I have nothing". It exists because a model that
# explains its own emptiness in prose will still cite the clauses it looked at,
# and an answer carrying citations is one the UI presents as grounded. A single
# token the agent either emits or does not is checkable; a sentence is not.
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


def get_product_compliance_tool(product_id: str) -> dict:
    from google.cloud import firestore

    from app.core.impact import rollup_status
    from app.db import get_db

    reqs = [
        d.to_dict() | {"id": d.id}
        for d in (
            get_db()
            .collection("requirements")
            .where(filter=firestore.FieldFilter("product_id", "==", product_id))
            .limit(50)
            .stream()
        )
    ]
    _serve([str(r.get("clause_id")) for r in reqs if r.get("clause_id")])
    return {"requirements": reqs[:20], "statuses": rollup_status(product_id)}


def find_clauses_tool(query: str, k: int = 5) -> dict:
    """Clause search. Repeated searches within one run are answered from the
    first result.

    Every call embeds the query and scans Firestore, and the agent likes to
    rephrase and search again: a measured question spent 42 seconds making five
    of these. Rephrasings of the same question retrieve the same clauses, so
    remembering the run's searches costs nothing and saves a round trip each
    time."""
    from app.core.query import _retrieve

    cache = _searches.get()
    key = " ".join(query.lower().split())
    if cache is not None and key in cache:
        _serve([c["id"] for c in cache[key]])
        return {"clauses": cache[key], "repeat": True}

    bundle = _retrieve(query, None)
    clauses = [{"id": c["id"], "text": str(c.get("text"))[:300]} for c in bundle["clauses"]]
    if cache is not None:
        cache[key] = clauses
    _serve([c["id"] for c in bundle["clauses"]])
    return {"clauses": clauses}


def get_events_tool(entity_id: str) -> dict:
    from app.core.repository import events_for

    return {"events": events_for(entity_id, limit=20)}


def get_conflicts_tool() -> dict:
    from google.cloud import firestore

    from app.db import get_db

    docs = (
        get_db()
        .collection("conflicts")
        .where(filter=firestore.FieldFilter("status", "==", "open"))
        .limit(20)
        .stream()
    )
    conflicts = [d.to_dict() | {"id": d.id} for d in docs]
    for conflict in conflicts:
        _serve([str(conflict[k]) for k in ("clause_a", "clause_b") if conflict.get(k)])
    return {"conflicts": conflicts}


def build_query_agent():
    from google.adk.agents import Agent

    from app.settings import get_settings

    return Agent(
        name=QUERY_AGENT_NAME,
        model=get_settings().gemini_model,
        instruction=_INSTRUCTION,
        tools=[
            get_product_compliance_tool,
            find_clauses_tool,
            get_events_tool,
            get_conflicts_tool,
        ],
    )


def _evidence_block(clauses: list[dict]) -> str:
    """What the caller already retrieved, handed to the agent up front.

    The agent used to start with nothing and had to search before it could say
    anything, which made every question at least two model turns plus an
    embedding call — measured at 42s, then 31s once repeat searches were cached.
    The caller has already run retrieval by the time it gets here, so withholding
    that was paying for the same clauses twice. The tools remain available for
    when this is not enough; they are simply no longer compulsory.
    """
    if not clauses:
        return ""
    lines = [
        f"[{c['id']}] ({c.get('jurisdiction') or 'unknown jurisdiction'}) "
        f"{str(c.get('text'))[:300]}"
        for c in clauses[:8]
    ]
    return (
        "\n\nEvidence already retrieved for this question. Cite from it directly "
        "when it answers the question; search only if it does not:\n" + "\n".join(lines)
    )


async def run_query_agent(
    question: str, product_id: str | None, evidence: list[dict] | None = None
) -> tuple[str, list[str]]:
    """Answer one question with the agent choosing its own retrieval.

    Returns `(answer, served_clause_ids)`. The caller validates the answer's
    citations against those ids and refuses when nothing survives — this
    function deliberately does not decide whether its own answer is usable.
    """
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    bucket: list[str] = []
    token = _served.set(bucket)
    search_token = _searches.set({})
    try:
        runner = InMemoryRunner(agent=build_query_agent(), app_name="regulens")
        session = await runner.session_service.create_session(
            app_name="regulens", user_id="query"
        )
        prompt = question if not product_id else f"{question}\n\n(product_id={product_id})"
        # Ids handed over up front count as served: this process read them out of
        # Firestore, which is the whole basis of the citation check.
        _serve([c["id"] for c in evidence or []])
        prompt += _evidence_block(evidence or [])
        parts: list[str] = []
        tool_calls: list[str] = []
        async for event in runner.run_async(
            user_id="query",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
        ):
            content = getattr(event, "content", None)
            for part in getattr(content, "parts", None) or []:
                if getattr(part, "function_call", None):
                    tool_calls.append(part.function_call.name)
                if getattr(part, "text", None):
                    parts.append(part.text)
    finally:
        _served.reset(token)
        _searches.reset(search_token)

    log(
        logger, logging.INFO, "query agent complete",
        tool_calls=tool_calls, served=len(bucket),
    )
    return "".join(parts).strip(), bucket
