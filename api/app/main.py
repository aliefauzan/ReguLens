"""API service entrypoint.

Publishes to Pub/Sub synchronously and returns; it never does extraction work
itself. That belongs to the worker.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import documents as documents_core
from app.core import markets, products, query
from app.db import get_db, health_check
from app.models import DocumentIn, ProductIn, ProductPatch, QueryIn, SourceType
from app.observability import configure_logging, get_trace_id, log, set_trace_id
from app.settings import get_settings
from app.tracing import instrument

settings = get_settings()
configure_logging(settings.log_level, settings.service_name)
logger = logging.getLogger(__name__)

app = FastAPI(title="ReguLens API", version=settings.version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
instrument(app, settings.project_id)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """Adopt an inbound trace_id or mint one, and echo it back on every response
    so a caller can quote it when something goes wrong."""
    trace_id = set_trace_id(request.headers.get("x-trace-id"))
    log(logger, logging.INFO, "request", method=request.method, path=request.url.path)
    response = await call_next(request)
    response.headers["x-trace-id"] = trace_id
    return response


@app.get("/health")
def health() -> JSONResponse:
    try:
        firestore_status = health_check()
    except Exception as exc:  # noqa: BLE001 - health must report, not raise
        log(logger, logging.ERROR, "firestore health check failed", error=str(exc)
        )
        firestore_status = "error"
    body = {
        "status": "ok" if firestore_status == "ok" else "degraded",
        "version": settings.version,
        "firestore": firestore_status,
        "trace_id": get_trace_id(),
    }
    return JSONResponse(body, status_code=200 if firestore_status == "ok" else 503)


@app.get("/markets")
def get_markets() -> dict:
    return {"markets": markets.list_markets(), "trace_id": get_trace_id()}


@app.post("/markets/seed")
def post_markets_seed() -> dict:
    return {"markets": markets.seed_markets(), "trace_id": get_trace_id()}


@app.get("/substances")
def get_substances() -> dict:
    """The substance dictionary, so the UI can offer the names that will
    actually match a clause.

    An ingredient the dictionary does not know is flagged `unnormalized` and
    matches nothing, which looks exactly like "no problems found". Letting a
    user pick from the known set up front is the cheapest way to avoid that
    false negative, so this is a product feature, not a convenience.
    """
    from app.core.normalization import SYNONYMS

    return {
        "substances": [
            {
                "canonical": canonical,
                # The first synonym is the plain-English name in every entry.
                "label": synonyms[0],
                "synonyms": synonyms,
            }
            for canonical, synonyms in sorted(SYNONYMS.items())
        ],
        "trace_id": get_trace_id(),
    }


@app.post("/products", status_code=201)
def create_product(payload: ProductIn) -> dict:
    product = products.create_product(payload)
    return {"product": product.model_dump(mode="json"), "trace_id": get_trace_id()}


@app.get("/products")
def list_products() -> dict:
    return {
        "products": [p.model_dump(mode="json") for p in products.list_products()],
        "trace_id": get_trace_id(),
    }


@app.get("/products/{product_id}")
def get_product(product_id: str) -> dict:
    product = products.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    return {"product": product.model_dump(mode="json"), "trace_id": get_trace_id()}


@app.patch("/products/{product_id}")
def patch_product(product_id: str, payload: ProductPatch) -> dict:
    product = products.update_product(product_id, payload)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    return {"product": product.model_dump(mode="json"), "trace_id": get_trace_id()}


@app.get("/products/{product_id}/events")
def get_product_events(product_id: str) -> dict:
    if products.get_product(product_id) is None:
        raise HTTPException(status_code=404, detail="product not found")
    return {"events": products.product_events(product_id), "trace_id": get_trace_id()}


@app.get("/products/{product_id}/compliance")
def get_product_compliance(
    product_id: str,
    market_id: str | None = None,
) -> dict:
    """Readiness view: requirements + evaluations + issue counts per market."""
    from app.core.impact import rollup_status

    if products.get_product(product_id) is None:
        raise HTTPException(status_code=404, detail="product not found")

    from google.cloud import firestore

    from app.db import get_db

    reqs = [
        d.to_dict() | {"id": d.id}
        for d in (
            get_db()
            .collection("requirements")
            .where(filter=firestore.FieldFilter("product_id", "==", product_id))
            .limit(200)
            .stream()
        )
    ]
    if market_id:
        reqs = [r for r in reqs if r.get("market_id") == market_id]
    statuses = rollup_status(product_id)
    issues = sum(
        1 for r in reqs
        if r.get("evaluation") in {"fail", "needs_review"}
    )
    critical = sum(1 for r in reqs if r.get("evaluation") == "fail")
    return {
        "statuses": statuses,
        "requirements": reqs,
        "issue_counts": {"total": issues, "critical": critical},
        "trace_id": get_trace_id(),
    }


@app.get("/alerts")
def list_alerts() -> dict:
    """Unacknowledged `product_status_changed` events where the status worsened."""
    from google.cloud import firestore

    severity_order = {
        "unknown": 0,
        "attention_required": 1,
        "compliant": 1,
        "non_compliant": 2,
    }
    events = (
        get_db()
        .collection("graph_events")
        .where(filter=firestore.FieldFilter("event_type", "==", "product_status_changed"))
        .limit(50)
        .stream()
    )
    alerts = []
    for d in events:
        e = d.to_dict() | {"id": d.id}
        after = (e.get("after") or {}).get("status")
        before = (e.get("before") or {}).get("status")
        if severity_order.get(after, 0) > severity_order.get(before, 0) and not e.get("acknowledged"):
            alerts.append(e)
    alerts.sort(key=lambda e: e.get("occurred_at") or 0, reverse=True)
    return {"alerts": alerts[:20], "trace_id": get_trace_id()}


@app.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str) -> dict:
    get_db().collection("graph_events").document(alert_id).set(
        {"acknowledged": True}, merge=True
    )
    return {"status": "acked", "trace_id": get_trace_id()}


@app.post("/query")
def post_query(payload: QueryIn) -> dict:
    result = query.ask(payload.question, payload.product_id)
    return {**result, "trace_id": get_trace_id()}


@app.post("/documents", status_code=202)
def create_document(
    source_type: SourceType = Form(...),  # noqa: B008 - FastAPI DI pattern
    source_name: str = Form(..., min_length=1, max_length=200),  # noqa: B008
    jurisdiction: str = Form(..., min_length=2, max_length=16),  # noqa: B008
    declared_effective_date: str | None = Form(default=None, max_length=10),  # noqa: B008
    file: UploadFile | None = File(default=None),  # noqa: B008
    text: str | None = Form(default=None),  # noqa: B008
) -> JSONResponse:
    """Upload a PDF or paste text. Returns 202 immediately; extraction is the
    worker's job. An identical re-upload short-circuits to the cached document."""
    import io

    content_bytes: bytes | None = None
    page_count: int | None = None
    text_content: str | None = (text or None)
    filename: str | None = None
    storage_uri: str | None = None
    preview: str | None = None
    char_count = len(text_content) if text_content else 0

    if file is not None and (file.filename or ""):
        filename = file.filename[:200]
        raw = file.file.read()
        if len(raw) > settings.max_document_mb * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"file exceeds {settings.max_document_mb} MB",
            )
        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                page_count = len(pdf.pages)
                first_page_text = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
        except Exception as exc:  # noqa: BLE001 - a bad PDF is a client error
            raise HTTPException(status_code=422, detail=f"could not read PDF: {exc}") from exc
        if page_count > settings.max_document_pages:
            raise HTTPException(
                status_code=413,
                detail=f"document has {page_count} pages; limit is {settings.max_document_pages}",
            )
        content_bytes = raw
        preview = first_page_text
        char_count = len(first_page_text)

        try:
            from app.storage import upload

            storage_uri = upload(
                f"documents/{get_trace_id()}/{filename}",
                raw,
                file.content_type or "application/pdf",
            )
        except Exception as exc:  # noqa: BLE001 - storage failure is server-side
            log(logger, logging.ERROR, "gcs upload failed", error=str(exc))
            raise HTTPException(status_code=502, detail="could not store the uploaded file") from exc

    if content_bytes is None and text_content is None:
        raise HTTPException(status_code=422, detail="provide a PDF file or pasted text")

    meta = DocumentIn(
        source_type=source_type,
        source_name=source_name,
        jurisdiction=jurisdiction,
        declared_effective_date=declared_effective_date,
        filename=filename,
    )
    document, cached = documents_core.create_document(
        meta=meta,
        content_bytes=content_bytes,
        text=text_content,
        page_count=page_count,
        text_preview=preview,
        char_count=char_count,
        storage_uri=storage_uri,
        trace_id=get_trace_id(),
    )
    status_code = 200 if cached else 202
    body = {
        "document": document.model_dump(mode="json"),
        "cached": cached,
        "trace_id": get_trace_id(),
    }
    return JSONResponse(body, status_code=status_code)


