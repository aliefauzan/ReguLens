"""ADK Query Agent — the one agent that genuinely needs tool selection.

Tools are the retrieval functions from `core/`; the agent decides which to call
for an open-ended question. Grounding validation stays in `core/query.py` — the
agent proposes answers; typed code decides what may be returned to a user.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

QUERY_AGENT_NAME = "regulens_query"

_INSTRUCTION = """You are ReguLens's compliance query agent. Answer the user's
question about their product and ingested regulations. Use the retrieval tools
to ground every claim:

- get_product_compliance(product_id) — current requirements and evaluations
- find_clauses(query) — clause search over ingested regulations
- get_events(entity_id) — what changed and when
- get_conflicts() — open cross-jurisdiction conflicts

Cite stored clause IDs inline as [clause_id]. If the tools return nothing
relevant, say you do not have enough information — never answer a compliance
question from general knowledge."""


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
    return {"requirements": reqs[:20], "statuses": rollup_status(product_id)}


def find_clauses_tool(query: str, k: int = 5) -> dict:
    from app.core.query import _retrieve

    bundle = _retrieve(query, None)
    return {"clauses": [{"id": c["id"], "text": str(c.get("text"))[:300]} for c in bundle["clauses"]]}


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
    return {"conflicts": [d.to_dict() | {"id": d.id} for d in docs]}


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
