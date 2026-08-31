"""The gate between model output and Firestore state, under adversarial input.

Every test here is a way the model can be wrong. A rejection must stay a
rejection no matter how confident the emission looked.
"""


from app.core.extraction.candidates import (
    best_consistency,
    build_candidate,
    finalize_confidence,
    score_consistency,
)
from app.models import ClauseType, SourceType, Unit


def _build(raw, source_type=SourceType.OFFICIAL_REGULATION):
    candidate, rejection = build_candidate(
        raw, document_id="doc_x", source_type=str(source_type)
    )
    return candidate, rejection


def test_valid_numeric_limit_builds():
    candidate, rejection = _build(
        {
            "text": "Maximum level of sodium benzoate is 150 mg/kg in flavoured drinks.",
            "clause_type": "numeric_limit",
            "substance": "sodium benzoate",
            "limit_value": 150,
            "unit_raw": "mg/kg",
            "product_type": None,
        }
    )
    assert rejection == {}
    assert candidate is not None
    assert candidate.substance_normalized == "sodium_benzoate"
    assert candidate.unit_enum is Unit.MG_PER_KG
    assert candidate.unnormalized_substance is False


def test_missing_clause_type_is_rejected_not_coerced():
    candidate, rejection = _build({"text": "Something about additives."})
    assert candidate is None
    assert rejection["reason"] == "validation_failed"
    assert any("clause_type" in reason for reason in rejection["detail"])


def test_unknown_unit_keeps_clause_as_other_and_flags_review():
    candidate, rejection = _build(
        {
            "text": "Not more than 5 grams per litre.",
            "clause_type": "numeric_limit",
            "substance": "sodium benzoate",
            "limit_value": 5,
            "unit_raw": "g/L",
        }
    )
    assert rejection == {}
    assert candidate is not None
    assert candidate.unnormalized_unit is True
    assert candidate.needs_review is True
    assert "unit_not_normalizable" in candidate.review_reasons
    # A limit we cannot compare must not masquerade as one we can.
    assert candidate.clause_type is ClauseType.OTHER


def test_e_number_substance_normalizes():
    candidate, _ = _build(
        {
            "text": "E211 limited to 0.1%.",
            "clause_type": "numeric_limit",
            "substance": "E211",
            "limit_value": 0.1,
            "unit_raw": "%",
        }
    )
    assert candidate is not None
    assert candidate.substance_normalized == "sodium_benzoate"


def test_unrecognized_substance_flags_review_but_survives():
    candidate, rejection = _build(
        {
            "text": "Fictional extract 9000 shall not exceed 3 ppm.",
            "clause_type": "numeric_limit",
            "substance": "Fictional Extract 9000",
            "limit_value": 3,
            "unit_raw": "ppm",
        }
    )
    assert rejection == {}
    assert candidate is not None
    assert candidate.unnormalized_substance is True
    assert candidate.needs_review is True


def test_identical_samples_are_fully_consistent():
    raw = {"substance": "Sodium Benzoate", "limit_value": 150, "unit_raw": "mg/kg"}
    assert score_consistency(raw, dict(raw)) == 1.0


def test_partial_agreement_scores_partially():
    score = score_consistency(
        {"substance": "sodium benzoate", "limit_value": 150, "unit_raw": "mg/kg"},
        {"substance": "sodium benzoate", "limit_value": 900, "unit_raw": "mg/kg"},
    )
    assert 0.0 < score < 1.0


def test_best_consistency_ignores_index_misalignment():
    primary = {"substance": "a", "limit_value": 1, "unit_raw": "%", "product_type": None}
    secondary = [
        {"substance": "zzz", "limit_value": 9, "unit_raw": "ppm"},
        {"substance": "A", "limit_value": 1, "unit_raw": " % "},
    ]
    assert best_consistency(primary, secondary) == 1.0


