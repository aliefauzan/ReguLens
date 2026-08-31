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


# ---------------------------------------------------------------------------
# The food stated in words, for annexes that print no category code


class TestStatedScope:
    """EU Annex II limit rows carry no GSFA code. They name the food in the row.

    Twenty-four nitrite rows of Commission Regulation (EU) 2023/2108 are written
    this way — one per cured meat — and without reading the phrase every pair of
    them is a supersede question with no date to settle it, which is exactly the
    case that reaches the judge and comes back ambiguous.
    """

    def test_the_restriction_phrase_is_read_with_its_keyword(self):
        from app.core.scope import stated_scope

        assert stated_scope(
            "E 249-250 Nitrites 50 (39) only jellied veal and brisket : Injection of curing"
        ) == ("only", "jellied veal and brisket")

    def test_the_validity_window_is_not_part_of_the_food(self):
        """Two rows about one food, one superseding the other, differ only by
        their dates. Leaving the window in the scope makes them two foods and
        the supersede never happens."""
        from app.core.scope import stated_scope

        new = stated_scope(
            "E 249-250 Nitrites 80 (59) (XC) (XD) except sterilised meat products "
            "(Fo > 3,00) Period of application: from 9 October 2025"
        )
        old = stated_scope(
            "E 249-250 Nitrites 150 (7) (59) except sterilised meat products "
            "(Fo > 3,00) Period of application: until 9 October 2025"
        )
        assert new == old

    def test_a_row_that_states_no_food_says_so(self):
        from app.core.scope import stated_scope

        assert stated_scope("14.1.4.2 Minuman Berbasis Air Berperisa 400 mg/kg") is None
        assert stated_scope(None) is None

    def test_only_and_except_are_different_statements(self):
        """A rule that applies to everything but a food and a rule that applies
        to nothing but a food say opposite things with the same words."""
        from app.core.scope import scopes_comparable, stated_scope

        a = stated_scope("Nitrites 100 only sterilised meat products")
        b = stated_scope("Nitrites 80 except sterilised meat products")
        assert a != b
        assert scopes_comparable(a, b) is False

    def test_silence_blocks_nothing(self):
        from app.core.scope import scopes_comparable

        assert scopes_comparable(None, ("only", "dry cured bacon")) is True
        assert scopes_comparable(None, None) is True

    def test_two_rows_about_different_meats_are_not_compared(self):
        """The whole point. Refusing is the cautious direction: nothing is
        superseded, both rows stay active, and a product is still measured
        against the stricter of them."""
        from app.core.guardrail import comparability

        row = {
            "clause_type": "numeric_limit",
            "substance_normalized": "nitrites",
            "unit": "mg_per_kg",
            "product_type": "food_solid",
        }
        veal = row | {"limit_value": 50.0, "text": "E 249-250 Nitrites 50 only jellied veal"}
        bacon = row | {
            "limit_value": 105.0,
            "text": "E 249-250 Nitrites 105 only Wiltshire bacon and similar products :",
        }
        verdict = comparability(veal, bacon)
        assert getattr(verdict, "reason", None) == "stated_scope_mismatch"

    def test_one_food_amended_stays_one_supersede_question(self):
        from app.core.guardrail import comparability

        row = {
            "clause_type": "numeric_limit",
            "substance_normalized": "nitrites",
            "unit": "mg_per_kg",
            "product_type": "food_solid",
        }
        old = row | {
            "limit_value": 150.0,
            "text": "E 249-250 Nitrites 150 (7) (59) except sterilised meat products "
                    "(Fo > 3,00) Period of application: until 9 October 2025",
        }
        new = row | {
            "limit_value": 80.0,
            "text": "E 249-250 Nitrites 80 (59) (XC) except sterilised meat products "
                    "(Fo > 3,00) Period of application: from 9 October 2025",
        }
        verdict = comparability(old, new)
        assert getattr(verdict, "reason", None) is None
        assert (verdict.value_a, verdict.value_b) == (150.0, 80.0)


class TestAppliesUntil:
    """Annex II writes an amendment as two rows, and only one of them carries a
    date extraction can read as an effective date."""

    def test_the_end_of_a_period_is_read(self):
        from app.core.scope import applies_until

        assert applies_until(
            "E 249-250 Nitrites 150 (7) (59) except sterilised meat products "
            "(Fo > 3,00) Period of application: until 9 October 2025"
        ) == "2025-10-09"

    def test_a_start_date_is_not_an_end_date(self):
        from app.core.scope import applies_until

        assert applies_until("Nitrites 80 Period of application: from 9 October 2025") is None

    def test_a_row_with_no_period_states_no_end(self):
        """None means the row states no end — never that it ended."""
        from app.core.scope import applies_until

        assert applies_until("E 249-250 Nitrites 50 only jellied veal and brisket") is None

    def test_the_replacement_supersedes_without_a_model(self):
        """The pair the model was being asked about: 150 until 9 October 2025,
        80 from it. The rows answer it themselves."""
        from app.core.reconciliation import _dates_decide, _is_newer

        old = {
            "limit_value": 150.0,
            "effective_date": None,
            "text": "E 249-250 Nitrites 150 except sterilised meat products "
                    "Period of application: until 9 October 2025",
        }
        new = {
            "limit_value": 80.0,
            "effective_date": "2025-10-09",
            "text": "E 249-250 Nitrites 80 except sterilised meat products "
                    "Period of application: from 9 October 2025",
        }
        assert _dates_decide(new, old) is True
        assert _is_newer(new, old) is True
        assert _is_newer(old, new) is False
