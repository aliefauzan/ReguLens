"""Worker service entrypoint.

Every route here consumes a Pub/Sub *push* envelope. Push, not pull, and the
same shape locally as in production — the plan is explicit that a system which
pushes in one environment and polls in the other is not being tested.

Ack semantics: return 2xx to ack, 5xx to nack and get redelivered. A malformed
message is acked, because redelivering it forever helps nobody; it goes to the
dead-letter path by way of the delivery attempt count instead.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.cloud import firestore

from app.db import get_db
from app.messaging import already_processed, mark_processed, parse_push_request
from app.observability import configure_logging, get_trace_id, log, set_trace_id
from app.settings import get_settings
from app.tracing import instrument

settings = get_settings()
configure_logging(settings.log_level, "regulens-worker")
logger = logging.getLogger(__name__)

app = FastAPI(title="ReguLens Worker", version=settings.version)
instrument(app, settings.project_id)

HANDLER = "echo"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": settings.version, "service": "worker"}


@app.post("/internal/document-uploaded")
async def document_uploaded(request: Request) -> JSONResponse:
    """The phase-0 round-trip proof: a published message becomes a Firestore
    record, written by the deployed worker."""
    try:
        envelope = parse_push_request(await request.json())
    except Exception as exc:  # noqa: BLE001
        # Ack: a message we cannot parse will never parse.
        log(logger, logging.ERROR, "unparseable push envelope", error=str(exc))
        return JSONResponse({"status": "dropped"}, status_code=200)

    set_trace_id(envelope.trace_id)
    message_id = envelope.message_id

    if already_processed(HANDLER, message_id):
        return JSONResponse({"status": "duplicate"}, status_code=200)

    payload = envelope.payload
    log(
        logger, logging.INFO, "handling document.uploaded",
        message_id=message_id, payload_keys=sorted(payload),
    )

    get_db().collection("echo_events").document(message_id or get_trace_id()).set(
        {
            "payload": payload,
            "trace_id": get_trace_id(),
            "message_id": message_id,
            "received_at": firestore.SERVER_TIMESTAMP,
        }
    )
    mark_processed(HANDLER, message_id)
    return JSONResponse({"status": "ok", "trace_id": get_trace_id()}, status_code=200)
