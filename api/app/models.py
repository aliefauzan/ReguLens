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
    # A clause left the review queue without a person answering it: new
    # deterministic evidence settled the question that parked it there.
    CLAUSE_RECHECKED = "clause_rechecked"
    CONFLICT_OPENED = "conflict_opened"
    REQUIREMENT_CREATED = "requirement_created"
    REQUIREMENT_CHANGED = "requirement_changed"
    PRODUCT_CREATED = "product_created"
    PRODUCT_UPDATED = "product_updated"
    PRODUCT_STATUS_CHANGED = "product_status_changed"
    # A verdict that changes on a date nobody has reached yet. Distinct from
    # PRODUCT_STATUS_CHANGED because nothing about the product is wrong today.
    PRODUCT_STATUS_SCHEDULED = "product_status_scheduled"
    PRODUCT_DELETED = "product_deleted"
    DOCUMENT_DELETED = "document_deleted"
    SOURCE_ADDED = "source_added"
    SOURCE_UPDATED = "source_updated"
    SOURCE_REMOVED = "source_removed"


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


class LibraryLoadIn(BaseModel):
    """Which bundled rules to read. Empty means the starter set."""

    ids: list[str] | None = Field(default=None, max_length=64)


class QueryIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    product_id: str | None = None


class SourceKind(StrEnum):
    """What is at the other end of a watched address.

    `document` is one regulation whose wording can change under us. `feed` is a
    list of things published over time, where "changed" means a new entry
    appeared rather than the page being rewritten. They need different
    change-detection, so the distinction is typed rather than sniffed.
    """

    DOCUMENT = "document"
    FEED = "feed"
    # An index page. New links on it are new regulations — the answer to "what
    # if the rule is published at a different address?", which watching a known
    # document can never see.
    LISTING = "listing"
    # A query against a publisher's own catalogue. Same discovery job as a
    # listing, but asked rather than scraped: the publisher decides what counts
    # as "a food-additive regulation published since June", not a regex over a
    # page that a redesign can break.
    SPARQL = "sparql"


class SourceCheckStatus(StrEnum):
    NEVER_CHECKED = "never_checked"
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    # A feed's first look. Its current entries are remembered and deliberately
    # not ingested: adopting a feed means "tell me what happens next", not
    # "read the last twenty things that happened".
    BASELINED = "baselined"
    # Another check for the same source is already running.
    BUSY = "busy"
    ERROR = "error"


class WatchedSourceIn(BaseModel):
    """An address ReguLens re-reads on a schedule."""

    url: str = Field(min_length=8, max_length=2000)
    label: str = Field(min_length=1, max_length=200)
    kind: SourceKind = SourceKind.DOCUMENT
    source_type: SourceType
    jurisdiction: str = Field(min_length=2, max_length=16)
    check_interval_hours: int = Field(default=24, ge=1, le=24 * 30)
    enabled: bool = True
    # `listing` only: which links on the page are regulations. Required there
    # and ignored elsewhere — an index page carries navigation, a language
    # switcher and social links, and a watcher that followed all of them would
    # ingest the website.
    link_pattern: str | None = Field(default=None, max_length=400)
    # `sparql` only: the query to ask. `{since}` is substituted with an ISO date
    # so the window moves with the calendar instead of growing forever.
    sparql_query: str | None = Field(default=None, max_length=4000)

    def model_post_init(self, _: Any) -> None:
        if not self.url.lower().startswith(("http://", "https://")):
            raise ValueError("a watched source must be an http:// or https:// address")
        if self.kind == SourceKind.LISTING:
            if not (self.link_pattern or "").strip():
                raise ValueError(
                    "a listing needs a link_pattern saying which links are regulations"
                )
            import re as _re

            try:
                _re.compile(self.link_pattern)
            except _re.error as exc:
                # Caught here rather than at fetch time: a pattern that cannot
                # compile would otherwise fail every night at 06:00, in a log.
                raise ValueError(f"link_pattern is not a valid expression: {exc}") from exc
        if self.kind == SourceKind.SPARQL:
            query = (self.sparql_query or "").strip()
            if not query:
                raise ValueError("a sparql source needs a sparql_query to ask")
            # Same reasoning as the pattern: a query selecting nothing we can
            # fetch is a source that reports "no new regulations" every night
            # while watching nothing at all.
            if not any(name in query for name in ("?celex", "?work", "?uri")):
                raise ValueError(
                    "the query must select a ?celex, ?work or ?uri column naming each document"
                )


class WatchedSourcePatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    check_interval_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    enabled: bool | None = None


