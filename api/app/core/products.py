"""Product (compliance twin) operations.

Plain functions over the repository. Nothing here knows about FastAPI or ADK.
"""

from __future__ import annotations

import logging
from typing import Any

from google.cloud import firestore

from app.core.normalization import normalize_substance
from app.core.repository import events_for, new_id, write_with_event
from app.db import get_db
from app.models import WORKSPACE_ID, EventType, Ingredient, Product, ProductIn, ProductPatch
from app.observability import log

logger = logging.getLogger(__name__)

COLLECTION = "products"


def _normalize_ingredients(ingredients: list[Ingredient]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ingredient in ingredients:
        normalized, unmatched = normalize_substance(ingredient.name)
        out.append(
            {
                "name": ingredient.name,
                "normalized": normalized,
                "unnormalized": unmatched,
                "amount": ingredient.amount,
                "unit": str(ingredient.unit) if ingredient.unit else None,
            }
        )
    return out


def _to_product(doc_id: str, data: dict[str, Any]) -> Product:
    return Product.model_validate({**data, "id": doc_id})


def create_product(payload: ProductIn) -> Product:
    product_id = new_id("prod")
    record = {
        "workspace_id": WORKSPACE_ID,
        "name": payload.name,
        "product_type": str(payload.product_type),
        "origin": payload.origin.upper(),
        "packaging": payload.packaging,
        "ingredients": _normalize_ingredients(payload.ingredients),
        "target_markets": payload.target_markets,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    write_with_event(
        COLLECTION,
        product_id,
        record,
        event_type=EventType.PRODUCT_CREATED,
        entity_type="product",
        after={k: v for k, v in record.items() if k not in {"created_at", "updated_at"}},
    )
    log(logger, logging.INFO, "product created", product_id=product_id)
    return get_product(product_id)  # type: ignore[return-value]


def get_product(product_id: str) -> Product | None:
    snapshot = get_db().collection(COLLECTION).document(product_id).get()
    if not snapshot.exists:
        return None
    return _to_product(snapshot.id, snapshot.to_dict())


def list_products(limit: int = 50) -> list[Product]:
    docs = get_db().collection(COLLECTION).limit(limit).stream()
    products = [_to_product(doc.id, doc.to_dict()) for doc in docs]
    products.sort(key=lambda p: p.created_at or 0, reverse=True)
    return products


def update_product(product_id: str, patch: ProductPatch) -> Product | None:
    existing = get_product(product_id)
    if existing is None:
        return None

    changes: dict[str, Any] = {}
    for field in ("name", "origin", "packaging", "target_markets"):
        value = getattr(patch, field)
        if value is not None:
            changes[field] = value.upper() if field == "origin" else value
    if patch.product_type is not None:
        changes["product_type"] = str(patch.product_type)
    if patch.ingredients is not None:
        changes["ingredients"] = _normalize_ingredients(patch.ingredients)

    if not changes:
        return existing

    before = existing.model_dump(mode="json", include=set(changes))
    write_with_event(
        COLLECTION,
        product_id,
        {**changes, "updated_at": firestore.SERVER_TIMESTAMP},
        event_type=EventType.PRODUCT_UPDATED,
        entity_type="product",
        before=before,
        after=changes,
        merge=True,
    )
    return get_product(product_id)


def product_events(product_id: str) -> list[dict[str, Any]]:
    return events_for(product_id)
