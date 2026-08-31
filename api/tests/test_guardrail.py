"""Zero false conflicts, proven over adversarial pairs.

The guardrail is the architectural thesis: the judge never sees an incomparable
pair. Every test here is a pair that must NOT produce a finding.
"""

from app.core.guardrail import (
    ComparablePair,
    IncomparablePair,
    comparability,
    relationship_class,
    to_mg_per_kg,
)

EU = "EU"
BPOM = "ID_BPOM"


def clause(**over):
    base = {
        "id": "clause_a",
        "clause_type": "numeric_limit",
        "substance_normalized": "sodium_benzoate",
        "limit_value": 0.05,
        "unit": "percent_w_w",
        "product_type": "food_beverage_powder",
        "jurisdiction": EU,
    }
    base.update(over)
    return base


def test_same_substance_same_jurisdiction_lower_limit_is_supersede_question():
    a = clause(limit_value=0.05)
    b = clause(limit_value=0.10, jurisdiction="EU")
    assert relationship_class(a, b) == "supersede_question"


def test_different_jurisdiction_is_cross_jurisdiction_conflict():
    a = clause(limit_value=0.05, jurisdiction=EU)
    b = clause(limit_value=0.10, jurisdiction=BPOM)
    assert relationship_class(a, b) == "cross_jurisdiction_conflict"


def test_numerically_equal_limits_produce_no_finding():
    a = clause(limit_value=0.10, jurisdiction=EU)
    b = clause(limit_value=1000, unit="mg_per_kg", jurisdiction=BPOM)
    guard = comparability(a, b)
    assert isinstance(guard, ComparablePair)
    assert relationship_class(a, b, values=(guard.value_a, guard.value_b)) == "equal_no_finding"


def test_percent_converts_to_mg_per_kg():
    assert to_mg_per_kg(0.05, "percent_w_w") == 500.0
    assert to_mg_per_kg(150, "mg_per_kg") == 150.0
    assert to_mg_per_kg(500, "ppm") == 500.0


def test_different_substance_is_incomparable():
    guard = comparability(clause(), clause(substance_normalized="carmine"))
    assert isinstance(guard, IncomparablePair)
    assert guard.reason == "substance_mismatch"


def test_benzoate_family_compares_across_jurisdictions():
    """EU limits the group 'Benzoic acid — benzoates'; BPOM limits natrium
    benzoat computed as benzoic acid. Same chemistry, documented shared basis."""
    eu = clause(substance_normalized="benzoic_acid", limit_value=150, unit="mg_per_kg")
    bpom = clause(substance_normalized="sodium_benzoate", jurisdiction=BPOM,
                  limit_value=400, unit="mg_per_kg")
    guard = comparability(eu, bpom)
    assert isinstance(guard, ComparablePair)
    cls = relationship_class(eu, bpom, values=(guard.value_a, guard.value_b))
    assert cls == "cross_jurisdiction_conflict"


def test_different_product_type_is_incomparable():
    guard = comparability(clause(), clause(product_type="cosmetic"))
    assert isinstance(guard, IncomparablePair)
    assert guard.reason == "product_type_mismatch"


def test_wildcard_product_type_is_comparable():
    guard = comparability(clause(), clause(product_type=None))
    assert isinstance(guard, ComparablePair)


def test_incompatible_units_are_incomparable():
    guard = comparability(clause(), clause(unit="cups_per_gallon"))
    assert isinstance(guard, IncomparablePair)
    assert guard.reason == "unit_mismatch"


def test_non_numeric_clauses_never_compare():
    guard = comparability(clause(), clause(clause_type="labeling"))
    assert isinstance(guard, IncomparablePair)
    assert guard.reason == "not_both_numeric_limits"


def test_missing_limit_is_incomparable():
    guard = comparability(clause(), clause(limit_value=None))
    assert isinstance(guard, IncomparablePair)
    assert guard.reason == "limit_value_missing"


def test_percent_vs_mg_per_kg_compares_on_one_basis():
    guard = comparability(
        clause(limit_value=0.05),  # 500 mg/kg
        clause(limit_value=150, unit="mg_per_kg"),
    )
    assert isinstance(guard, ComparablePair)
    assert guard.value_a == 500.0
    assert guard.value_b == 150.0
    assert guard.value_a > guard.value_b

def test_a_powder_and_the_drink_made_from_it_are_the_same_product_kind():
    """BPOM writes its beverage limits "dihitung terhadap produk siap konsumsi"
    — computed on the ready-to-consume drink — so a rule for the drink is a rule
    for the powder you make it from."""
    guard = comparability(clause(), clause(product_type="food_beverage_liquid"))
    assert isinstance(guard, ComparablePair)


def test_a_rule_for_another_kind_of_food_does_not_bind():
    """The check that keeps the bundled library honest: it carries limits for
    dairy desserts and bakery wares too, and none of those judge a drink."""
    from app.core.guardrail import product_types_comparable

    assert not product_types_comparable("food_solid", "food_beverage_powder")
    assert not product_types_comparable("supplement", "food_beverage_liquid")
    # A source that does not say which products it covers still binds; that is
    # the documented wildcard, not an accident.
    assert product_types_comparable(None, "food_solid")


# --- Curing salts -----------------------------------------------------------
# Added after the deployed stack read the whole nitrite table of Commission
# Regulation (EU) 2023/2108 into the graph and bound nothing with it: the rule
# says "nitrites", a recipe says "sodium nitrite", and nothing joined the two.


def test_group_row_and_named_member_are_the_same_substance():
    a = clause(substance_normalized="nitrites")
    b = clause(substance_normalized="sodium_nitrite")
    assert isinstance(comparability(a, b), ComparablePair)


def test_the_other_nitrite_of_the_pair_is_in_the_family_too():
    a = clause(substance_normalized="nitrites")
    b = clause(substance_normalized="potassium_nitrite")
    assert isinstance(comparability(a, b), ComparablePair)


def test_nitrates_are_their_own_family():
    a = clause(substance_normalized="nitrates")
    b = clause(substance_normalized="potassium_nitrate")
    assert isinstance(comparability(a, b), ComparablePair)


def test_a_nitrite_limit_never_binds_a_nitrate_ingredient():
    """The two groups sit on adjacent rows of the same table and cap different
    chemistry. Widening one family must not quietly merge them."""
    a = clause(substance_normalized="nitrites")
    b = clause(substance_normalized="sodium_nitrate")
    assert isinstance(comparability(a, b), IncomparablePair)


def test_a_curing_salt_limit_never_binds_a_benzoate():
    a = clause(substance_normalized="nitrites")
    b = clause(substance_normalized="sodium_benzoate")
    assert isinstance(comparability(a, b), IncomparablePair)
