"""API service entrypoint.

Publishes to Pub/Sub synchronously and returns; it never does extraction work
itself. That belongs to the worker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import detection, markets, products, query
from app.core import documents as documents_core
from app.db import get_db, health_check
from app.models import (
    DocumentIn,
    LibraryLoadIn,
    ProductIn,
    ProductPatch,
    QueryIn,
    SourceType,
    WatchedSourceIn,
    WatchedSourcePatch,
)
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


@app.get("/substances/resolve")
def resolve_substance(q: str = "") -> dict:
    """What we think an ingredient name means, and what we will do about it.

    The strict matcher answers yes or no. This answers the "no" cases usefully:
    a misspelling gets the name offered back, a food gets told it is a food, and
    a genuinely unknown name gets told plainly that nothing will be checked
    against it — which is the sentence that stops a false pass reading like a
    real one.
    """
    from app.core import substances

    return substances.resolve(q).to_dict() | {"trace_id": get_trace_id()}


@app.get("/samples")
def get_samples() -> dict:
    """Regulation excerpts bundled with the app.

    Someone evaluating ReguLens rarely has a regulation PDF open. Without one
    they cannot reach any page that shows an answer, so the samples are part of
    the product, not a test fixture.
    """
    from app.core import samples

    return {"samples": samples.list_samples(), "trace_id": get_trace_id()}


@app.get("/library")
def get_library() -> dict:
    """The regulations we already hold, ready to read.

    This is the answer to "why do I have to add a regulation?". Two real
    regulations are in the repo; the library is a set of verbatim excerpts of
    them, so a user with no PDF of their own still gets a real answer.
    """
    from app.core import library

    return {
        "entries": library.list_entries(),
        "starter_ids": list(library.STARTER_IDS),
        "trace_id": get_trace_id(),
    }


@app.post("/library/load", status_code=202)
def post_library_load(payload: LibraryLoadIn | None = None) -> JSONResponse:
    """Read the named library entries, or the starter set when none are named.

    Each entry goes through the ordinary upload path — hash, store, publish,
    extract, reconcile — so nothing here can put a clause into the graph that an
    upload could not. Repeat calls short-circuit on the content hash.
    """
    from app.core import library

    results = library.load_entries(payload.ids if payload else None)
    unknown = [r["id"] for r in results if not r["found"]]
    if unknown and len(unknown) == len(results):
        raise HTTPException(status_code=404, detail=f"no such rules: {', '.join(unknown)}")
    queued = [r for r in results if r.get("found") and not r.get("cached")]
    return JSONResponse(
        {
            "results": results,
            "queued": len(queued),
            "already_read": sum(1 for r in results if r.get("cached")),
            "unknown": unknown,
            "trace_id": get_trace_id(),
        },
        # Nothing new to do is a completed request, not an accepted one.
        status_code=202 if queued else 200,
    )


@app.post("/demo/seed", status_code=202)
def post_demo_seed() -> JSONResponse:
    """Create the demo product and ingest one real rule for it.

    Returns 202: extraction runs on the worker, so the document arrives
    `uploaded` and the caller polls it like any other upload. Safe to call
    repeatedly — the product is matched by name and the document by content
    hash.
    """
    from app.core import demo

    product, document, cached = demo.seed_demo()
    return JSONResponse(
        {
            "product": product.model_dump(mode="json"),
            "document": document.model_dump(mode="json"),
            "cached": cached,
            "trace_id": get_trace_id(),
        },
        status_code=200 if cached else 202,
    )


@app.get("/stats/autonomy")
def get_autonomy() -> dict:
    """What ReguLens did without being asked, counted from stored records.

    Every figure is a query over the same collections that serve the rest of the
    app, so a number here can be clicked through to the thing it counts. A quiet
    week reports zeros — which is the ordinary case for a monitor, and the
    easiest number in this codebase to have inflated.
    """
    from app.core import autonomy

    return autonomy.summary() | {"trace_id": get_trace_id()}


@app.get("/sources")
def get_sources() -> dict:
    """The addresses ReguLens re-reads on a schedule, and what happened last time.

    Rendered rather than hidden because the honest claim depends on it: a source
    that has been erroring for a week means "we are not watching that", and the
    only place a user can find that out is here.
    """
    from app.core import sources

    return {
        "sources": [s.model_dump(mode="json") for s in sources.list_sources()],
        "default_interval_hours": settings.source_check_interval_hours,
        "trace_id": get_trace_id(),
    }


@app.post("/sources", status_code=201)
def post_source(payload: WatchedSourceIn) -> JSONResponse:
    """Start watching an address. Adding one already watched returns it as it
    stands, with 200 rather than 201."""
    from app.core import sources

    source, created = sources.add_source(payload)
    return JSONResponse(
        {"source": source.model_dump(mode="json"), "created": created, "trace_id": get_trace_id()},
        status_code=201 if created else 200,
    )


@app.patch("/sources/{source_id}")
def patch_source(source_id: str, payload: WatchedSourcePatch) -> dict:
    from app.core import sources

    source = sources.patch_source(source_id, payload)
    if source is None:
        raise HTTPException(status_code=404, detail="no such source")
    return {"source": source.model_dump(mode="json"), "trace_id": get_trace_id()}


@app.delete("/sources/{source_id}", status_code=200)
def delete_source(source_id: str) -> dict:
    """Stop watching. Documents already read from it stay — they are rules that
    verdicts cite, and removing one is a separate decision made on its own page."""
    from app.core import sources

    if not sources.delete_source(source_id):
        raise HTTPException(status_code=404, detail="no such source")
    return {"deleted": source_id, "trace_id": get_trace_id()}


@app.post("/sources/seed", status_code=201)
def post_sources_seed() -> dict:
    """Register the built-in watch list. Idempotent."""
    from app.core import sources

    return {"sources": sources.seed_sources(), "trace_id": get_trace_id()}


@app.post("/sources/{source_id}/check")
def post_source_check(source_id: str) -> dict:
    """Read one source now, ignoring the interval.

    Synchronous on purpose: a person who pressed "Check now" is waiting for the
    answer, and the answer takes one HTTP fetch and a hash comparison. Anything
    slow that follows — extraction, reconciliation, impact — is already behind
    Pub/Sub, exactly as it is for an upload.
    """
    from app.core import sources

    result = sources.check_source(source_id, force=True)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such source")
    return result | {"trace_id": get_trace_id()}


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


@app.delete("/products/{product_id}", status_code=200)
def delete_product(product_id: str) -> dict:
    """Remove a product and the requirements derived from it.

    Deliberately destructive and deliberately available: without it, a typo in
    an ingredient list is permanent for anyone who cannot reach Firestore. The
    `product_deleted` event survives the delete.
    """
    if not products.delete_product(product_id):
        raise HTTPException(status_code=404, detail="product not found")
    return {"deleted": product_id, "trace_id": get_trace_id()}


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
    from app.core.impact import rollup_status, upcoming_changes

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
    # What binds today, and the next date that answer changes. Both, because a
    # product that passes today and fails in March is neither "compliant" nor
    # "non_compliant" on its own, and picking one of those words would be a lie
    # in whichever direction it was picked.
    upcoming = upcoming_changes(product_id)
    if market_id:
        upcoming = {k: v for k, v in upcoming.items() if k == market_id}
    # One recipe, several markets: the number the product must actually meet is
    # the lowest one still in force. Omitted when the caller narrowed to a
    # single market, where "strictest across your markets" is not a question.
    binding = None
    if not market_id:
        from app.core.strictest import binding_limits

        binding = binding_limits(product_id)
    issues = sum(
        1 for r in reqs
        if r.get("evaluation") in {"fail", "needs_review"}
    )
    critical = sum(1 for r in reqs if r.get("evaluation") == "fail")
    return {
        "statuses": statuses,
        "upcoming": upcoming,
        "binding_limits": binding,
        "requirements": reqs,
        "issue_counts": {"total": issues, "critical": critical},
        "trace_id": get_trace_id(),
    }


@app.post("/simulate")
def simulate_product(payload: ProductIn) -> dict:
    """What-if: the verdict for a product nobody saved.

    Read-only by construction — it writes no document, emits no event and leaves
    no requirement row behind, so it can be called from a form as often as the
    form changes without putting anything in the audit trail.
    """
    from app.core.products import _normalize_ingredients
    from app.core.simulation import simulate

    product = payload.model_dump(mode="json")
    product["ingredients"] = _normalize_ingredients(payload.ingredients)
    result = simulate(product)
    return result | {"trace_id": get_trace_id()}


@app.get("/products/{product_id}/evidence")
def get_product_evidence(product_id: str) -> dict:
    """The pack somebody hands an auditor: every verdict, the rule behind it as
    the regulator wrote it, where that document came from, and its content hash.

    Read-only, assembled from stored records. Nothing here is signed — the
    hashes show the content has not changed, not who produced it.
    """
    from app.core.evidence import build

    try:
        pack = build(product_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="product not found") from None
    return pack | {"trace_id": get_trace_id()}


@app.get("/alerts")
def list_alerts() -> dict:
    """Unacknowledged worsening status changes, each carrying why it happened.

    The `context` on every alert is resolved from stored records — the causing
    document, the causing clause, the product and the market. It exists so the
    banner can say which regulation moved the verdict and whether anybody
    uploaded it, instead of only that something changed.
    """
    from app.core import alerts as alerts_core

    return {"alerts": alerts_core.list_alerts(), "trace_id": get_trace_id()}


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


@dataclass
class _Upload:
    """What we can learn from the bytes before anything is stored."""

    content_bytes: bytes | None = None
    text: str | None = None
    filename: str | None = None
    page_count: int | None = None
    preview: str | None = None
    head_text: str = ""
    char_count: int = 0


def _read_upload(file: UploadFile | None, text: str | None, *, store: bool) -> tuple[_Upload, str | None]:
    """Turn a multipart upload into text, once, for both endpoints.

    `store` is what separates a detection probe from a real upload: probing must
    not leave a file in the bucket for a document the user may never submit.
    """
    import io

    upload = _Upload(text=(text or None))
    upload.char_count = len(upload.text) if upload.text else 0
    if upload.text:
        upload.head_text = upload.text
    storage_uri: str | None = None

    if file is None or not (file.filename or ""):
        return upload, None

    upload.filename = file.filename[:200]
    raw = file.file.read()
    if len(raw) > settings.max_document_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds {settings.max_document_mb} MB",
        )
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            upload.page_count = len(pdf.pages)
            first_page_text = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
            # Detection reads a little further than the preview: a masthead can
            # sit on page 1 while the entry-into-force clause sits on page 3.
            head = [
                (page.extract_text() or "") for page in pdf.pages[: settings.detect_pages]
            ]
    except Exception as exc:  # noqa: BLE001 - a bad PDF is a client error
        raise HTTPException(status_code=422, detail=f"could not read PDF: {exc}") from exc
    if upload.page_count > settings.max_document_pages:
        raise HTTPException(
            status_code=413,
            detail=(
                f"This document has {upload.page_count} pages and we read up to "
                f"{settings.max_document_pages}. Paste the part that matters, or split it up."
            ),
        )
    upload.content_bytes = raw
    upload.preview = first_page_text
    upload.head_text = "\n".join(head)
    upload.char_count = len(first_page_text)

    if store:
        try:
            from app.storage import upload as storage_upload

            storage_uri = storage_upload(
                f"documents/{get_trace_id()}/{upload.filename}",
                raw,
                file.content_type or "application/pdf",
            )
        except Exception as exc:  # noqa: BLE001 - storage failure is server-side
            log(logger, logging.ERROR, "gcs upload failed", error=str(exc))
            raise HTTPException(status_code=502, detail="could not store the uploaded file") from exc

    return upload, storage_uri


@app.post("/documents/detect")
def detect_document(
    file: UploadFile | None = File(default=None),  # noqa: B008 - FastAPI DI pattern
    text: str | None = Form(default=None),  # noqa: B008
) -> dict:
    """Read a document's own words for the metadata the form used to demand.

    Stores nothing, publishes nothing, costs nothing: the user gets to see what
    we think their file is *before* deciding to submit it.
    """
    upload, _ = _read_upload(file, text, store=False)
    if not upload.head_text.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "We could not find any text in that file. A photo or a scan has no text "
                "in it to read, so paste the wording instead."
            ),
        )
    found = detection.detect(upload.head_text, upload.filename)
    log(
        logger,
        logging.INFO,
        "document detected",
        jurisdiction=found.jurisdiction.value,
        source_type=found.source_type.value,
        needs_confirmation=found.needs_confirmation,
    )
    return {
        "detection": found.to_dict(),
        "page_count": upload.page_count,
        "filename": upload.filename,
        "trace_id": get_trace_id(),
    }


@app.post("/documents", status_code=202)
def create_document(
    source_type: SourceType | None = Form(default=None),  # noqa: B008 - FastAPI DI pattern
    source_name: str | None = Form(default=None, max_length=200),  # noqa: B008
    jurisdiction: str | None = Form(default=None, max_length=16),  # noqa: B008
    declared_effective_date: str | None = Form(default=None, max_length=10),  # noqa: B008
    file: UploadFile | None = File(default=None),  # noqa: B008
    text: str | None = Form(default=None),  # noqa: B008
) -> JSONResponse:
    """Upload a PDF or paste text. Returns 202 immediately; extraction is the
    worker's job. An identical re-upload short-circuits to the cached document.

    Every metadata field is optional. Whatever the caller leaves out is read from
    the document itself; only an unreadable jurisdiction or source type is
    refused, because guessing either one would change what the clause is allowed
    to do downstream.
    """
    upload, storage_uri = _read_upload(file, text, store=True)

    if upload.content_bytes is None and upload.text is None:
        raise HTTPException(status_code=422, detail="provide a PDF file or pasted text")

    found = detection.detect(upload.head_text, upload.filename)
    resolved_type = source_type or (
        SourceType(found.source_type.value) if found.source_type.certain else None
    )
    resolved_jurisdiction = jurisdiction or (
        found.jurisdiction.value if found.jurisdiction.certain else None
    )
    if resolved_jurisdiction is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "We could not tell which country's rules this document sets out. "
                "Say which, and we will read the rest."
            ),
        )
    if resolved_type is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "We could not tell what kind of source this is. Say where it came from — "
                "that decides how much it is allowed to change."
            ),
        )
    resolved_name = source_name or found.source_name.value or resolved_jurisdiction
    resolved_date = declared_effective_date or found.effective_date.value

    meta = DocumentIn(
        source_type=resolved_type,
        source_name=resolved_name,
        jurisdiction=resolved_jurisdiction,
        declared_effective_date=resolved_date,
        filename=upload.filename,
    )
    document, cached = documents_core.create_document(
        meta=meta,
        content_bytes=upload.content_bytes,
        text=upload.text,
        page_count=upload.page_count,
        text_preview=upload.preview,
        char_count=upload.char_count,
        storage_uri=storage_uri,
        trace_id=get_trace_id(),
        detection=found.to_dict(),
        # What the user typed wins over what we read, and the document records
        # which of the two it was — a verdict traced back here must not have to
        # guess whether a human confirmed the jurisdiction.
        declared_fields=sorted(
            field
            for field, value in {
                "source_type": source_type,
                "source_name": source_name,
                "jurisdiction": jurisdiction,
                "declared_effective_date": declared_effective_date,
            }.items()
            if value
        ),
    )
    status_code = 200 if cached else 202
    body = {
        "document": document.model_dump(mode="json"),
        "cached": cached,
        "detection": found.to_dict(),
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


@app.delete("/documents/{document_id}", status_code=200)
def delete_document(document_id: str) -> dict:
    """Remove a document and everything derived from it.

    A product could always be deleted and the document you uploaded by mistake
    could not, so the wrong PDF stayed in the rulebook for good unless you had
    Firestore access. Clauses, the requirements they produced, the conflicts
    they opened and the debug record all go, and every affected product is
    re-evaluated — a delete that leaves a stale red verdict on screen is worse
    than no delete. The `document_deleted` event survives.
    """
    summary = documents_core.delete_document(document_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="document not found")
    return {"deleted": document_id, **summary, "trace_id": get_trace_id()}


@app.get("/documents/{document_id}/text")
def get_document_text(document_id: str) -> dict:
    """The document's own words, with each clause located inside them.

    This is what turns "where this came from" into something a reader can
    check: the passage, in place, in the document. A clause we cannot locate is
    reported as `not_found` rather than pointed at the nearest paragraph —
    highlighting the wrong sentence would be worse than highlighting none.
    """
    from app.core import citations

    doc = documents_core.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    text = doc.text_inline or doc.text_extracted or ""
    clauses = [c.model_dump(mode="json") for c in documents_core.clauses_for_document(document_id)]
    located = citations.locate_all(text, clauses)
    return {
        "document_id": document_id,
        "text": text,
        "source": "pasted" if doc.text_inline else "extracted",
        "truncated": bool(doc.text_truncated),
        # A document read before this endpoint existed kept only a 500-character
        # preview; say so rather than showing a stump as if it were the whole.
        "available": bool(text),
        "citations": [citation.to_dict() for citation in located],
        "trace_id": get_trace_id(),
    }


@app.post("/documents/{document_id}/retry", status_code=202)
def retry_document(document_id: str) -> dict:
    doc = documents_core.retry_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return {"document": doc.model_dump(mode="json"), "trace_id": get_trace_id()}


@app.post("/clauses/{clause_id}/dismiss", status_code=200)
def dismiss_review_clause(clause_id: str) -> dict:
    """The review queue's second action: reject without deleting.

    With only a confirm button, a clause the reader judged wrong sat in the
    queue forever and the count stopped meaning anything.
    """
    from app.core.reconciliation import dismiss_clause

    result = dismiss_clause(clause_id)
    if result is None:
        raise HTTPException(status_code=404, detail="clause not found")
    return {"result": result, "trace_id": get_trace_id()}


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
    relevant_only: bool = False,
) -> dict:
    """Clauses, optionally narrowed to the ones that could bear on this workspace.

    `relevant_only` never deletes and never downgrades. It is computed at read
    time from the products that exist right now, so a rule held back today
    applies to a product added tomorrow with no migration and no recompute. The
    response always carries `hidden` and `hidden_reasons`, because a list that
    quietly drops a hundred and forty rules is worse than a long one.
    """
    from app.core.clauses import query_clauses

    # Single-field filters only (no composite indexes in the MVP); the
    # jurisdiction refinement happens in-process over a bounded result set.
    clauses = query_clauses(substance=substance, status=status)
    if jurisdiction:
        clauses = [c for c in clauses if str(c.get("jurisdiction") or "").upper() == jurisdiction.upper()]

    hidden_reasons: dict[str, int] = {}
    if relevant_only:
        from app.core import relevance

        clauses, hidden_reasons = relevance.partition(clauses, relevance.current_workspace())
    return {
        "clauses": clauses,
        "hidden": sum(hidden_reasons.values()),
        "hidden_reasons": hidden_reasons,
        "trace_id": get_trace_id(),
    }


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
