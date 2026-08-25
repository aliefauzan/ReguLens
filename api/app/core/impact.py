"""The Impact Engine.

clause changed → requirements referencing it → products → markets →
re-evaluate → status rollup → alert. Pure deterministic traversal; there is no
model call in this module and the submission says so plainly.
"""

from __future__ import annotations

import logging

from google.cloud import firestore

from app.core.guardrail import substances_comparable, to_mg_per_kg
from app.core.repository import write_with_event
from app.db import get_db
from app.models import EventType
from app.observability import log

logger = logging.getLogger(__name__)


def clauses_active() -> list[dict]:
    docs = (
        get_db()
        .collection("clauses")
        .where(filter=firestore.FieldFilter("status", "in", ["active", "conflicted"]))
        .limit(200)
        .stream()
    )
    return [d.to_dict() | {"id": d.id} for d in docs]


def markets_all() -> list[dict]:
    return [
        d.to_dict() | {"id": d.id}
        for d in get_db().collection("markets").limit(20).stream()
    ]


def products_all() -> list[dict]:
    return [
        d.to_dict() | {"id": d.id}
        for d in get_db().collection("products").limit(50).stream()
    ]


# ---------------------------------------------------------------------------
# Materialization: this clause binds this product in this market


def materialize_for_product(product_id: str) -> list[dict]:
    """Create/update `requirements` for one product across its target markets.

    Requirements are keyed (product_id, market_id, clause_id) and updated in
    place — never duplicated.
    """
    db = get_db()
    product = next(
        (p for p in products_all() if p["id"] == product_id), None
    )
    if product is None:
        return []
    markets = [m for m in markets_all() if m["id"] in set(product.get("target_markets") or [])]
    active = clauses_active()
    requirements: list[dict] = []
    for market in markets:
        ingredient_substances = {i.get("normalized") for i in product.get("ingredients", [])}
        for clause in active:
            jurisdictions = {str(j).upper() for j in market.get("jurisdictions", [])}
            if str(clause.get("jurisdiction") or "").upper() not in jurisdictions:
                continue
            # Family-aware bind: a clause limiting "benzoic acid — benzoates"
            # binds a product containing sodium benzoate (same documented basis).
            matches = any(
                substances_comparable(clause.get("substance_normalized"), ing)
                for ing in ingredient_substances
            )
            if not matches and clause.get("clause_type") == "numeric_limit":
                continue  # numeric limits bind only via a matching ingredient
            key = f"{product_id}:{market['id']}:{clause['id']}"
            evaluation = evaluate(product, clause)
            existing = (
                db.collection("requirements")
                .where(filter=firestore.FieldFilter("requirement_key", "==", key))
                .limit(1)
                .stream()
            )
            existing_list = list(existing)
            req_ref = None
            before = None
            if existing_list:
                snap = existing_list[0]
                req_ref = db.collection("requirements").document(snap.id)
                before = snap.to_dict()
            payload = {
                "workspace_id": "ws_demo",
                "requirement_key": key,
                "product_id": product_id,
                "market_id": market["id"],
                "jurisdiction": clause.get("jurisdiction"),
                "clause_id": clause["id"],
                "document_id": clause.get("document_id"),
                "requirement_type": clause.get("clause_type"),
                "substance_normalized": clause.get("substance_normalized"),
                "limit_value": clause.get("limit_value"),
                "unit": clause.get("unit"),
                "product_value": evaluation["product_value"],
                "product_unit": evaluation["product_unit"],
                "comparable_value": evaluation["comparable_value"],
                "comparable_limit": evaluation["comparable_limit"],
                "comparable_unit": evaluation["comparable_unit"],
                "evaluation": evaluation["evaluation"],
                "severity": evaluation["severity"],
                "reason": evaluation["reason"],
                "status": "active",
                "evaluated_at": firestore.SERVER_TIMESTAMP,
            }
            if before is None:
                event_type = EventType.REQUIREMENT_CREATED
                after_payload = payload
            else:
                changed = any(
                    before.get(f) != v
                    for f, v in payload.items()
                    if f in {"limit_value", "evaluation", "severity", "clause_id"}
                )
                if not changed:
                    requirements.append({**before, "id": snap.id})
                    continue  # idempotent: unchanged requirement writes nothing
                event_type = EventType.REQUIREMENT_CHANGED
                after_payload = {**before, **payload}
            write_with_event(
                "requirements",
                (req_ref.id if req_ref else key.replace(":", "_")),
                payload | ({} if before is None else {"updated_at": firestore.SERVER_TIMESTAMP}),
                event_type=event_type,
                entity_type="requirement",
                before=before,
                after=after_payload,
                triggered_by="impact_engine",
                cause={
                    "clause_id": clause["id"],
                    "document_id": clause.get("document_id"),
                    "market_id": market["id"],
                },
                confidence=clause.get("confidence"),
                merge=True,
            )
            requirements.append(payload | {"id": (req_ref.id if req_ref else key.replace(":", "_"))})
    return requirements


