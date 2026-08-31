"""Alerts, and the sentence behind each one.

A `product_status_changed` event carries the transition and two ids: the clause
that caused it and the document that clause came from. That is enough to be
correct and not enough to be useful — the banner said "Herbal Drink Powder
changed" and the one fact worth reading was missing: *nobody asked for this*.
The regulation arrived on its own, overnight, from an address the app watches,
and the product it affects is one somebody shipped.

So this module resolves those ids into the facts the sentence needs, and does it
by reading stored records only. Nothing here composes prose and nothing here
guesses. If the causing document has been deleted, the alert says the cause is
no longer on file rather than inventing a plausible one — an alert that explains
itself wrongly is worse than one that admits it cannot.
"""

from __future__ import annotations

import logging
from typing import Any

from google.cloud import firestore

from app.db import get_db
from app.observability import log

logger = logging.getLogger(__name__)

# Worse is up. Two statuses of equal weight are not an alert: a product moving
# from compliant to attention_required is news, and the reverse is not.
SEVERITY: dict[str, int] = {
    "unknown": 0,
    "attention_required": 1,
    "compliant": 1,
    "non_compliant": 2,
}

# Two kinds of news. A verdict that changed today, and a verdict that will
# change on a date already known — a rule adopted now that enters into force
# later. The second is the only warning a company can still act on, so it is an
# alert and not a footnote.
ALERTING_EVENTS = ("product_status_changed", "product_status_scheduled")

# Origins that mean "no human went and fetched this". The distinction is the
# product's entire claim, so it is named here rather than inferred in the UI.
UNPROMPTED_ORIGINS = {"watched_source"}


def worsened(event: dict[str, Any]) -> bool:
    after = (event.get("after") or {}).get("status")
    before = (event.get("before") or {}).get("status")
    return SEVERITY.get(after, 0) > SEVERITY.get(before, 0)


def _document(document_id: str | None) -> dict[str, Any] | None:
    if not document_id:
        return None
    snapshot = get_db().collection("documents").document(document_id).get()
    return (snapshot.to_dict() or {}) if snapshot.exists else None


def _clause(clause_id: str | None) -> dict[str, Any] | None:
    if not clause_id:
        return None
    snapshot = get_db().collection("clauses").document(clause_id).get()
    return (snapshot.to_dict() or {}) if snapshot.exists else None


def cause_document_id(event: dict[str, Any]) -> str | None:
    """Which document caused this event, following the clause if it has to.

    `graph.changed` carries the clause that moved and, until recently, nothing
    else — so an event written from reconciliation records a `clause_id` and a
    null `document_id`. Every fact this module reports about the cause hangs
    off the document: which regulation, which regulator, and whether anybody
    uploaded it. With a null there, a verdict moved by a regulation the
    scheduler found reported `unprompted: false`, which is the opposite of what
    happened and the one claim this product cannot get wrong.

    Resolved on read rather than backfilled, so events already written answer
    correctly too, and a clause that is later deleted goes back to saying
    nothing instead of borrowing another document's story.
    """
    cause = event.get("cause") or {}
    document_id = cause.get("document_id")
    if document_id:
        return str(document_id)
    clause = _clause(cause.get("clause_id"))
    found = (clause or {}).get("document_id")
    return str(found) if found else None


def explain(
    event: dict[str, Any],
    *,
    products_by_id: dict[str, Any],
    markets_by_id: dict[str, Any],
) -> dict[str, Any]:
    """The facts behind one alert. Every field is read, never composed.

    Returned as data, not a sentence, for the same reason every other status
    word in this system is: the UI owns the wording and translates machine
    tokens once, in one file.
    """
    cause = event.get("cause") or {}
    document_id = cause_document_id(event)
    document = _document(document_id)
    clause = _clause(cause.get("clause_id"))
    market_id = (event.get("after") or {}).get("market")
    market = markets_by_id.get(market_id) or {}
    product = products_by_id.get(event.get("entity_id")) or {}

    origin = (document or {}).get("origin")
    context: dict[str, Any] = {
        "product_id": event.get("entity_id"),
        "product_name": product.get("name"),
        "market_id": market_id,
        "market_label": market.get("label"),
        "market_country": market.get("country"),
        "from_status": (event.get("before") or {}).get("status"),
        "to_status": (event.get("after") or {}).get("status"),
        "document_id": cause.get("document_id"),
        "clause_id": cause.get("clause_id"),
        # The headline fact. True means the regulation reached the graph without
        # anybody uploading it — which is the difference between a checker and a
        # monitor, and the only reason this field exists.
        "unprompted": origin in UNPROMPTED_ORIGINS,
        "origin": origin,
        # Present only on a scheduled alert: the day the new verdict starts. The
        # UI needs it to say "from 12 January" rather than "soon", and the
        # difference between those two sentences is whether anybody can plan.
        "effective_date": (event.get("after") or {}).get("effective_date"),
        "scheduled": event.get("event_type") == "product_status_scheduled",
    }
    if document is not None:
        context |= {
            "source_name": document.get("source_name"),
            "jurisdiction": document.get("jurisdiction"),
            "source_type": document.get("source_type"),
            "ingested_at": document.get("uploaded_at"),
        }
    if clause is not None:
        context |= {
            "substance": clause.get("substance_normalized") or clause.get("substance"),
            "limit_value": clause.get("limit_value"),
            "limit_unit": clause.get("unit") or clause.get("unit_raw"),
            "clause_text": (clause.get("text") or "")[:400] or None,
        }
    # Said out loud rather than left as a missing key: an alert whose cause was
    # deleted must not look like an alert nobody bothered to explain.
    context["cause_available"] = document is not None or clause is not None
    return context


def list_alerts(limit: int = 20) -> list[dict[str, Any]]:
    """Unacknowledged worsening transitions, each with its cause resolved."""
    from app.core import markets as markets_core
    from app.core import products as products_core

    events = (
        get_db()
        .collection("graph_events")
        .where(filter=firestore.FieldFilter("event_type", "in", list(ALERTING_EVENTS)))
        .limit(50)
        .stream()
    )
    candidates = []
    for snapshot in events:
        event = snapshot.to_dict() | {"id": snapshot.id}
        if worsened(event) and not event.get("acknowledged"):
            candidates.append(event)
    candidates.sort(key=lambda e: e.get("occurred_at") or 0, reverse=True)

    # An alert about a product that no longer exists is a link to a 404 and a
    # verdict nobody can act on. The event stays in the audit trail; it just
    # stops being presented as something needing attention.
    products_by_id = {p.id: p.model_dump(mode="json") for p in products_core.list_products()}
    markets_by_id = {m["id"]: m for m in markets_core.list_markets()}
    alerts = [a for a in candidates if a.get("entity_id") in products_by_id][:limit]

    for alert in alerts:
        alert["context"] = explain(
            alert, products_by_id=products_by_id, markets_by_id=markets_by_id
        )
    log(
        logger, logging.INFO, "alerts listed",
        count=len(alerts),
        unprompted=sum(1 for a in alerts if a["context"].get("unprompted")),
    )
    return alerts
