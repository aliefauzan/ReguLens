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
    CLAUSE_DISMISSED = "clause_dismissed"
    CONFLICT_OPENED = "conflict_opened"
    REQUIREMENT_CREATED = "requirement_created"
    REQUIREMENT_CHANGED = "requirement_changed"
    PRODUCT_CREATED = "product_created"
    PRODUCT_UPDATED = "product_updated"
    PRODUCT_STATUS_CHANGED = "product_status_changed"
    PRODUCT_DELETED = "product_deleted"


class SourceType(StrEnum):
    """Declared by the uploader, because in this MVP nobody else can. The tier
    is trivially gameable and that is fine for a demo — but it is a *product
    decision*, so the UI presents it as "how authoritative is this source?"
    with the tiers visible rather than hiding it as a form field."""

    OFFICIAL_REGULATION = "official_regulation"
    OFFICIAL_GUIDANCE = "official_guidance"
    INDUSTRY_ASSOCIATION = "industry_association"
    NEWS_ARTICLE = "news_article"
    SOCIAL_CHAT = "social_chat"


# Composite confidence weights per the concept's model:
# 0.3 parse quality + 0.4 self-consistency + 0.3 authority tier.
AUTHORITY_TIERS: dict[str, float] = {
    str(SourceType.OFFICIAL_REGULATION): 1.0,
    str(SourceType.OFFICIAL_GUIDANCE): 0.8,
    str(SourceType.INDUSTRY_ASSOCIATION): 0.5,
    str(SourceType.NEWS_ARTICLE): 0.35,
    str(SourceType.SOCIAL_CHAT): 0.2,
}


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    RECONCILING = "reconciling"
    RECONCILED = "reconciled"
    FAILED = "failed"


class ClauseType(StrEnum):
    NUMERIC_LIMIT = "numeric_limit"
    DOCUMENTATION = "documentation"
    LABELING = "labeling"
    CERTIFICATION = "certification"
    OTHER = "other"


class ClauseStatus(StrEnum):
    """Phase 2 writes `pending_reconciliation`; phase 3 owns every transition
    past it."""

    PENDING_RECONCILIATION = "pending_reconciliation"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CONFLICTED = "conflicted"
    NEEDS_REVIEW = "needs_review"
    # A human read this in the review queue and said no. It never becomes
    # active, and it is not deleted — the audit trail keeps what was rejected.
    DISMISSED = "dismissed"


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


class DocumentIn(BaseModel):
    """Source metadata declared at upload. `declared_effective_date` is the
    uploader's claim — extraction may find a different date in the text, and the
    guardrail later prefers what the document itself states."""

    source_type: SourceType
    source_name: str = Field(min_length=1, max_length=200)
    jurisdiction: str = Field(min_length=2, max_length=16)
    declared_effective_date: str | None = Field(default=None, max_length=10)
    filename: str | None = Field(default=None, max_length=200)


class QueryIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    product_id: str | None = None


class RegulatoryDocument(DocumentIn):
    id: str
    workspace_id: str = WORKSPACE_ID
    filename: str | None = None
    content_sha256: str
    storage_uri: str | None = None
    text_preview: str | None = None  # first ~500 chars; full text lives with the file or inline below
    text_inline: str | None = None  # pasted-text path: content small enough to keep inline
    page_count: int | None = None
    char_count: int = 0
    parse_quality: float | None = None
    text_method: str | None = None  # pdfplumber (ocr is cut from MVP)
    status: DocumentStatus = DocumentStatus.UPLOADED
    stage_log: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    failed_stage: str | None = None
    trace_id: str | None = None
    uploaded_at: datetime | None = None
    updated_at: datetime | None = None


class ClauseCandidateRaw(BaseModel):
    """Exactly what we ask the model for. Field constraints mean a malformed
    response fails *here*, loudly, instead of becoming Firestore state."""

    text: str = Field(min_length=1)
    clause_type: ClauseType
    substance: str | None = Field(default=None, max_length=200)
    limit_value: float | None = Field(default=None, ge=0)
    unit_raw: str | None = Field(default=None, max_length=32)
    product_type: ProductType | None = None
    effective_date: str | None = Field(default=None, max_length=10)


class ClauseCandidate(ClauseCandidateRaw):
    """A raw candidate that survived validation and normalization. This is the
    only shape that may reach Firestore."""

    id: str
    workspace_id: str = WORKSPACE_ID
    document_id: str
    jurisdiction: str | None = None
    substance_normalized: str | None = None
    unnormalized_substance: bool = False
    unit_enum: Unit | None = None
    unnormalized_unit: bool = False
    authority_tier: float
    self_consistency: float
    parse_quality: float
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    confidence: float
    confidence_breakdown: dict[str, float]
    status: ClauseStatus = ClauseStatus.PENDING_RECONCILIATION
    created_at: datetime | None = None
