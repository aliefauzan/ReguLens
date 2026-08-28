"""Repository layer.

The rule from the plan, enforced here rather than by convention: every mutation
writes its `graph_event` in the same batch as the change. There is no raw update
method to reach around, so an audit trail with holes is not reachable from the
API surface.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from google.cloud import firestore

from app.db import get_db
from app.models import WORKSPACE_ID, EventType
from app.observability import get_trace_id, log

logger = logging.getLogger(__name__)

EVENTS = "graph_events"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _event_payload(
    event_type: EventType,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    triggered_by: str,
    cause: dict[str, Any] | None,
    confidence: float | None,
) -> dict[str, Any]:
    return {
        "workspace_id": WORKSPACE_ID,
        "event_type": str(event_type),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before": before,
        "after": after,
        "cause": cause,
        "triggered_by": triggered_by,
        "confidence": confidence,
        "trace_id": get_trace_id(),
        "occurred_at": firestore.SERVER_TIMESTAMP,
    }


def write_with_event(
    collection: str,
    doc_id: str,
    data: dict[str, Any],
    *,
    event_type: EventType,
    entity_type: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    triggered_by: str = "api",
    cause: dict[str, Any] | None = None,
    confidence: float | None = None,
    merge: bool = False,
) -> str:
    """Write a document and its event atomically. Returns the event id."""
    db = get_db()
    batch = db.batch()
    batch.set(db.collection(collection).document(doc_id), data, merge=merge)

    event_id = new_id("evt")
    batch.set(
        db.collection(EVENTS).document(event_id),
        _event_payload(
            event_type, entity_type, doc_id, before, after, triggered_by, cause, confidence
        ),
    )
    batch.commit()
    log(
        logger, logging.INFO, "mutation recorded",
        collection=collection, entity_id=doc_id, event_type=str(event_type), event_id=event_id,
    )
    return event_id


def delete_with_event(
    collection: str,
    doc_id: str,
    *,
    event_type: EventType,
    entity_type: str,
    before: dict[str, Any] | None,
    also_delete: list[Any] | None = None,
    triggered_by: str = "api",
    cause: dict[str, Any] | None = None,
) -> str:
    """Delete a document, its derived documents, and record the event — all in
    one batch. Returns the event id.

    A delete is still a mutation, so it goes through here for the same reason
    every write does: the event cannot be skipped by anyone using this module.
    `also_delete` takes the references of documents that only exist because the
    deleted one did; leaving those behind would keep a removed entity visible
    to every query that scans a derived collection.
    """
    db = get_db()
    batch = db.batch()
    for reference in also_delete or []:
        batch.delete(reference)
    batch.delete(db.collection(collection).document(doc_id))

    event_id = new_id("evt")
    batch.set(
        db.collection(EVENTS).document(event_id),
        _event_payload(
            event_type, entity_type, doc_id, before, None, triggered_by, cause, None
        ),
    )
    batch.commit()
    log(
        logger, logging.INFO, "deletion recorded",
        collection=collection, entity_id=doc_id, event_type=str(event_type),
        event_id=event_id, derived_deleted=len(also_delete or []),
    )
    return event_id


def events_for(entity_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Read the audit trail for one entity, newest first."""
    query = (
        get_db()
        .collection(EVENTS)
        .where(filter=firestore.FieldFilter("entity_id", "==", entity_id))
        .limit(limit)
    )
    events = [doc.to_dict() | {"id": doc.id} for doc in query.stream()]
    events.sort(key=lambda e: e.get("occurred_at") or 0, reverse=True)
    return events
