"""ADK registration — a thin wrapper, nothing more.

Google ADK is a hard requirement of the hackathon rules, so this must run in the
deployed environment, not only locally. The pattern established here holds for
every agent added later: the tool body lives in `app/core/`, and this module
only registers it.
"""

from __future__ import annotations

import logging

from app.core.tools import lookup_market
from app.observability import log
from app.settings import get_settings

logger = logging.getLogger(__name__)

ROOT_AGENT_NAME = "regulens_root"

_INSTRUCTION = """You are ReguLens, a regulatory compliance assistant.
Use the lookup_market tool to resolve a jurisdiction before answering questions
about it. Never invent a regulatory limit; if you do not have one, say so."""


def build_root_agent():
    """Construct the root agent. Imported lazily so that a missing or broken ADK
    install cannot stop the API from serving `/health`."""
    from google.adk.agents import Agent

    settings = get_settings()
    return Agent(
        name=ROOT_AGENT_NAME,
        model=settings.gemini_model,
        instruction=_INSTRUCTION,
        tools=[lookup_market],
    )


async def run_smoke_test(prompt: str = "Which regulator covers Indonesia?") -> dict:
    """Prove ADK actually executes here. This is a phase-0 exit criterion: an
    agent with one tool running on Cloud Run, not just on a laptop."""
    settings = get_settings()
    if settings.fake_llm:
        # Phase 6's E2E suite runs without touching Vertex. The switch goes in
        # now so no handler has to grow one later.
        return {
            "agent": ROOT_AGENT_NAME,
            "model": "fake",
            "tool_calls": ["lookup_market"],
            "text": "BPOM regulates food and drugs in Indonesia.",
        }

    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent = build_root_agent()
    runner = InMemoryRunner(agent=agent, app_name="regulens")
    session = await runner.session_service.create_session(app_name="regulens", user_id="smoke")

    tool_calls: list[str] = []
    parts: list[str] = []
    async for event in runner.run_async(
        user_id="smoke",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        content = getattr(event, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "function_call", None):
                tool_calls.append(part.function_call.name)
            if getattr(part, "text", None):
                parts.append(part.text)

    result = {
        "agent": ROOT_AGENT_NAME,
        "model": settings.gemini_model,
        "tool_calls": tool_calls,
        "text": "".join(parts).strip(),
    }
    log(logger, logging.INFO, "adk smoke test complete", tool_calls=tool_calls)
    return result
