"""Clause persistence and reads.

Phase 2 writes clauses as `pending_reconciliation` proposals. The decision
events (`clause_created` / `clause_superseded` / `conflict_opened` /
`clause_flagged_review`) belong to phase 3's verdict application — one decision,
one event. Until reconciliation exists, the audit trail for a clause is the
document's `document_ingested` event plus its `stage_log`.
"""

from __future__ import annotations

import logging
from typing import Any

from google.cloud import firestore

from app.core.repository import new_id
from app.db import get_db
from app.models import ClauseCandidate
from app.observability import log

logger = logging.getLogger(__name__)

COLLECTION = "clauses"


def persist_clauses(candidates: list[ClauseCandidate]) -> list[str]:
    """Write every clause for one document in a single batch — never a
    half-written clause set."""
    db = get_db()
    batch = db.batch()
    ids: list[str] = []
    now = firestore.SERVER_TIMESTAMP
    for candidate in candidates:
        doc_id = candidate.id or new_id("clause")
        ids.append(doc_id)
        payload = candidate.model_dump(mode="json")
        # Flat enum-string mirror of unit_enum: the guardrail, evaluator and
        # API filters all read `unit`, and Firestore cannot query a nested
        # member without extra index machinery.
        payload["unit"] = str(candidate.unit_enum) if candidate.unit_enum else None
        payload["id"] = doc_id
        payload["created_at"] = now
        batch.set(db.collection(COLLECTION).document(doc_id), payload)
    batch.commit()
    log(
        logger, logging.INFO, "clauses persisted",
        count=len(ids), document_id=candidates[0].document_id if candidates else None,
    )
    return ids


def clauses_for_document(document_id: str) -> list[dict[str, Any]]:
    query = (
        get_db()
        .collection(COLLECTION)
        .where(filter=firestore.FieldFilter("document_id", "==", document_id))
        .limit(200)
    )
    return [doc.to_dict() | {"id": doc.id} for doc in query.stream()]


def query_clauses(
    *,
    substance: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    from app.core.normalization import normalize_substance

    db = get_db()
    q = db.collection(COLLECTION)
    if substance:
        normalized, _ = normalize_substance(substance)
        q = q.where(filter=firestore.FieldFilter("substance_normalized", "==", normalized))
    if status:
        q = q.where(filter=firestore.FieldFilter("status", "==", status))
    return [d.to_dict() | {"id": d.id} for d in q.limit(200).stream()]
