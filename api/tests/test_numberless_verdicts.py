"""Rules with no comparable number, and what the system still says about them.

Every one of these used to come back `needs_review / non_numeric_clause`, which
the product page printed as "This rule has no number in it, so a person has to
read it." Over a row reading `350` that sentence was also untrue.
"""

from __future__ import annotations

from app.core.impact import evaluate

PRODUCT = {
    "id": "prod_1",
    "product_type": "food_beverage_liquid",
    "ingredients": [
        {"name": "acesulfame k", "normalized": "acesulfame_k", "amount": 200, "unit": "mg_per_kg"}
    ],
}


def clause(**overrides) -> dict:
    return {
        "id": "clause_1",
        "clause_type": "other",
        "substance_normalized": "acesulfame_k",
        "limit_value": None,
        "unit": None,
        "unit_raw": None,
        "confidence": 0.9,
        "text": "",
    } | overrides


class TestARowThatDoesHaveANumber:
    def test_an_unreadable_unit_is_not_reported_as_a_missing_number(self):
        """`candidates.py` demotes a row whose unit will not normalize to
        `clause_type: other` while leaving `limit_value` on it. The old reason
        then told the reader the row had no number in it. It has 350 in it."""
        result = evaluate(PRODUCT, clause(limit_value=350.0, unit_raw="g/l"))
        assert result["reason"] == "clause_unit_unreadable"
        assert result["reason_detail"] == "g/l"
        assert result["evaluation"] == "needs_review"


class TestQuantumSatis:
    def test_a_stated_absence_of_a_maximum_is_an_answer(self):
        result = evaluate(
            PRODUCT, clause(text="| E 300 | Ascorbic acid | quantum satis |  |  |")
        )
        assert result["evaluation"] == "pass"
        assert result["reason"] == "no_maximum"
        assert result["reason_detail"] == "quantum satis"

    def test_a_quantum_satis_row_restricted_to_one_food_asks_instead(self):
        """"only traditional Swedish and Finnish fruit syrups" is a condition
        this module will not decide about a product — but it is one question,
        not a page of annex."""
        result = evaluate(
            PRODUCT,
            clause(
                text="| E 296 | Malic acid | quantum satis |  | only traditional "
                "Swedish and Finnish fruit syrups |"
            ),
        )
        assert result["evaluation"] == "needs_review"
        assert result["reason"] == "conditional_permission"
        assert result["reason_detail"].startswith("only traditional swedish")


class TestAProhibition:
    def test_may_not_be_used_is_a_limit_of_zero(self):
        result = evaluate(PRODUCT, clause(text="E 950 may not be used in this category"))
        assert result["evaluation"] == "fail"
        assert result["reason"] == "prohibited"
        assert result["severity"] == "high"

    def test_a_prohibition_with_a_carve_out_is_a_question_not_a_verdict(self):
        result = evaluate(
            PRODUCT,
            clause(
                text="E 968 may not be used except where specifically provided for "
                "in this food category"
            ),
        )
        assert result["evaluation"] == "needs_review"
        assert result["reason"] == "conditional_permission"


class TestWhatStillWaitsForAPerson:
    def test_an_unrecognised_rule_is_still_handed_over_honestly(self):
        result = evaluate(
            PRODUCT,
            clause(text="The competent authority shall be notified before placing on the market"),
        )
        assert result["reason"] == "non_numeric_clause"
        assert result["evaluation"] == "needs_review"

    def test_a_rule_about_nothing_in_this_product_decides_nothing(self):
        """No matching ingredient means there is nothing of theirs to rule on,
        so `quantum satis` must not be reported as a pass."""
        result = evaluate(
            PRODUCT, clause(substance_normalized="tartrazine", text="quantum satis")
        )
        assert result["evaluation"] == "needs_review"
        assert result["reason"] == "non_numeric_clause"

    def test_a_low_confidence_reading_still_overrides_a_decided_verdict(self):
        """A clause we are not sure we read correctly cannot pass a product,
        however decidable its words look."""
        result = evaluate(PRODUCT, clause(text="quantum satis", confidence=0.2))
        assert result["evaluation"] == "needs_review"
        assert result["reason"] == "clause_confidence_below_0_5"


class TestTheNumericPathIsUntouched:
    def test_a_real_limit_still_compares(self):
        result = evaluate(
            PRODUCT,
            clause(clause_type="numeric_limit", limit_value=350.0, unit="mg_per_kg"),
        )
        assert (result["evaluation"], result["reason"]) == ("pass", None)

    def test_and_still_fails_when_it_should(self):
        result = evaluate(
            PRODUCT,
            clause(clause_type="numeric_limit", limit_value=100.0, unit="mg_per_kg"),
        )
        assert result["evaluation"] == "fail"
