"""Markets — the trivial real payload that proves the delivery path in phase 0.

Plain functions. No FastAPI types, no ADK types. Everything in `core/` must be
importable and testable without a web server or an agent framework.
"""

from __future__ import annotations

import logging

from google.cloud import firestore

from app.db import get_db
from app.observability import log

logger = logging.getLogger(__name__)

COLLECTION = "markets"

# The MVP ceiling is two markets; the plan says so and phase 1 depends on it.
SEED_MARKETS: list[dict] = [
    {
        "id": "market_de",
        "country": "Germany",
        "country_code": "DE",
        # A list because a market can inherit several regimes at once.
        "jurisdictions": ["EU"],
        "label": "European Union — Germany",
        "regulator": "European Commission",
    },
    {
        "id": "market_id",
        "country": "Indonesia",
        "country_code": "ID",
        "jurisdictions": ["ID_BPOM"],
        "label": "Indonesia — BPOM",
        "regulator": "Badan Pengawas Obat dan Makanan",
    },
]


def list_markets() -> list[dict]:
    docs = get_db().collection(COLLECTION).order_by("id").stream()
    return [doc.to_dict() | {"id": doc.id} for doc in docs]


def seed_markets() -> list[dict]:
    """Idempotent: writing the same seed twice leaves the same two documents."""
    db = get_db()
    batch = db.batch()
    for market in SEED_MARKETS:
        ref = db.collection(COLLECTION).document(market["id"])
        batch.set(ref, {**market, "seeded_at": firestore.SERVER_TIMESTAMP}, merge=True)
    batch.commit()
    log(logger, logging.INFO, "markets seeded", count=len(SEED_MARKETS))
    return list_markets()
