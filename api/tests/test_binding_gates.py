"""Which rules reach a product, and which never should have.

The card that started this read:

    ⚠ acesulfame k
    This rule has no number in it, so a person has to read it.
    From EU Annex II — 14.1.3 Fruit and vegetable nectars

on a drink powder. Three separate reasons it should not have been there, one
test class each.
"""

from __future__ import annotations

from app.core.impact import clause_binds

EU = {"id": "market_de", "jurisdictions": ["EU"]}

POWDER = {
    "id": "prod_1",
    "product_type": "food_beverage_powder",
    "ingredients": [
        {"name": "acesulfame k", "normalized": "acesulfame_k", "amount": 200, "unit": "mg_per_kg"}
    ],
}


def clause(**overrides) -> dict:
    return {
        "id": "clause_1",
        "jurisdiction": "EU",
        "clause_type": "other",
        "substance_normalized": "acesulfame_k",
        "product_type": None,
        "text": "some rule",
    } | overrides


class TestAFootnoteIsNotARequirement:
    def test_an_annex_footnote_never_binds(self):
        assert not clause_binds(
            POWDER,
            clause(
                text="(49):  The maximum usable levels are derived from the maximum "
                "usable levels for its constituent parts, aspartame (E 951) and "
                "acesulfame-K (E 950)"
            ),
            EU,
        )

    def test_the_row_the_footnote_qualifies_still_binds(self):
        """Killing the footnote must not kill the limit it explains."""
        assert clause_binds(
            POWDER,
            clause(
                clause_type="numeric_limit",
                limit_value=350,
                text="| E 950 | Acesulfame K | 350 | (11)a (49) | only energy-reduced |",
            ),
            EU,
        )


class TestAFoodGateForEveryRule:
    def test_a_rule_for_a_different_food_does_not_bind(self):
        """The gate existed and was spelled `if numeric and not …`, so exactly
        the rows with no number escaped it — a supplement rule reached a drink
        powder because it happened to carry no limit."""
        assert not clause_binds(
            POWDER, clause(product_type="supplement", text="a supplement rule"), EU
        )

    def test_a_drink_rule_still_binds_the_powder_it_makes(self):
        """Powder and liquid are one family on purpose: the powder is sold to be
        reconstituted, and `guardrail._PRODUCT_TYPE_FAMILIES` says so. This gate
        must not quietly reverse that decision."""
        assert clause_binds(
            POWDER, clause(product_type="food_beverage_liquid", text="a nectar rule"), EU
        )

    def test_a_rule_written_for_this_food_binds(self):
        assert clause_binds(
            POWDER, clause(product_type="food_beverage_powder", text="a powder rule"), EU
        )

    def test_a_rule_that_names_no_food_still_binds(self):
        """`None` means the source did not say, which is the documented superset
        — not an excuse to drop the rule."""
        assert clause_binds(POWDER, clause(product_type=None, text="an unscoped rule"), EU)


class TestASubstanceGateForEveryRule:
    def test_a_rule_about_something_the_product_does_not_contain_does_not_bind(self):
        assert not clause_binds(POWDER, clause(substance_normalized="tartrazine"), EU)

    def test_a_rule_naming_no_substance_binds_anyway(self):
        """Labelling, notification and record-keeping obligations name no
        substance. Gating them out would be this same bug pointing the other
        way: silence where there is a requirement."""
        assert clause_binds(
            POWDER,
            clause(
                substance_normalized=None,
                clause_type="labeling",
                text="The label shall state the presence of a sweetener",
            ),
            EU,
        )

    def test_the_family_bind_still_works(self):
        product = POWDER | {
            "ingredients": [
                {"name": "sodium benzoate", "normalized": "sodium_benzoate",
                 "amount": 100, "unit": "mg_per_kg"}
            ]
        }
        assert clause_binds(product, clause(substance_normalized="benzoic_acid"), EU)


class TestTheJurisdictionGateIsUntouched:
    def test_another_jurisdiction_never_binds(self):
        assert not clause_binds(POWDER, clause(jurisdiction="ID_BPOM"), EU)
