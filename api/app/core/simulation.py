"""What-if: the verdict for a product that does not exist yet.

"Reformulate to 120 mg/kg and you are legal in both markets" is a sentence
somebody can act on, and until now the only way to get it was to save a real
product, wait for the pipeline, read the answer and delete it again.

Everything here is read-only. No document is written, no event is emitted, and
no requirement row survives the request — which is why it can be called on every
keystroke of a form without polluting the audit trail.

It shares `clause_binds` and `evaluate` with the impact engine on purpose. A
preview that decided which rules apply by its own route would eventually
disagree with the page it is previewing, and a disagreeing preview is worse than
none.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.core.impact import (
    _in_force,
    _status_from,
    clause_binds,
    clauses_active,
    evaluate,
    markets_all,
)
from app.core.strictest import binding_limits_from
from app.observability import log

logger = logging.getLogger(__name__)


def simulate(product: dict[str, Any], as_of: date | None = None) -> dict[str, Any]:
    """Evaluate a hypothetical product against every rule currently in force.

    `product` is a normalized product dict — the same shape the repository
    stores, ingredients already carrying `normalized`. Returns the statuses, the
    requirement rows that produced them, and the strictest limit per substance.
    """
    as_of = as_of or date.today()
    targets = set(product.get("target_markets") or [])
    markets = [m for m in markets_all() if m["id"] in targets]
    active = clauses_active()

    rows: list[dict[str, Any]] = []
    for market in markets:
        for clause in active:
            if not clause_binds(product, clause, market):
                continue
            evaluation = evaluate(product, clause)
            rows.append(
                {
                    "market_id": market["id"],
                    "jurisdiction": clause.get("jurisdiction"),
                    "clause_id": clause["id"],
                    "document_id": clause.get("document_id"),
                    "requirement_type": clause.get("clause_type"),
                    "substance_normalized": clause.get("substance_normalized"),
                    "limit_value": clause.get("limit_value"),
                    "unit": clause.get("unit"),
                    "effective_date": clause.get("effective_date"),
                    **evaluation,
                }
            )

    statuses: dict[str, str] = {}
    for market in markets:
        market_rows = [r for r in rows if r["market_id"] == market["id"]]
        if not market_rows:
            statuses[market["id"]] = "unknown"
            continue
        binding = [r for r in market_rows if _in_force(r.get("effective_date"), as_of)]
        statuses[market["id"]] = _status_from(binding) if binding else "compliant"

    result = {
        "statuses": statuses,
        "requirements": rows,
        "binding_limits": binding_limits_from(rows, markets, as_of),
        # Said plainly, because a page showing a verdict for something that was
        # never saved must not be mistaken for the product's actual record.
        "simulated": True,
    }
    log(
        logger, logging.INFO, "simulation run",
        markets=len(markets), rules_bound=len(rows), statuses=statuses,
    )
    return result
