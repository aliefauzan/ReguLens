"""One-click demo data.

Seeds the same baseline the Cloud Run Job seeds, but through the API's own
async path: the document is published to Pub/Sub and the worker extracts it,
exactly as it would for a document a user uploaded. Nothing is written
straight into `clauses` or `requirements`.

Idempotent twice over — the product is looked up by name, and an identical
re-ingest short-circuits on the content hash — so a user who presses the
button twice gets the same workspace, not a second copy.
"""

from __future__ import annotations

import logging

from app.core import markets
from app.core.documents import create_document
from app.core.products import create_product, list_products
from app.core.samples import BPOM_EXCERPT, DEMO_PRODUCT, DEMO_PRODUCT_NAME
from app.models import DocumentIn, Product, ProductIn, RegulatoryDocument, SourceType
from app.observability import get_trace_id, log

logger = logging.getLogger(__name__)


def seed_demo() -> tuple[Product, RegulatoryDocument, bool]:
    """Create the demo product and ingest the Indonesian rule for it.

    Returns `(product, document, cached)`. `cached=False` means extraction was
    just queued and the document is still on its way through the pipeline.

    Only the Indonesian rule is seeded. The EU rule is left for the user to add
    themselves, because watching a verdict change is the point of the product
    and it cannot be watched if it already happened.
    """
    markets.seed_markets()

    existing = next((p for p in list_products() if p.name == DEMO_PRODUCT_NAME), None)
    product = existing if existing is not None else create_product(ProductIn(**DEMO_PRODUCT))

    document, cached = create_document(
        meta=DocumentIn(
            source_type=SourceType.OFFICIAL_REGULATION,
            source_name="BPOM Perka 11/2019",
            jurisdiction="ID_BPOM",
        ),
        text=BPOM_EXCERPT,
        trace_id=get_trace_id(),
    )
    log(
        logger,
        logging.INFO,
        "demo seeded",
        product_id=product.id,
        document_id=document.id,
        cached=cached,
        reused_product=existing is not None,
    )
    return product, document, cached