def test_composite_confidence_follows_the_concept_weights():
    candidate, _ = _build(
        {
            "text": "x",
            "clause_type": "numeric_limit",
            "substance": "sodium benzoate",
            "limit_value": 1,
            "unit_raw": "%",
        }
    )
    assert candidate is not None
    scored = finalize_confidence(
        candidate.model_copy(
            update={"parse_quality": 1.0, "self_consistency": 1.0}
        )
    )
    # Official regulation tier is 1.0, so all three terms are 1.0.
    assert scored.confidence == 1.0
    assert scored.confidence_breakdown["authority_tier"] == 1.0


def test_low_authority_source_caps_confidence():
    candidate, _ = _build(
        {
            "text": "x",
            "clause_type": "numeric_limit",
            "substance": "sodium benzoate",
            "limit_value": 1,
            "unit_raw": "%",
        },
        source_type=SourceType.SOCIAL_CHAT,
    )
    assert candidate is not None
    scored = finalize_confidence(
        candidate.model_copy(update={"parse_quality": 1.0, "self_consistency": 1.0})
    )
    # 0.3*1 + 0.4*1 + 0.3*0.2 = 0.76 — high-ish but capped well below an
    # official source at equal quality, and phase 3 routes < 0.5 to review only.
    assert scored.confidence_breakdown["authority_tier"] == 0.2
    assert abs(scored.confidence - 0.76) < 1e-9

# --- Purity criteria are not food limits ------------------------------------
# Seen in production: "Loss on drying Not more than 0,25 %" reached Firestore as
# an active numeric limit on sodium nitrite with no product type, which the
# guardrail reads as "any product type" — one laboratory method binding every
# product in the workspace.


def test_a_drying_specification_goes_to_a_person():
    candidate, rejection = _build(
        {
            "text": "Loss on drying Not more than 0,25 % (4 hours, over silica gel)",
            "clause_type": "numeric_limit",
            "substance": "sodium nitrite",
            "limit_value": 0.25,
            "unit_raw": "%",
            "product_type": None,
        }
    )
    assert rejection == {}
    assert candidate is not None
    assert candidate.needs_review is True
    assert "specification_not_food_limit" in candidate.review_reasons


def test_a_real_food_limit_from_the_same_regulation_still_passes():
    candidate, rejection = _build(
        {
            "text": (
                "E 249-250 Nitrites 80 (59) (XC) (XD) except sterilised meat "
                "products (Fo > 3,00) Period of application: from 9 October 2025"
            ),
            "clause_type": "numeric_limit",
            "substance": "nitrites",
            "limit_value": 80,
            "unit_raw": "mg/kg",
            "product_type": "food_solid",
        }
    )
    assert rejection == {}
    assert candidate is not None
    assert candidate.needs_review is False
    assert candidate.substance_normalized == "nitrites"


def test_every_purity_heading_is_caught_not_only_the_one_seen_in_production():
    """One marker fixed one clause; the table has several headings and they all
    arrive with no food category attached."""
    candidate, _ = _build(
        {
            "text": "Sulphated ash Not more than 1,0 %",
            "clause_type": "numeric_limit",
            "substance": "sodium nitrite",
            "limit_value": 1.0,
            "unit_raw": "%",
            "product_type": None,
        }
    )
    assert candidate is not None
    assert "specification_not_food_limit" in candidate.review_reasons


def test_a_ceiling_that_names_no_food_is_a_specification():
    """"Nitrites — Not more than 20 mg/kg expressed as KNO2" is a purity row
    from Regulation 231/2012. At 20 mg/kg it is the strictest nitrite number in
    the annex, and naming no food it would bind every cured meat in the graph."""
    from app.core.extraction.candidates import _reads_as_specification

    assert _reads_as_specification("Nitrites Not more than 20 mg/kg expressed as KNO 2") is True


def test_a_food_limit_that_names_its_food_is_not_a_specification():
    from app.core.extraction.candidates import _reads_as_specification

    assert _reads_as_specification(
        "E 249-250 Nitrites 80 (59) except sterilised meat products (Fo > 3,00) "
        "Period of application: from 9 October 2025"
    ) is False
    assert _reads_as_specification(
        "14.1.4.2 Minuman Berbasis Air Berperisa Tidak Berkarbonat 400 mg/kg"
    ) is False
