"""Relevance — which rules could bear on what this workspace actually makes.

Written after the review queue reached two hundred entries, every one of them
the guardrail behaving correctly and almost none of them about anything the
workspace sells. The danger in fixing that is obvious and worth pinning: a
filter that is a shade too clever hides a rule that mattered, and it hides it
silently, which is the one failure this codebase keeps refusing to ship.

So the tests below are mostly about what must NOT be filtered.
"""

import pytest

from app.core import relevance
from app.core.relevance import Workspace

MARKETS = [
    {"id": "market_de", "jurisdictions": ["EU"], "label": "European Union — Germany"},
    {"id": "market_id", "jurisdictions": ["ID_BPOM"], "label": "Indonesia — BPOM"},
]

DRINK_POWDER = {
    "name": "Herbal Drink Powder",
    "product_type": "food_beverage_powder",
    "target_markets": ["market_de", "market_id"],
    "ingredients": [
        {"name": "sodium benzoate", "normalized": "sodium_benzoate"},
        {"name": "ginger", "normalized": "ginger"},
    ],
}


def workspace(*products) -> Workspace:
    return relevance.build_workspace(list(products), MARKETS)


def clause(**overrides) -> dict:
    base = {
        "jurisdiction": "EU",
        "substance_normalized": "sodium_benzoate",
        "product_type": "food_beverage_powder",
    }
    return base | overrides


# ---------------------------------------------------------------------------
# What the workspace is
# ---------------------------------------------------------------------------


def test_the_workspace_collects_jurisdictions_through_its_markets():
    """A product targets a market; a rule names a jurisdiction. Without the
    market table in between, every EU rule looks foreign."""
    space = workspace(DRINK_POWDER)
    assert space.jurisdictions == {"EU", "ID_BPOM"}


def test_an_unrecognised_ingredient_is_not_added_to_the_workspace():
    """An ingredient normalization could not place matches no clause anyway.
    Adding its raw name here would widen the filter on exactly the products
    whose ingredients the app already says it cannot check."""
    space = workspace(
        {
            "product_type": "food_solid",
            "target_markets": ["market_de"],
            "ingredients": [{"name": "mystery powder X", "unnormalized": True}],
        }
    )
    assert space.substances == set()


# ---------------------------------------------------------------------------
# What survives the filter — the important half
# ---------------------------------------------------------------------------


def test_a_rule_about_an_ingredient_we_use_is_kept():
    assert relevance.assess(clause(), workspace(DRINK_POWDER)).relevant


def test_a_rule_naming_no_substance_is_kept():
    """Labelling and documentation requirements usually apply across a whole
    category. There is nothing in them to rule out, so they are shown."""
    verdict = relevance.assess(
        clause(substance_normalized=None, product_type=None), workspace(DRINK_POWDER)
    )
    assert verdict.relevant


def test_a_rule_with_no_stated_product_type_still_binds():
    """The documented wildcard. An unstated type is not permission to ignore
    the rule — that decision is already recorded in the guardrail."""
    assert relevance.assess(clause(product_type=None), workspace(DRINK_POWDER)).relevant


def test_the_benzoate_family_equivalence_is_honoured():
    """EU limits the benzoate group; BPOM names natrium benzoat. A workspace
    holding one is affected by a rule naming the other, and this filter must not
    be the place that quietly forgets it."""
    space = workspace(DRINK_POWDER)
    verdict = relevance.assess(clause(substance_normalized="benzoic_acid"), space)
    assert verdict.relevant, "the documented family equivalence was dropped"


def test_nothing_is_filtered_when_the_workspace_has_no_products():
    """A brand-new user is the one person who most needs to see that the app
    knows something. Filtering here empties the rulebook."""
    verdict = relevance.assess(clause(jurisdiction="JP"), workspace())
    assert verdict.relevant
    assert verdict.reason == relevance.NO_PRODUCTS


def test_a_rule_for_a_second_product_is_kept_once_that_product_exists():
    """The whole reason relevance is computed on read: adding a product must
    change what the queue shows, with no migration and no recompute."""
    cosmetic_rule = clause(substance_normalized="paraben", product_type="cosmetic")
    assert not relevance.assess(cosmetic_rule, workspace(DRINK_POWDER)).relevant

    with_cosmetic = workspace(
        DRINK_POWDER,
        {
            "product_type": "cosmetic",
            "target_markets": ["market_de"],
            "ingredients": [{"name": "paraben", "normalized": "paraben"}],
        },
    )
    assert relevance.assess(cosmetic_rule, with_cosmetic).relevant


# ---------------------------------------------------------------------------
# What is held back
# ---------------------------------------------------------------------------


def test_a_rule_for_a_market_we_do_not_sell_in_is_held_back():
    verdict = relevance.assess(clause(jurisdiction="JP"), workspace(DRINK_POWDER))
    assert not verdict.relevant
    assert verdict.reason == relevance.NO_MARKET


def test_a_rule_about_a_substance_we_do_not_use_is_held_back():
    """The case that produced two hundred review entries: real EU nitrite
    limits for cured meats, read correctly, against a drink powder."""
    verdict = relevance.assess(clause(substance_normalized="nitrite"), workspace(DRINK_POWDER))
    assert not verdict.relevant
    assert verdict.reason == relevance.SUBSTANCE_ABSENT


def test_a_rule_for_a_kind_of_product_we_do_not_make_is_held_back():
    verdict = relevance.assess(
        clause(substance_normalized=None, product_type="cosmetic"), workspace(DRINK_POWDER)
    )
    assert not verdict.relevant
    assert verdict.reason == relevance.PRODUCT_TYPE_ABSENT


# ---------------------------------------------------------------------------
# Never silently
# ---------------------------------------------------------------------------


def test_partition_reports_what_it_held_back_and_why():
    """A caller that shows the kept list without this tally is hiding rules.
    The count is what lets the UI say '148 not shown, here is why'."""
    clauses = [
        clause(),
        clause(jurisdiction="JP"),
        clause(substance_normalized="nitrite"),
        clause(substance_normalized="nitrate"),
    ]
    kept, held_back = relevance.partition(clauses, workspace(DRINK_POWDER))
    assert len(kept) == 1
    assert held_back == {relevance.NO_MARKET: 1, relevance.SUBSTANCE_ABSENT: 2}
    assert sum(held_back.values()) == len(clauses) - len(kept)


@pytest.mark.parametrize(
    "reason",
    [relevance.NO_MARKET, relevance.SUBSTANCE_ABSENT, relevance.PRODUCT_TYPE_ABSENT],
)
def test_no_reason_token_claims_the_rule_is_wrong(reason):
    """Irrelevant is not incorrect. The app has no opinion on a regulation it
    cannot apply, and the vocabulary must not smuggle one in."""
    assert not any(word in reason for word in ("invalid", "wrong", "bad", "reject"))
