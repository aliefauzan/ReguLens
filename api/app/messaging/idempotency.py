"""Pub/Sub delivery is at-least-once and *will* redeliver. Every handler checks
here first and records completion at the end, so a redelivery is a cheap no-op
rather than a duplicate write.

The marker collection is keyed by (handler, message_id) so two different
handlers consuming the same message do not shadow each other.
"""

from __future__ import annotations

import logging

from google.api_core import exceptions as gexc
from google.cloud import firestore

from app.db import get_db
from app.observability import log

logger = logging.getLogger(__name__)

_COLLECTION = "processed_messages"


def _doc_id(handler: str, message_id: str) -> str:
    return f"{handler}:{message_id}"


def already_processed(handler: str, message_id: str) -> bool:
    if not message_id:
        return False
    snapshot = get_db().collection(_COLLECTION).document(_doc_id(handler, message_id)).get()
    if snapshot.exists:
        log(logger, logging.INFO, "duplicate delivery ignored", handler=handler, message_id=message_id)
        return True
    return False


def mark_processed(handler: str, message_id: str) -> None:
    if not message_id:
        return
    try:
        get_db().collection(_COLLECTION).document(_doc_id(handler, message_id)).create(
            {"handler": handler, "message_id": message_id, "processed_at": firestore.SERVER_TIMESTAMP}
        )
    except gexc.AlreadyExists:
        # Two concurrent deliveries raced. Both did the work idempotently; the
        # marker existing is the desired end state either way.
        pass
