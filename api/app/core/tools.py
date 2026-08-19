"""Tool bodies.

These are plain Python functions with plain arguments and plain return values.
`app/adk/` registers them with ADK; nothing here imports ADK. That separation is
the whole point: every tool stays unit-testable without standing up an agent.
"""

from __future__ import annotations

from app.core.markets import list_markets


def lookup_market(jurisdiction: str) -> dict:
    """Return the configured market for a jurisdiction code such as EU or ID.

    Args:
        jurisdiction: Two-letter jurisdiction code, case-insensitive.

    Returns:
        The market record, or an explicit not-found result. Never raises for a
        miss — an agent handles a structured answer better than an exception.
    """
    wanted = (jurisdiction or "").strip().upper()
    for market in list_markets():
        codes = {str(j).upper() for j in market.get("jurisdictions", [])}
        codes.add(str(market.get("country_code", "")).upper())
        if wanted in codes or any(code.startswith(wanted) for code in codes if wanted):
            return {"found": True, "market": market}
    return {"found": False, "jurisdiction": wanted}
