"""Getting a worsening verdict out of the app.

Until now a person learned their product had gone non-compliant by opening the
page and looking. That is a dashboard. The word the project fought to earn is
*monitoring*, and monitoring that requires you to check it is not monitoring —
so a verdict that got worse is pushed to a channel a person already watches.

Deliberately small:

* One channel kind — an HTTP POST of JSON. A Slack incoming webhook is one of
  those, so is Discord, so is anything in between. Email is **not** built: it
  needs an SMTP provider and a verified sender address, neither of which exists
  here, and shipping an untested mail path would be a claim rather than a
  feature.
* Off unless configured. A webhook URL is a credential; nothing is posted
  anywhere by accident.
* Delivery is marked on the event that caused it, so at-least-once redelivery of
  the Pub/Sub message does not send the same alert twice.
* A failed send leaves the mark off, so it is retried on the next graph change
  rather than silently lost — and it is logged, because a channel that quietly
  stops working is worse than one that was never configured.
"""

from __future__ import annotations

import logging
from typing import Any

from app.db import get_db
from app.observability import log
from app.settings import get_settings

logger = logging.getLogger(__name__)

EVENTS = "graph_events"


def configured() -> bool:
    return bool((get_settings().alert_webhook_url or "").strip())


def _summarize(alert: dict[str, Any]) -> dict[str, Any]:
    """The payload posted out. Facts only, in the same shape the banner reads —
    the receiving end owns its own wording, exactly as the UI does."""
    context = alert.get("context") or {}
    after = alert.get("after") or {}
    before = alert.get("before") or {}
    scheduled = context.get("scheduled") is True
    product = context.get("product_name") or context.get("product_id") or "A product"
    market = context.get("market_label") or context.get("market_id") or "a market"
    if scheduled:
        headline = (
            f"{product}: the rules for {market} change on "
            f"{context.get('effective_date')} — it will read "
            f"'{after.get('status')}' from that date."
        )
    else:
        headline = (
            f"{product} is now '{after.get('status')}' for {market} "
            f"(was '{before.get('status')}')."
        )
    return {
        "source": "regulens",
        "text": headline,
        "alert_id": alert.get("id"),
        "event_type": alert.get("event_type"),
        "product_id": context.get("product_id"),
        "product_name": context.get("product_name"),
        "market_id": context.get("market_id"),
        "from_status": before.get("status"),
        "to_status": after.get("status"),
        "scheduled": scheduled,
        "effective_date": context.get("effective_date"),
        # The claim the whole product rests on: nobody asked for this.
        "unprompted": context.get("unprompted"),
        "source_name": context.get("source_name"),
        "substance": context.get("substance"),
        "limit_value": context.get("limit_value"),
        "limit_unit": context.get("limit_unit"),
        "document_id": context.get("document_id"),
        "clause_id": context.get("clause_id"),
    }


def _post(url: str, payload: dict[str, Any], timeout: float) -> None:
    import httpx

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()


def deliver_pending(limit: int | None = None) -> dict[str, Any]:
    """Send every worsening verdict that has not been sent yet.

    Returns a summary rather than raising: a channel being down must not fail
    the pipeline run that produced the verdict. The verdict is already stored;
    the notification is the part that can be retried.
    """
    settings = get_settings()
    url = (settings.alert_webhook_url or "").strip()
    if not url:
        return {"configured": False, "sent": 0, "failed": 0}

    from app.core import alerts as alerts_core

    cap = limit if limit is not None else settings.alert_webhook_max_per_run
    pending = [a for a in alerts_core.list_alerts() if not a.get("notified_at")]
    # Oldest first, so a burst delivers the change that started it rather than
    # whichever happened to sort highest.
    pending.reverse()
    sent = 0
    failed = 0
    db = get_db()
    for alert in pending[:cap]:
        try:
            _post(url, _summarize(alert), settings.alert_webhook_timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - a channel being down is not a pipeline failure
            failed += 1
            log(
                logger, logging.ERROR, "alert delivery failed",
                alert_id=alert.get("id"), error=str(exc)[:200],
            )
            continue
        # Delivery plumbing, not a decision: a plain merge with no event, the
        # same call embeddings use. It exists to stop a redelivered Pub/Sub
        # message sending the same alert a second time.
        db.collection(EVENTS).document(str(alert["id"])).set(
            {"notified_at": firestore_now()}, merge=True
        )
        sent += 1
    log(
        logger, logging.INFO, "alerts delivered",
        sent=sent, failed=failed, pending=len(pending), cap=cap,
    )
    return {"configured": True, "sent": sent, "failed": failed, "pending": len(pending)}


def firestore_now():
    from google.cloud import firestore

    return firestore.SERVER_TIMESTAMP
