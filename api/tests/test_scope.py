"""Food-category scope: the deterministic answer to "are these two rows about
the same food?", which is what emptied thirty-six entries out of the review
queue without a person answering any of them."""

from __future__ import annotations

from app.core.guardrail import IncomparablePair, comparability
from app.core.scope import categories_comparable, category_code, category_of


def _clause(text: str, limit: float, **over) -> dict:
    base = {
        "text": text,
        "clause_type": "numeric_limit",
        "substance_normalized": "sodium_benzoate",
        "unit": "mg_per_kg",
        "limit_value": limit,
        "product_type": None,
        "jurisdiction": "ID",
        "document_id": "doc_bpom_11_2019",
        "effective_date": "2019-06-01",
    }
    return base | over


BEVERAGE = (
    "14.1.4.2 Minuman Berbasis Air Berperisa Tidak Berkarbonat, Termasuk Punches "
    "dan Ades Batas Maksimal 400 mg/kg dihitung sebagai asam benzoat"
)
FRUIT_PREP = (
    "04.1.2.8 Bahan Baku Berbasis Buah, Meliputi Bubur Buah, Puree, Topping Buah "
    "dan Santan Kelapa Batas Maksimal 1000 mg/kg dihitung sebagai asam benzoat"
)


class TestCategoryCode:
    def test_reads_the_code_the_regulator_printed(self):
        assert category_code(BEVERAGE) == "14.1.4.2"
        assert category_code(FRUIT_PREP) == "04.1.2.8"

    def test_two_level_code(self):
        assert category_code("12.10 Produk Protein Batas Maksimal 500 mg/kg") == "12.10"

    def test_a_measurement_is_not_a_category(self):
        # "1.5 mg/kg …" opens with something shaped exactly like a shallow code.
        assert category_code("1.5 mg/kg of benzoic acid in soft drinks") is None
        assert category_code("0.05 % w/w maximum") is None

    def test_silence_stays_silence(self):
        assert category_code("Benzoic acid limit 150 mg/kg") is None
        assert category_code(None) is None
        assert category_code("") is None

    def test_a_reference_mid_sentence_is_not_this_rows_scope(self):
        assert category_code("Excluding food category 12.10, the limit is 500 mg/kg") is None

    def test_category_of_prefers_a_stored_value(self):
        assert category_of({"category_code": "14.1", "text": FRUIT_PREP}) == "14.1"
        assert category_of({"text": FRUIT_PREP}) == "04.1.2.8"


class TestCategoriesComparable:
    def test_different_branches_are_different_foods(self):
        assert categories_comparable("14.1.4.2", "04.1.2.8") is False

    def test_the_same_category_is_still_a_real_question(self):
        assert categories_comparable("14.1.4.2", "14.1.4.2") is True

    def test_a_broader_row_covers_a_narrower_one(self):
        assert categories_comparable("14.1", "14.1.4.2") is True
        assert categories_comparable("14.1.4.2", "14.1") is True

    def test_leading_zeros_do_not_split_a_branch(self):
        assert categories_comparable("04.1", "4.1.2.8") is True

    def test_sibling_leaves_are_not_comparable(self):
        assert categories_comparable("14.1.4.1", "14.1.4.2") is False

    def test_unknown_blocks_nothing(self):
        assert categories_comparable(None, "14.1.4.2") is True
        assert categories_comparable("14.1.4.2", None) is True


class TestGuardrailUsesTheCategory:
    def test_two_rows_of_one_table_never_reach_the_judge(self):
        verdict = comparability(_clause(BEVERAGE, 400), _clause(FRUIT_PREP, 1000))
        assert isinstance(verdict, IncomparablePair)
        assert verdict.reason == "food_category_mismatch"

    def test_the_same_category_still_compares(self):
        other = _clause(
            "14.1.4.2 Minuman Berbasis Air Berperisa Batas Maksimal 200 mg/kg", 200,
            document_id="doc_bpom_2024",
        )
        verdict = comparability(_clause(BEVERAGE, 400), other)
        assert not isinstance(verdict, IncomparablePair)
        assert (verdict.value_a, verdict.value_b) == (400.0, 200.0)

    def test_a_clause_with_no_category_compares_exactly_as_before(self):
        eu = _clause(
            "Benzoic acid — benzoates (E 210-213): 150 mg/kg", 150,
            jurisdiction="EU", document_id="doc_eu_1333", effective_date="2011-06-01",
        )
        verdict = comparability(_clause(BEVERAGE, 400), eu)
        assert not isinstance(verdict, IncomparablePair)
        assert (verdict.value_a, verdict.value_b) == (400.0, 150.0)