@app.get("/documents")
def list_documents() -> dict:
    docs = documents_core.list_documents()
    return {
        "documents": [d.model_dump(mode="json") for d in docs],
        "trace_id": get_trace_id(),
    }


@app.get("/documents/{document_id}")
def get_document(document_id: str) -> dict:
    doc = documents_core.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    clauses = documents_core.clauses_for_document(document_id)
    return {
        "document": doc.model_dump(mode="json"),
        "clauses": [c.model_dump(mode="json") for c in clauses],
        "trace_id": get_trace_id(),
    }


@app.post("/documents/{document_id}/retry", status_code=202)
def retry_document(document_id: str) -> dict:
    doc = documents_core.retry_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return {"document": doc.model_dump(mode="json"), "trace_id": get_trace_id()}


@app.get("/debug/documents/{document_id}")
def debug_document(document_id: str) -> dict:
    """Every decision the pipeline made about one document — including the
    rejected candidates. Behind `DEBUG_VIEW`; it demonstrates the
    code-gates-the-model claim instead of asserting it."""
    if not settings.debug_view:
        raise HTTPException(status_code=404, detail="not found")
    doc = documents_core.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return {
        "document": doc.model_dump(mode="json"),
        "clauses": [c.model_dump(mode="json") for c in documents_core.clauses_for_document(document_id)],
        "rejected_candidates": documents_core.rejected_for_document(document_id),
        "llm_calls": documents_core.llm_calls_for_document(document_id),
        "events": documents_core.events_for_document(document_id),
        "trace_id": get_trace_id(),
    }


