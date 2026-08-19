"""Typed shapes for everything that touches Firestore.

Deterministic code owns every mutation. A model response never becomes a stored
document without passing through one of these validators first.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

WORKSPACE_ID = "ws_demo"


class ProductType(StrEnum):
    """An enum, not free text: the guardrail matches clause `product_type`
    against this, and free text would make every comparison a guess."""

    FOOD_BEVERAGE_POWDER = "food_beverage_powder"
    FOOD_BEVERAGE_LIQUID = "food_beverage_liquid"
    FOOD_SOLID = "food_solid"
    SUPPLEMENT = "supplement"
    COSMETIC = "cosmetic"


class Unit(StrEnum):
    PERCENT_W_W = "percent_w_w"
    MG_PER_KG = "mg_per_kg"
    PPM = "ppm"


class EventType(StrEnum):
    DOCUMENT_INGESTED = "document_ingested"
    CLAUSE_CREATED = "clause_created"
    CLAUSE_SUPERSEDED = "clause_superseded"
    CLAUSE_FLAGGED_REVIEW = "clause_flagged_review"
    CONFLICT_OPENED = "conflict_opened"
    REQUIREMENT_CREATED = "requirement_created"
    REQUIREMENT_CHANGED = "requirement_changed"
    PRODUCT_CREATED = "product_created"
    PRODUCT_UPDATED = "product_updated"
    PRODUCT_STATUS_CHANGED = "product_status_changed"


class Ingredient(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    normalized: str | None = None
    unnormalized: bool = False
    amount: float | None = Field(default=None, ge=0)
    unit: Unit | None = None

    def model_post_init(self, _: Any) -> None:
        if self.amount is not None and self.unit is None:
            raise ValueError(f"ingredient '{self.name}': an amount needs a unit")


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    product_type: ProductType
    origin: str = Field(min_length=2, max_length=2, description="ISO country code")
    packaging: str | None = Field(default=None, max_length=200)
    ingredients: list[Ingredient] = Field(default_factory=list)
    target_markets: list[str] = Field(default_factory=list)


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    product_type: ProductType | None = None
    origin: str | None = Field(default=None, min_length=2, max_length=2)
    packaging: str | None = Field(default=None, max_length=200)
    ingredients: list[Ingredient] | None = None
    target_markets: list[str] | None = None


class Product(ProductIn):
    id: str
    workspace_id: str = WORKSPACE_ID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GraphEvent(BaseModel):
    id: str
    workspace_id: str = WORKSPACE_ID
    event_type: EventType
    entity_type: str
    entity_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    cause: dict[str, Any] | None = None
    triggered_by: str = "api"
    confidence: float | None = None
    trace_id: str | None = None
    occurred_at: datetime | None = None