def rollup_status(product_id: str) -> dict[str, str]:
    """Per-market compliance status for one product."""
    statuses: dict[str, str] = {}
    product = next((p for p in products_all() if p["id"] == product_id), None)
    if product is None:
        return statuses
    requirements = [
        d.to_dict() | {"id": d.id}
        for d in (
            get_db()
            .collection("requirements")
            .where(filter=firestore.FieldFilter("product_id", "==", product_id))
            .limit(200)
            .stream()
        )
    ]
    markets = [m for m in markets_all() if m["id"] in set(product.get("target_markets") or [])]
    for market in markets:
        market_reqs = [r for r in requirements if r.get("market_id") == market["id"]]
        evaluations = {r.get("evaluation") for r in market_reqs}
        if not market_reqs:
            statuses[market["id"]] = "unknown"
        elif "fail" in evaluations:
            statuses[market["id"]] = "non_compliant"
        elif "needs_review" in evaluations:
            statuses[market["id"]] = "attention_required"
        else:
            statuses[market["id"]] = "compliant"
    return statuses


def run_impact(clause_id: str | None, document_id: str | None) -> dict:
    """`graph.changed` consumer. Re-evaluates every product; idempotent because
    unchanged requirements write nothing and status events fire only on actual
    transitions."""
    summary: dict = {"products": {}}
    for product in products_all():
        materialize_for_product(product["id"])
        new_statuses = rollup_status(product["id"])
        previous = _previous_status(product["id"])
        for market_id, new_status in new_statuses.items():
            old_status = previous.get(market_id)
            if old_status != new_status:
                merged = dict(previous)
                merged[market_id] = new_status
                write_with_event(
                    "products",
                    product["id"],
                    {"compliance_status": merged, "updated_at": firestore.SERVER_TIMESTAMP},
                    event_type=EventType.PRODUCT_STATUS_CHANGED,
                    entity_type="product",
                    before={"market": market_id, "status": old_status},
                    after={"market": market_id, "status": new_status},
                    triggered_by="impact_engine",
                    cause={
                        "clause_id": clause_id,
                        "document_id": document_id,
                    },
                    merge=True,
                )
                log(
                    logger, logging.INFO, "status_changed",
                    product_id=product["id"], market_id=market_id,
                    before=old_status, after=new_status,
                )
        summary["products"][product["id"]] = new_statuses
    return summary


def _previous_status(product_id: str) -> dict[str, str | None]:
    """Read the stored per-market compliance map from the product doc."""
    snap = get_db().collection("products").document(product_id).get()
    return (snap.to_dict() or {}).get("compliance_status") or {}


def run_impact_for_product(product_id: str) -> dict:
    """Product create/update hook: materialize + evaluate + rollup."""
    materialize_for_product(product_id)
    statuses = rollup_status(product_id)
    db = get_db()
    snap = db.collection("products").document(product_id).get()
    previous = (snap.to_dict() or {}).get("compliance_status") or {}
    changed = {m: s for m, s in statuses.items() if previous.get(m) != s}
    for market_id, new_status in changed.items():
        write_with_event(
            "products",
            product_id,
            {"compliance_status": statuses},
            event_type=EventType.PRODUCT_STATUS_CHANGED,
            entity_type="product",
            before={"market": market_id, "status": previous.get(market_id)},
            after={"market": market_id, "status": new_status},
            triggered_by="impact_engine",
            cause=None,
            merge=True,
        )
    if changed:
        db.collection("products").document(product_id).set(
            {"compliance_status": statuses}, merge=True
        )
    return {"statuses": statuses, "changed": changed}


# ---------------------------------------------------------------------------
# Evaluation — deterministic, no model


def evaluate(product: dict, requirement_clause: dict) -> dict:
    """Evaluate one clause against one product.

    Returns the raw amount as the user entered it AND the converted value the
    comparison actually used. Reporting `product_value` next to the clause's
    unit — 0.02 alongside a mg/kg limit when the ingredient was given as 0.02%
    — states a number that is off by four orders of magnitude, which is worse
    than saying nothing.
    """
    ingredient = next(
        (
            i for i in product.get("ingredients", [])
            if substances_comparable(i.get("normalized"), requirement_clause.get("substance_normalized"))
        ),
        None,
    )
    amount = ingredient.get("amount") if ingredient else None
    comparable_value: float | None = None
    comparable_limit: float | None = None

    if requirement_clause.get("clause_type") != "numeric_limit":
        result = "needs_review"
        reason = "non_numeric_clause"
    elif amount is None:
        result = "needs_review"
        reason = "product_amount_unknown"
    elif to_mg_per_kg(amount, ingredient.get("unit")) is None or \
            to_mg_per_kg(requirement_clause.get("limit_value"), requirement_clause.get("unit")) is None:
        result = "needs_review"
        reason = "unit_unconvertible"
    else:
        pv = to_mg_per_kg(amount, ingredient.get("unit"))
        lv = to_mg_per_kg(requirement_clause.get("limit_value"), requirement_clause.get("unit"))
        result = "pass" if pv <= lv else "fail"
        reason = None
        comparable_value = pv
        comparable_limit = lv

    if (requirement_clause.get("confidence") or 0) < 0.5 and result != "needs_review":
        result = "needs_review"
        reason = "clause_confidence_below_0_5"

    severity = {"fail": "high", "needs_review": "medium", "pass": "low"}.get(result, "medium")
    return {
        "evaluation": result,
        "severity": severity,
        "product_value": amount,
        "product_unit": (ingredient or {}).get("unit"),
        # Both sides in one unit, so a reader can see the comparison that was
        # actually made rather than being asked to trust it.
        "comparable_value": comparable_value,
        "comparable_limit": comparable_limit,
        "comparable_unit": "mg_per_kg" if comparable_value is not None else None,
        "reason": reason,
    }