"""Document ingestion: hash, dedupe, store, record, publish.

The API does no extraction work — it hashes, stores, records, publishes, and
returns 202. Everything slow lives behind the Pub/Sub message this module sends.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from google.cloud import firestore

from app.core.repository import events_for, new_id, write_with_event
from app.db import get_db
from app.models import (
    WORKSPACE_ID,
    ClauseCandidate,
    DocumentIn,
    DocumentStatus,
    EventType,
    RegulatoryDocument,
)
from app.observability import get_trace_id, log
from app.settings import get_settings

logger = logging.getLogger(__name__)

COLLECTION = "documents"

# A document whose pipeline has reached one of these states is *done*; a
# re-upload of identical bytes short-circuits to it instead of re-billing Gemini.
_DONE_STATUSES = {str(DocumentStatus.EXTRACTED), str(DocumentStatus.RECONCILED)}


def _to_document(doc_id: str, data: dict[str, Any]) -> RegulatoryDocument:
    return RegulatoryDocument.model_validate({**data, "id": doc_id})


def find_by_hash(content_sha256: str) -> RegulatoryDocument | None:
    """The rehearsal cache. Returns a document that is already past extraction —
    an in-flight or failed upload never satisfies a re-upload."""
    query = (
        get_db()
        .collection(COLLECTION)
        .where(filter=firestore.FieldFilter("workspace_id", "==", WORKSPACE_ID))
        .where(filter=firestore.FieldFilter("content_sha256", "==", content_sha256))
        .limit(5)
    )
    for snapshot in query.stream():
        data = snapshot.to_dict() or {}
        status = str(data.get("status", ""))
        if status in _DONE_STATUSES:
            return _to_document(snapshot.id, data)
    return None


def create_document(
    *,
    meta: DocumentIn,
    content_bytes: bytes | None = None,
    text: str | None = None,
    page_count: int | None = None,
    text_preview: str | None = None,
    char_count: int = 0,
    storage_uri: str | None = None,
    trace_id: str | None = None,
) -> tuple[RegulatoryDocument, bool]:
    """Create the documents record (or return the cached twin).

    Returns `(document, cached)` — `cached=True` means an identical file was
    already processed and nothing new will run.
    """
    hasher = hashlib.sha256()
    if content_bytes:
        hasher.update(content_bytes)
    if text:
        hasher.update(text.encode("utf-8"))
    content_sha256 = hasher.hexdigest()

    cached_doc = find_by_hash(content_sha256)
    if cached_doc is not None:
        log(
            logger,
            logging.INFO,
            "upload cache hit",
            content_sha256=content_sha256,
            existing_document_id=cached_doc.id,
        )
        return cached_doc, True

    document_id = new_id("doc")
    now_status = DocumentStatus.UPLOADED
    record: dict[str, Any] = {
        "workspace_id": WORKSPACE_ID,
        "filename": meta.filename or f"{document_id}.txt",
        "content_sha256": content_sha256,
        "source_type": str(meta.source_type),
        "source_name": meta.source_name,
        "jurisdiction": meta.jurisdiction.upper(),
        "declared_effective_date": meta.declared_effective_date,
        "storage_uri": storage_uri,
        "text_preview": (text_preview[:500] if text_preview else None),
        "text_inline": text,
        "page_count": page_count,
        "char_count": char_count,
        "status": str(now_status),
        "stage_log": [],
        "error": None,
        "failed_stage": None,
        "trace_id": trace_id or get_trace_id(),
        "uploaded_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    write_with_event(
        COLLECTION,
        document_id,
        record,
        event_type=EventType.DOCUMENT_INGESTED,
        entity_type="document",
        after={
            k: v
            for k, v in record.items()
            if k not in {"created_at", "updated_at", "uploaded_at"}
        },
    )

    from app.messaging.publisher import publish

    publish(
        get_settings().topic_document_uploaded,
        {"document_id": document_id, "workspace_id": WORKSPACE_ID},
    )

    created = get_document(document_id)
    assert created is not None  # we just wrote it
    return created, False


def get_document(document_id: str) -> RegulatoryDocument | None:
    snapshot = get_db().collection(COLLECTION).document(document_id).get()
    if not snapshot.exists:
        return None
    return _to_document(snapshot.id, snapshot.to_dict())


def list_documents(limit: int = 50) -> list[RegulatoryDocument]:
    docs = get_db().collection(COLLECTION).limit(limit).stream()
    out = [_to_document(d.id, d.to_dict()) for d in docs]
    out.sort(key=lambda d: d.uploaded_at or 0, reverse=True)
    return out


def retry_document(document_id: str, *, publish_message: bool = True) -> RegulatoryDocument | None:
    """Reset a failed document to `uploaded` and republish `document.uploaded`.

    Retry is only meaningful from `failed`; anything else returns unchanged.
    """
    existing = get_document(document_id)
    if existing is None:
        return None
    if existing.status != DocumentStatus.FAILED:
        return existing

    db = get_db()
    db.collection(COLLECTION).document(document_id).set(
        {
            "status": str(DocumentStatus.UPLOADED),
            "error": None,
            "failed_stage": None,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    if publish_message:
        from app.messaging.publisher import publish

        publish(
            get_settings().topic_document_uploaded,
            {"document_id": document_id, "status": "retry"},
        )
    log(logger, logging.INFO, "document retry queued", document_id=document_id)
    return get_document(document_id)


def events_for_document(document_id: str) -> list[dict[str, Any]]:
    return events_for(document_id)


def clauses_for_document(document_id: str) -> list[Any]:
    from app.core.clauses import clauses_for_document as _clauses

    return [
        ClauseCandidate.model_validate(c)
        for c in _clauses(document_id)
    ]


def extraction_debug(document_id: str) -> dict[str, Any]:
    snapshot = get_db().collection("extraction_debug").document(document_id).get()
    return snapshot.to_dict() or {}


def rejected_for_document(document_id: str) -> list[dict[str, Any]]:
    return extraction_debug(document_id).get("rejected", [])


def llm_calls_for_document(document_id: str) -> list[dict[str, Any]]:
    # Vertex call records live in Cloud Logging (jsonPayload.stage="extraction");
    # the debug view links out rather than duplicating them.
    debug = extraction_debug(document_id)
    if not debug:
        return []
    return [
        {
            "stage": "extraction",
            "parse_quality": debug.get("parse_quality"),
            "self_consistency": debug.get("self_consistency"),
            "trace_id": debug.get("trace_id"),
        }
    ]


def append_stage_log(
    document_id: str, stage: str, ok: bool, detail: dict[str, Any] | None = None
) -> None:
    """Pipeline bookkeeping, not a graph mutation: stage_log entries and status
    changes are operational state and are deliberately NOT graph_events — the
    knowledge-graph event for a document is `document_ingested`, written once at
    creation."""
    db = get_db()
    # A server-timestamp sentinel cannot live inside an ArrayUnion transform,
    # so stage-log entries carry a client-side UTC stamp instead.
    from datetime import UTC, datetime

    entry: dict[str, Any] = {
        "stage": stage,
        "ok": ok,
        "at": datetime.now(UTC),
    }
    if detail:
        entry["detail"] = detail
    db.collection(COLLECTION).document(document_id).set(
        {
            "stage_log": firestore.ArrayUnion([entry]),
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def set_status(
    document_id: str,
    status: DocumentStatus,
    *,
    error: str | None = None,
    failed_stage: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "status": str(status),
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if error is not None:
        payload["error"] = error
    if failed_stage is not None:
        payload["failed_stage"] = failed_stage
    if extra:
        payload.update(extra)
    db = get_db()
    db.collection(COLLECTION).document(document_id).set(payload, merge=True)
