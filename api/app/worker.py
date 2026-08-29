"""Worker service entrypoint.

Every route here consumes a Pub/Sub *push* envelope. Push, not pull, and the
same shape locally as in production — the plan is explicit that a system which
pushes in one environment and polls in the other is not being tested.

Ack semantics:
- 2xx acks. A malformed message acks: redelivering it forever helps nobody.
- 5xx nacks: Pub/Sub redelivers with backoff, and after max-delivery-attempts
  the message lands in the dead-letter topic.
- Permanent failures never nack — they mark the document `failed` and ack.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.core.extraction.pipeline import (
    PermanentExtractionError,
    TransientExtractionError,
    run_extraction,
    run_extraction_via_agent,
)
from app.messaging import already_processed, mark_processed, parse_push_request
from app.models import DocumentStatus
from app.observability import configure_logging, get_trace_id, log, set_trace_id
from app.settings import get_settings
from app.tracing import instrument

settings = get_settings()
configure_logging(settings.log_level, "regulens-worker")
logger = logging.getLogger(__name__)

app = FastAPI(title="ReguLens Worker", version=settings.version)
instrument(app, settings.project_id)

HANDLER_EXTRACT = "extract"
HANDLER_RECONCILE = "reconcile"
HANDLER_IMPACT = "impact"

# Every consumer here is `async def` because a push envelope has to be awaited,
# but the work behind it — Firestore, embeddings, Gemini — is blocking and
# synchronous. Called directly it holds the event loop, so one instance handled
# one clause at a time no matter how many Pub/Sub deliveries were in flight, and
# a document's clauses reconciled in single file. `run_in_threadpool` hands each
# one to a worker thread and lets the fan-out Pub/Sub already provides be real.


@app.post("/internal/graph-changed")
async def graph_changed(request: Request) -> JSONResponse:
    """`graph.changed` consumer: re-run impact for the changed clause."""
    try:
        envelope = parse_push_request(await request.json())
    except Exception as exc:  # noqa: BLE001
        log(logger, logging.ERROR, "unparseable push envelope", error=str(exc))
        return JSONResponse({"status": "dropped"}, status_code=200)

    set_trace_id(envelope.trace_id)
    payload = envelope.payload
    clause_id = payload.get("clause_id") or payload.get("entity_id")
    if not clause_id:
        return JSONResponse({"status": "dropped"}, status_code=200)
    if already_processed(HANDLER_IMPACT, envelope.message_id):
        return JSONResponse({"status": "duplicate"}, status_code=200)

    from app.core.impact import run_impact

    summary = await run_in_threadpool(run_impact, str(clause_id), payload.get("document_id"))
    mark_processed(HANDLER_IMPACT, envelope.message_id)
    return JSONResponse({"status": "ok", "summary": summary["products"]})


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": settings.version, "service": "worker"}


@app.post("/internal/document-uploaded")
async def document_uploaded(request: Request) -> JSONResponse:
    """`document.uploaded` consumer: run extraction for the referenced document."""
    try:
        envelope = parse_push_request(await request.json())
    except Exception as exc:  # noqa: BLE001 - unparseable will never parse
        log(logger, logging.ERROR, "unparseable push envelope", error=str(exc))
        return JSONResponse({"status": "dropped"}, status_code=200)

    set_trace_id(envelope.trace_id)
    message_id = envelope.message_id
    payload = envelope.payload
    document_id = str(payload.get("document_id") or "")
    if not document_id:
        # Nothing actionable; record and ack rather than burn five retries.
        log(logger, logging.ERROR, "message missing document_id", message_id=message_id)
        return JSONResponse({"status": "dropped"}, status_code=200)

    if already_processed(HANDLER_EXTRACT, message_id):
        return JSONResponse({"status": "duplicate"}, status_code=200)
    log(
        logger, logging.INFO, "handling document.uploaded",
        message_id=message_id, document_id=document_id,
    )

    try:
        if settings.fake_llm:
            result = await run_in_threadpool(run_extraction, document_id)
        else:
            result = await run_extraction_via_agent(document_id)
    except PermanentExtractionError as exc:
        _fail(document_id, stage="extracting", error=str(exc))
        return JSONResponse({"status": "failed_permanent", "error": str(exc)}, status_code=200)
    except TransientExtractionError as exc:
        # Nack: Pub/Sub redelivers; DLQ after max attempts (handled by
        # /internal/dead-letter).
        log(
            logger, logging.WARNING, "nack transient",
            document_id=document_id, error=str(exc),
        )
        _fail(document_id, stage="extracting", error=f"transient: {exc}", failed=False)
        return JSONResponse({"status": "retry_later"}, status_code=500)

    if not result.skipped:
        mark_processed(HANDLER_EXTRACT, message_id)
    return JSONResponse(
        {
            "status": "skipped" if result.skipped else "ok",
            "document_id": document_id,
            "accepted": result.accepted,
            "rejected": len(result.rejected),
            "trace_id": get_trace_id(),
        },
        status_code=200,
    )


@app.post("/internal/clause-extracted")
async def clause_extracted(request: Request) -> JSONResponse:
    """`clause.extracted` consumer: run reconciliation for one clause."""
    try:
        envelope = parse_push_request(await request.json())
    except Exception as exc:  # noqa: BLE001
        log(logger, logging.ERROR, "unparseable push envelope", error=str(exc))
        return JSONResponse({"status": "dropped"}, status_code=200)

    set_trace_id(envelope.trace_id)
    clause_id = str(envelope.payload.get("clause_id") or "")
    if not clause_id:
        log(logger, logging.ERROR, "message missing clause_id", message_id=envelope.message_id)
        return JSONResponse({"status": "dropped"}, status_code=200)
    if already_processed(HANDLER_RECONCILE, envelope.message_id):
        return JSONResponse({"status": "duplicate"}, status_code=200)

    from app.core.reconciliation import (
        PermanentReconcileError,
        TransientReconcileError,
        reconcile_clause,
    )

    try:
        result = await run_in_threadpool(reconcile_clause, clause_id)
    except PermanentReconcileError as exc:
        log(logger, logging.ERROR, "reconcile permanent failure",
            clause_id=clause_id, error=str(exc)[:300])
        return JSONResponse({"status": "failed_permanent"}, status_code=200)
    except TransientReconcileError as exc:
        log(logger, logging.WARNING, "nack transient reconcile",
            clause_id=clause_id, error=str(exc)[:300])
        return JSONResponse({"status": "retry_later"}, status_code=500)

    # Debug-view record: every guardrail decision for this clause.
    if result.get("decisions"):
        from google.cloud import firestore

        from app.db import get_db

        get_db().collection("extraction_debug").document(
            str(result.get("document_id") or clause_id)
        ).set(
            {"reconciliations": firestore.ArrayUnion([result])},
            merge=True,
        )

    if result.get("status") != "skipped":
        # Self-check: two simultaneous deliveries of DIFFERENT messages can
        # both no-op inside their transactions and ack, leaving the clause
        # stuck pending. Force a redelivery rather than lose it silently.
        from app.db import get_db as _get_db

        fresh = _get_db().collection("clauses").document(clause_id).get()
        if fresh.exists and fresh.to_dict().get("status") == "pending_reconciliation":
            log(logger, logging.WARNING, "reconcile_left_pending", clause_id=clause_id)
            return JSONResponse({"status": "retry_later"}, status_code=500)
        mark_processed(HANDLER_RECONCILE, envelope.message_id)
    return JSONResponse({"status": result.get("status"), "clause_id": clause_id})


@app.post("/internal/check-sources")
async def check_sources(request: Request) -> JSONResponse:
    """The scheduled sweep. Cloud Scheduler calls this once a day with an OIDC
    token; the worker is `--no-allow-unauthenticated`, so nothing else can.

    This lives on the worker rather than the API for the same reason extraction
    does: it is slow, it is nobody's request, and a fetch that hangs must not
    hold a user-facing instance. It returns 200 even when individual sources
    fail — a broken regulator site is recorded on the source and shown in the
    UI, and asking Cloud Scheduler to retry it in five minutes would not fix it.

    A body is optional. `{"source_id": "..."}` checks one; `{"force": true}`
    ignores each source's interval.
    """
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - Cloud Scheduler may send no body at all
        body = {}
    if not isinstance(body, dict):
        body = {}

    set_trace_id(str(body.get("trace_id") or "") or None)
    force = bool(body.get("force"))
    source_id = str(body.get("source_id") or "")

    from app.core import sources

    if source_id:
        result = await run_in_threadpool(sources.check_source, source_id, force=True)
        return JSONResponse({"results": [result], "trace_id": get_trace_id()}, status_code=200)

    summary = await run_in_threadpool(sources.check_all, force=force)
    return JSONResponse(summary | {"trace_id": get_trace_id()}, status_code=200)


@app.post("/internal/dead-letter")
async def dead_letter(request: Request) -> JSONResponse:
    """The DLQ push target. When a `document.uploaded` message exhausts its
    retries, Pub/Sub forwards it here; we surface the document as `failed`
    instead of leaving it stuck mid-pipeline silently."""
    try:
        body = await request.json()
        envelope = parse_push_request(body)
    except Exception as exc:  # noqa: BLE001 - a DLQ envelope we cannot parse is logged, not looped
        log(logger, logging.ERROR, "unparseable dead-letter envelope", error=str(exc))
        return JSONResponse({"status": "dropped"}, status_code=200)

    # The forwarded message's own attributes ride along on the delivery.
    original = getattr(envelope.message, "attributes", {}) or {}
    inner_data = {}
    try:
        import base64
        import json

        raw = getattr(envelope.message, "data", None)
        if isinstance(raw, str) and raw:
            inner_data = json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception:  # noqa: BLE001 - best-effort decode only
        pass

    document_id = str(inner_data.get("document_id") or original.get("document_id") or "")
    set_trace_id(original.get("trace_id"))
    if document_id:
        _fail(document_id, stage="extracting", error="delivery exhausted; moved to dead letter")
    else:
        log(logger, logging.ERROR, "dead-letter without document id", attributes=dict(original))
    return JSONResponse({"status": "recorded"}, status_code=200)


def _fail(
    document_id: str,
    *,
    stage: str,
    error: str,
    failed: bool = True,
) -> None:
    """Mark a document failed (or just log for transient states)."""
    from app.core.documents import append_stage_log, set_status

    if failed:
        set_status(document_id, DocumentStatus.FAILED, error=error, failed_stage=stage)
        append_stage_log(document_id, stage, ok=False, detail={"error": error[:500]})
    log(
        logger,
        logging.ERROR if failed else logging.WARNING,
        "document failure recorded" if failed else "transient failure",
        document_id=document_id, stage=stage, error=error[:500],
    )