@app.post("/internal/adk-smoke")
async def adk_smoke() -> dict:
    """Phase-0 exit criterion: prove ADK runs in the deployed environment."""
    from app.adk.agent import run_smoke_test

    return await run_smoke_test()


@app.get("/clauses")
def list_clauses(
    jurisdiction: str | None = None,
    substance: str | None = None,
    status: str | None = None,
) -> dict:
    from app.core.clauses import query_clauses

    # Single-field filters only (no composite indexes in the MVP); the
    # jurisdiction refinement happens in-process over a bounded result set.
    clauses = query_clauses(substance=substance, status=status)
    if jurisdiction:
        clauses = [c for c in clauses if str(c.get("jurisdiction") or "").upper() == jurisdiction.upper()]
    return {"clauses": clauses, "trace_id": get_trace_id()}


@app.get("/conflicts")
def list_conflicts() -> dict:
    from google.cloud import firestore

    from app.db import get_db

    docs = (
        get_db()
        .collection("conflicts")
        .where(filter=firestore.FieldFilter("status", "==", "open"))
        .limit(50)
        .stream()
    )
    conflicts = [d.to_dict() | {"id": d.id} for d in docs]
    return {"conflicts": conflicts, "trace_id": get_trace_id()}


@app.post("/clauses/{clause_id}/confirm", status_code=200)
def confirm_review_clause(clause_id: str) -> dict:
    """The needs_review queue's single action: promote to active."""
    from app.core.reconciliation import confirm_clause

    result = confirm_clause(clause_id)
    if result is None:
        raise HTTPException(status_code=404, detail="clause not found")
    return {"result": result, "trace_id": get_trace_id()}
