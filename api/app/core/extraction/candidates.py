"""Candidate validation, normalization, self-consistency, composite confidence.

This module is the gate between the model and Firestore. A raw dict from Gemini
becomes a stored clause only by passing through `build_candidate` here. The
model proposes; this code decides.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from app.core.normalization import normalize_substance, parse_unit
from app.models import (
    AUTHORITY_TIERS,
    WORKSPACE_ID,
    ClauseCandidate,
    ClauseCandidateRaw,
    ClauseType,
    SourceType,
)

logger = logging.getLogger(__name__)

# Fields over which two independent samples must agree for self-consistency.
_CONSISTENCY_FIELDS = ("substance", "limit_value", "unit_raw", "product_type")

# An additive regulation carries two kinds of number that look identical to an
# extractor and mean opposite things. A food limit says how much of a substance
# may be in what you eat. A purity criterion says how pure the additive powder
# itself has to be before anyone is allowed to put it in food, and it names no
# food category at all — so it arrives with `product_type` unset, which the
# guardrail reads as "any product type", and one drying specification then binds
# every product in the workspace.
#
# Seen in production: "Loss on drying Not more than 0,25 % (4 hours, over silica
# gel)" from Commission Regulation (EU) 2023/2108, stored active against
# sodium nitrite, ready to answer a bacon recipe with a verdict drawn from a
# laboratory method.
#
# These headings are the ones that only ever open a purity criterion. A row that
# carries one goes to a person; nothing here approves anything, so a false match
# costs one review and a miss costs a wrong verdict.
_SPECIFICATION_MARKERS = (
    "loss on drying",
    "loss on ignition",
    "residue on ignition",
    "sulphated ash",
    "sulfated ash",
    "water insoluble matter",
    "assay",
    "solubility",
)


def _reads_as_specification(text: str) -> bool:
    """Is this row about the purity of the additive rather than a food limit?"""
    lowered = " ".join((text or "").lower().split())
    return any(marker in lowered for marker in _SPECIFICATION_MARKERS)


def build_candidate(
    raw: dict[str, Any],
    *,
    document_id: str,
    source_type: str | SourceType,
    declared_effective_date: str | None = None,
    source_jurisdiction: str | None = None,
) -> tuple[ClauseCandidate | None, dict[str, Any]]:
    """Validate one raw model emission into a ClauseCandidate.

    Returns `(candidate, rejection)`. Exactly one is non-None. A rejection
    carries the reason the candidate died — it never reaches Firestore as a
    clause, but it IS recorded in the debug view.
    """
    try:
        parsed = ClauseCandidateRaw.model_validate(raw)
    except ValidationError as exc:
        reasons = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        ]
        return None, {"raw": _safe(raw), "reason": "validation_failed", "detail": reasons}

    tier = AUTHORITY_TIERS.get(str(source_type), 0.2)

    substance_normalized: str | None = None
    unnormalized_substance = False
    if parsed.substance:
        substance_normalized, unnormalized_substance = normalize_substance(parsed.substance)

    unit_enum = None
    unnormalized_unit = False
    # A row with no number ("quantum satis", "CPPB") has no unit to normalize.
    # Flagging it as an unusable unit sends the reader hunting for a units
    # problem that is not there; the clause still lands in review on its own
    # merits, with a reason that is true.
    if parsed.unit_raw and parsed.limit_value is not None:
        try:
            unit_enum = parse_unit(parsed.unit_raw)
        except ValueError:
            # The plan is explicit: a clause whose unit cannot be normalized is
            # kept as clause_type other + needs_review, not discarded.
            unit_enum = None
            unnormalized_unit = True

    needs_review = False
    review_reasons: list[str] = []

    if unnormalized_unit:
        needs_review = True
        review_reasons.append("unit_not_normalizable")
        if parsed.clause_type == ClauseType.NUMERIC_LIMIT:
            parsed = parsed.model_copy(update={"clause_type": ClauseType.OTHER})
    if unnormalized_substance:
        needs_review = True
        review_reasons.append("substance_not_recognized")
    if parsed.clause_type == ClauseType.NUMERIC_LIMIT and _reads_as_specification(parsed.text):
        needs_review = True
        review_reasons.append("specification_not_food_limit")

    return (
        ClauseCandidate(
            id="",  # assigned at persistence
            document_id=document_id,
            workspace_id=WORKSPACE_ID,
            jurisdiction=str(source_jurisdiction).upper() if source_jurisdiction else None,
            text=parsed.text,
            clause_type=parsed.clause_type,
            substance=parsed.substance,
            limit_value=parsed.limit_value,
            unit_raw=parsed.unit_raw,
            product_type=parsed.product_type,
            effective_date=parsed.effective_date or declared_effective_date,
            substance_normalized=substance_normalized,
            unnormalized_substance=unnormalized_substance,
            unit_enum=unit_enum,
            unnormalized_unit=unnormalized_unit,
            authority_tier=tier,
            self_consistency=0.0,  # set by score_consistency once both samples exist
            parse_quality=0.0,  # injected by the pipeline
            needs_review=needs_review,
            review_reasons=review_reasons,
            confidence=0.0,  # computed by finalize_confidence
            confidence_breakdown={},
        ),
        {},
    )


def score_consistency(a_raw: dict, b_raw: dict) -> float:
    """Fraction of the four key fields on which two independent samples agree.
    Two identical emissions give 1.0; total disagreement gives 0.0."""
    matches = 0
    for field in _CONSISTENCY_FIELDS:
        va, vb = a_raw.get(field), b_raw.get(field)
        if va is None and vb is None:
            matches += 1  # agreeing that something is absent is agreement
        elif isinstance(va, str) and isinstance(vb, str):
            matches += int(va.strip().lower() == vb.strip().lower())
        else:
            matches += int(va == vb)
    return round(matches / len(_CONSISTENCY_FIELDS), 4)


def best_consistency(raw: dict, others: list[dict]) -> float:
    """Self-consistency for one primary candidate: agreement with the
    best-matching candidate of the second sample. Index-matching breaks as soon
    as the two samples emit different counts; best-match does not."""
    if not others:
        return 0.0
    return max(score_consistency(raw, other) for other in others)


def finalize_confidence(candidate: ClauseCandidate) -> ClauseCandidate:
    """Composite confidence per the concept:
    0.3 * parse_quality + 0.4 * self_consistency + 0.3 * authority_tier."""
    breakdown = {
        "parse_quality": candidate.parse_quality,
        "self_consistency": candidate.self_consistency,
        "authority_tier": candidate.authority_tier,
    }
    value = (
        0.3 * breakdown["parse_quality"]
        + 0.4 * breakdown["self_consistency"]
        + 0.3 * breakdown["authority_tier"]
    )
    return candidate.model_copy(
        update={
            "confidence": round(min(1.0, max(0.0, value)), 4),
            "confidence_breakdown": breakdown,
        }
    )


def _safe(raw: dict[str, Any], limit: int = 2000) -> dict[str, Any]:
    """Truncate a rejected raw response so debug payloads stay bounded."""
    out: dict[str, Any] = {}
    for key, value in list(raw.items())[:20]:
        text = str(value)
        out[key] = text[:limit]
    return out
