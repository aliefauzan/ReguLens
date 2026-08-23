"""ADK Extraction Agent — a thin wrapper, exactly like the root agent.

The tool bodies live in `app/core/extraction/tools.py`. This module only
registers them and drives the runner. The pipeline re-validates everything the
agent emits, so the agent proposes and typed code decides — even from inside
the agent loop.
"""

from __future__ import annotations

import logging

from app.core.extraction.tools import emit_clause_candidates, extract_text
from app.observability import log
from app.settings import get_settings

logger = logging.getLogger(__name__)

EXTRACTION_AGENT_NAME = "regulens_extraction"

_INSTRUCTION = """You are ReguLens's regulatory-clause extraction engine.
You will be given a document id. Work in order:

1. Call extract_text with that document id to load its text.
2. Read the text and extract every distinct regulatory statement that imposes
   a requirement on food, beverage, cosmetic or supplement products.
3. Call emit_clause_candidates ONCE with the complete JSON array of candidates.

Each candidate object has exactly these fields:
- text: verbatim source sentence(s)
- clause_type: numeric_limit | documentation | labeling | certification | other
- substance: substance name as written, or null for non-substance rules
- limit_value: the number in the limit, or null
- unit_raw: the unit as written (e.g. "mg/kg", "%", "ppm"), or null
- product_type: food_beverage_powder | food_beverage_liquid | food_solid |
  supplement | cosmetic — closest match or null
- effective_date: ISO date when stated, else null

Extract only what the text says. Never invent limits."""


def build_extraction_agent():
    """Imported lazily so a broken ADK install cannot take down /health."""
    from google.adk.agents import Agent

    settings = get_settings()
    return Agent(
        name=EXTRACTION_AGENT_NAME,
        model=settings.gemini_model,
        instruction=_INSTRUCTION,
        tools=[extract_text, emit_clause_candidates],
    )


async def run_extraction_agent(document_id: str) -> list[dict]:
    """Run the ADK extraction agent over one document.

    Returns the raw candidate dicts collected from `emit_clause_candidates`
    function calls. Empty list means the agent never emitted — callers fall
    back to the direct structured-output path rather than losing the document.
    """
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent = build_extraction_agent()
    runner = InMemoryRunner(agent=agent, app_name="regulens")
    session = await runner.session_service.create_session(
        app_name="regulens", user_id="worker"
    )

    collected: list[dict] = []
    async for event in runner.run_async(
        user_id="worker",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=f"document_id={document_id}")],
        ),
    ):
        content = getattr(event, "content", None)
        for part in getattr(content, "parts", None) or []:
            call = getattr(part, "function_call", None)
            if call is not None and call.name == "emit_clause_candidates":
                args = call.args or {}
                candidates = args.get("candidates") or []
                collected.extend(candidates)

    log(
        logger, logging.INFO, "adk extraction complete",
        document_id=document_id, candidates=len(collected),
    )
    return collected
