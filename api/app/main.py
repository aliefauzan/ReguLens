"""API service entrypoint.

Publishes to Pub/Sub synchronously and returns; it never does extraction work
itself. That belongs to the worker.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import markets, products
from app.db import health_check
from app.models import ProductIn, ProductPatch
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
        log(logger, logging.ERROR, "firestore health check failed", error=str(exc))
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


@app.post("/internal/adk-smoke")
async def adk_smoke() -> dict:
    """Phase-0 exit criterion: prove ADK runs in the deployed environment."""
    from app.adk.agent import run_smoke_test

    return await run_smoke_test()
