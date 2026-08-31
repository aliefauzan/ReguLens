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


def ensure_market(
    *, country_code: str, country_name: str, regulator: str | None = None
) -> tuple[str, bool]:
    """Make sure a market speaks for this country. Returns `(market_id, created)`.

    Discovery calls this before it commits a source, and the reason is load
    bearing rather than tidy. `impact.evaluate` skips any clause whose
    jurisdiction is not listed by some market, and `relevance` does the same on
    read. A watched source registered for a country with no market row would
    ingest regulations perfectly and produce no verdict anywhere — a green row
    in the source list and silence in the console.

    Idempotent, and careful with a market that already exists: Indonesia ships
    with `jurisdictions: ["ID_BPOM"]`, so discovering ID must *add* to that list
    rather than replace it. A market's regimes accumulate; nothing here removes
    one.

    `regulator` is optional because a market can exist before anybody has found
    who writes its rules: a user selling into France says so on the product
    long before discovery names ANSES. Such a market carries no source and no
    clause, so every verdict for it reads `unknown` — which is the truth, and
    is why it must exist rather than be dropped on the floor.
    """
    code = country_code.strip().upper()
    market_id = f"market_{code.lower()}"
    db = get_db()
    ref = db.collection(COLLECTION).document(market_id)
    snapshot = ref.get()
    existing = snapshot.to_dict() or {} if snapshot.exists else {}

    jurisdictions = [str(j) for j in existing.get("jurisdictions") or []]
    created = not snapshot.exists
    if code not in jurisdictions:
        jurisdictions.append(code)

    record = {
        # `list_markets` orders by the `id` field, and Firestore omits any
        # document that does not carry the field it is ordered by. A market
        # written without it exists and is invisible — which is the exact
        # failure this function was added to prevent, one level down.
        "id": market_id,
        "country": existing.get("country") or country_name,
        "country_code": code,
        "jurisdictions": jurisdictions,
        "label": existing.get("label")
        or (f"{country_name} — {regulator}" if regulator else country_name),
        "regulator": existing.get("regulator") or regulator,
        # "Discovered" means a model went and found this country's regulator.
        # A market created from the product form because somebody sells there
        # has found nothing, and must not claim it did.
        "discovered": existing.get("discovered", created and regulator is not None),
    }
    ref.set(record, merge=True)
    log(
        logger,
        logging.INFO,
        "market ensured",
        market_id=market_id,
        created=created,
        jurisdictions=jurisdictions,
    )
    return market_id, created


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
