"""The guardrail: deterministic code that decides WHETHER two clauses may be compared.

The LLM judge never sees an incomparable pair and never writes state. Every rule
here is ordinary Python so it can be pointed at during the demo and tested
without any framework in the loop.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.scope import categories_comparable, category_of


@dataclass(frozen=True)
class ComparablePair:
    a: dict
    b: dict
    # Values brought to one basis so the numeric compare later is honest.
    value_a: float | None
    value_b: float | None
    basis_unit: str


@dataclass(frozen=True)
class IncomparablePair:
    reason: str


ComparableOrNot = ComparablePair | IncomparablePair


# The ONLY conversions allowed — inferred conversions are how false conflicts
# get manufactured. percent_w_w ↔ mg_per_kg ↔ ppm, weight basis throughout.
_CONVERSIONS_TO_MG_PER_KG: dict[str, float] = {
    "percent_w_w": 10_000.0,
    "mg_per_kg": 1.0,
    "ppm": 1.0,
}


def to_mg_per_kg(value: float | None, unit: str | None) -> float | None:
    """Convert a limit to mg/kg, or return None when not convertible."""
    if value is None:
        return None
    factor = _CONVERSIONS_TO_MG_PER_KG.get(unit or "")
    if factor is None:
        return None
    return value * factor


# Substance families: jurisdictions regulate the same chemistry under different
# names. The EU limits "Benzoic acid — benzoates (E 210-213)" as a group; BPOM
# limits "Natrium benzoat … dihitung sebagai asam benzoat" (computed as benzoic
# acid). Comparing them is not a guess — both documents state the shared basis.
_SUBSTANCE_FAMILIES: dict[str, list[str]] = {
    "benzoic_acid": ["benzoic_acid", "sodium_benzoate", "potassium_benzoate", "calcium_benzoate"],
    "sorbic_acid": ["sorbic_acid", "potassium_sorbate"],
}


def substances_comparable(a: str | None, b: str | None) -> bool:
    """Equal keys, or members of one documented substance family."""
    if not a or not b:
        return False
    if a == b:
        return True
    return any(a in family and b in family for family in _SUBSTANCE_FAMILIES.values())


# A drink powder is regulated as the drink you make from it: the BPOM tables say
# so in as many words ("dihitung terhadap produk siap konsumsi", computed on the
# ready-to-consume product), and the EU beverage categories cover powders for
# home preparation in the same rows. No other family exists — a cosmetic limit
# never binds a food.
_PRODUCT_TYPE_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"food_beverage_powder", "food_beverage_liquid"}),
)


def product_types_comparable(a: str | None, b: str | None) -> bool:
    """May a rule written for product type `a` be applied to product type `b`?

    `None` on either side means the source did not say, which is treated as
    "any product type" — the documented superset, and the only one. Everything
    else must match exactly or share a family.

    This matters more than it looks. Once the bundled library is loaded the
    graph holds limits for dairy desserts, bakery wares and supplements as well
    as drinks; without this check a drink powder is judged against a jam.
    """
    if a is None or b is None:
        return True
    if a == b:
        return True
    return any(a in family and b in family for family in _PRODUCT_TYPE_FAMILIES)


def comparability(a: dict, b: dict) -> ComparableOrNot:
    """May these two clauses be compared at all? Returns a ComparablePair with
    values on one basis, or an IncomparablePair with a reason enum.

    `a` and `b` are clause dicts (or Pydantic dumps) with at least:
    substance_normalized, unit (enum string), limit_value, product_type,
    clause_type.
    """
    if a.get("clause_type") != "numeric_limit" or b.get("clause_type") != "numeric_limit":
        return IncomparablePair(reason="not_both_numeric_limits")
    if not a.get("substance_normalized") or not b.get("substance_normalized"):
        return IncomparablePair(reason="missing_substance")
    if not substances_comparable(a["substance_normalized"], b["substance_normalized"]):
        return IncomparablePair(reason="substance_mismatch")
    if a.get("unit") not in _CONVERSIONS_TO_MG_PER_KG or b.get("unit") in (None, ""):
        return IncomparablePair(reason="unit_mismatch")
    if b.get("unit") not in _CONVERSIONS_TO_MG_PER_KG:
        return IncomparablePair(reason="unit_mismatch")
    if not product_types_comparable(a.get("product_type"), b.get("product_type")):
        return IncomparablePair(reason="product_type_mismatch")
    # The food category the regulator printed at the head of the row. Two
    # limits from different branches of the GSFA tree are two different foods,
    # so they are not a supersede question, not a conflict, and not something
    # to ask a person about. Silence on either side blocks nothing.
    if not categories_comparable(category_of(a), category_of(b)):
        return IncomparablePair(reason="food_category_mismatch")

    value_a = to_mg_per_kg(a.get("limit_value"), a.get("unit"))
    value_b = to_mg_per_kg(b.get("limit_value"), b.get("unit"))
    if value_a is None or value_b is None:
        return IncomparablePair(reason="limit_value_missing")
    return ComparablePair(a=a, b=b, value_a=value_a, value_b=value_b, basis_unit="mg_per_kg")


def relationship_class(a: dict, b: dict, *, values: tuple[float, float] | None = None) -> str:
    """Deterministic pre-judge classification. Never calls a model.

    - same jurisdiction → supersede question (which is current?)
    - different jurisdiction → cross-jurisdiction conflict (both hold)
    - numerically equal limits → no finding; the model is never asked to
      confirm that 0.05 equals 0.05.
    """
    va, vb = values if values else (
        to_mg_per_kg(a.get("limit_value"), a.get("unit")) or 0.0,
        to_mg_per_kg(b.get("limit_value"), b.get("unit")) or 0.0,
    )
    if va == vb:
        return "equal_no_finding"
    if str(a.get("jurisdiction", "")).upper() == str(b.get("jurisdiction", "")).upper():
        return "supersede_question"
    return "cross_jurisdiction_conflict"