class WatchedSource(WatchedSourceIn):
    id: str
    workspace_id: str = WORKSPACE_ID
    last_status: SourceCheckStatus = SourceCheckStatus.NEVER_CHECKED
    last_error: str | None = None
    last_checked_at: datetime | None = None
    last_changed_at: datetime | None = None
    # Server validators, when the server bothers to send them. EUR-Lex sends
    # neither, so these stay null there and the text hash does the work.
    last_etag: str | None = None
    last_modified: str | None = None
    # The change signal that actually holds: a hash of the *words*, not the
    # bytes. The bytes of a government page change on every request.
    last_text_sha: str | None = None
    # Feed entries already seen, newest last. Capped — an unbounded list would
    # eventually exceed Firestore's document limit and take the source with it.
    seen_entry_ids: list[str] = Field(default_factory=list)
    # Documents this source has produced, newest first.
    document_ids: list[str] = Field(default_factory=list)
    checks: int = 0
    changes: int = 0
    # Set while a check is running, so two schedulers cannot double-ingest.
    check_lock_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RegulatoryDocument(DocumentIn):
    id: str
    workspace_id: str = WORKSPACE_ID
    filename: str | None = None
    content_sha256: str
    storage_uri: str | None = None
    text_preview: str | None = None  # first ~500 chars; full text lives with the file or inline below
    text_inline: str | None = None  # pasted-text path: content small enough to keep inline
    # PDF path: what the worker read out of the file, so the citation view can
    # show the passage a clause came from. Capped; `text_truncated` says when.
    text_extracted: str | None = None
    text_truncated: bool = False
    page_count: int | None = None
    char_count: int = 0
    parse_quality: float | None = None
    text_method: str | None = None  # pdfplumber (ocr is cut from MVP)
    status: DocumentStatus = DocumentStatus.UPLOADED
    stage_log: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    failed_stage: str | None = None
    # What the document said about itself at upload, and which fields the user
    # overrode. Kept so the UI can show its working rather than assert.
    detection: dict[str, Any] | None = None
    declared_fields: list[str] = Field(default_factory=list)
    origin: str = "upload"  # upload | library | demo | watched_source
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


# ---------------------------------------------------------------------------
# Remediation — a draft fix, not an action taken


class RemediationLimit(BaseModel):
    """One market's binding limit, with the words it was read from.

    The quote and the passage link are not decoration: this page exists to be
    approved by a person, and a number they cannot trace is a number they
    cannot sign off.
    """

    market_id: str
    limit: float
    unit: str
    clause_id: str
    document_id: str | None = None
    effective_date: str | None = None
    quote: str | None = None
    citation_href: str | None = None
    # Other limits for this substance in this market that are looser than the
    # one shown. Counted rather than dropped: a hidden row reads like it does
    # not exist.
    other_limits_in_market: int = 0
    is_strictest: bool = False


class RemediationTarget(BaseModel):
    """The number to hit for one substance, across every market in scope."""

    substance: str
    substance_label: str
    target_value: float | None = None
    target_unit: str | None = None
    # Filled exactly when `target_value` is None. Enforced below, because an
    # empty target with an empty reason is the failure mode this whole feature
    # is written against.
    no_target_reason: str | None = None
    no_target_reason_text: str = ""
    coverage: str  # full | partial
    markets_without_rules: list[str] = Field(default_factory=list)
    strictest_market_id: str | None = None
    current_value: float | None = None
    current_unit: str | None = None
    raw_value: float | None = None
    raw_unit: str | None = None
    verdict_today: str
    limits: list[RemediationLimit] = Field(default_factory=list)

    def model_post_init(self, _: Any) -> None:
        if self.target_value is None and not self.no_target_reason:
            raise ValueError("a missing target needs a reason")
        if self.target_value is not None and self.no_target_reason:
            raise ValueError("a target that exists cannot also carry a reason for not existing")
        if self.no_target_reason and not self.no_target_reason_text:
            raise ValueError("a reason code needs the sentence a reader sees")
        expected = "partial" if self.markets_without_rules else "full"
        if self.coverage != expected:
            raise ValueError(f"coverage says {self.coverage} but the market list says {expected}")


class RemediationNotChecked(BaseModel):
    """An ingredient no target speaks for, and why. Never silently omitted."""

    ingredient: str
    reason_code: str
    reason_text: str = Field(min_length=1)


class RemediationPlan(BaseModel):
    """A draft for a person to check. Nothing here was acted on."""

    product_id: str
    product_name: str
    generated_for_markets: list[str] = Field(default_factory=list)
    targets: list[RemediationTarget] = Field(default_factory=list)
    not_checked: list[RemediationNotChecked] = Field(default_factory=list)
    trace_id: str | None = None
