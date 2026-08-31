"""Which number actually binds a product sold in more than one market.

The graph detects that the EU allows 150 mg/kg of benzoates and Indonesia allows
400, and stops there, calling it a conflict. That is true and it is not the
question anybody asks. A company selling into both markets has one recipe, and
the only number it can ship is the lowest one still in force — 150, set by the
EU, whether or not Indonesia would have permitted more.

So this module answers the shipping question: per substance, the strictest limit
across the markets this product actually targets, which jurisdiction sets it,
and whether the product satisfies it today.

Deterministic. No model call, no new state — it reads the requirement rows the
impact engine already wrote, and is computed on every read so it cannot go
stale, exactly like `relevance.py`.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.core.impact import _in_force, _requirements_for, _target_markets
from app.observability import log

logger = logging.getLogger(__name__)


def _comparable(requirement: dict[str, Any]) -> float | None:
    """The limit in mg/kg, or None when this row cannot take part in a
    comparison. `comparable_limit` is written by the evaluator precisely so that
    two limits are only ever compared after both were converted."""
    value = requirement.get("comparable_limit")
    return float(value) if isinstance(value, int | float) else None


def binding_limits(
    product_id: str,
    as_of: date | None = None,
) -> dict[str, Any]:
    """The strictest in-force limit per substance across a product's markets."""
    return binding_limits_from(
        _requirements_for(product_id), _target_markets(product_id), as_of
    )


def binding_limits_from(
    rows: list[dict[str, Any]],
    markets: list[dict[str, Any]],
    as_of: date | None = None,
) -> dict[str, Any]:
    """The same answer over rows already in hand.

    Split out so the what-if simulator can ask it of requirements that were
    never written to Firestore — a preview that computed its ceiling by a
    different route than the real page would not be a preview.

    Returns `{"substances": [...], "markets": [...], "skipped": {...}}`.

    `skipped` is not decoration. A substance whose rules could not be compared —
    no numeric limit, or a unit nothing converts — is counted and named, because
    a page that silently drops it presents a partial answer as a complete one,
    and the whole product is a claim that it does not do that.
    """
    as_of = as_of or date.today()
    market_ids = [m["id"] for m in markets]
    labels = {m["id"]: m for m in markets}
    requirements = [
        r
        for r in rows
        if r.get("market_id") in set(market_ids)
        and _in_force(r.get("effective_date"), as_of)
    ]

    by_substance: dict[str, list[dict]] = {}
    uncomparable: dict[str, int] = {}
    for requirement in requirements:
        substance = requirement.get("substance_normalized")
        if not substance:
            continue
        if _comparable(requirement) is None:
            uncomparable[substance] = uncomparable.get(substance, 0) + 1
            continue
        by_substance.setdefault(substance, []).append(requirement)

    substances: list[dict[str, Any]] = []
    for substance, rows in sorted(by_substance.items()):
        # The strictest row wins. Ties break on the market id so the answer is
        # stable between reads rather than depending on Firestore's ordering.
        rows.sort(key=lambda r: (_comparable(r), str(r.get("market_id"))))
        strictest = rows[0]
        limit = _comparable(strictest)
        product_value = strictest.get("comparable_value")
        covered = {str(r.get("market_id")) for r in rows}
        if product_value is None:
            verdict = "unknown"
        elif float(product_value) <= limit:
            verdict = "pass"
        else:
            verdict = "fail"
        substances.append(
            {
                "substance_normalized": substance,
                "binding_limit": limit,
                "unit": "mg_per_kg",
                "binding_market_id": strictest.get("market_id"),
                "binding_market_label": (labels.get(strictest.get("market_id")) or {}).get("label"),
                "binding_jurisdiction": strictest.get("jurisdiction"),
                "binding_clause_id": strictest.get("clause_id"),
                "binding_document_id": strictest.get("document_id"),
                "product_value": product_value,
                "verdict": verdict,
                # The spread, so a reader can see that one market is the reason
                # rather than being asked to take the single number on trust.
                "limits_by_market": [
                    {
                        "market_id": r.get("market_id"),
                        "market_label": (labels.get(r.get("market_id")) or {}).get("label"),
                        "limit": _comparable(r),
                        "clause_id": r.get("clause_id"),
                    }
                    for r in rows
                ],
                # Named because "the strictest of the markets that regulate it"
                # and "the strictest of every market you sell in" are different
                # claims, and only the first one is true.
                "markets_without_a_rule": sorted(set(market_ids) - covered),
                "uncomparable_rules": uncomparable.get(substance, 0),
            }
        )

    result = {
        "substances": substances,
        "markets": market_ids,
        "skipped": {
            "uncomparable_rules": sum(uncomparable.values()),
            "substances_affected": sorted(uncomparable),
        },
    }
    log(
        logger, logging.INFO, "binding limits computed",
        markets=len(market_ids), substances=len(substances),
        skipped=result["skipped"]["uncomparable_rules"],
    )
    return result
