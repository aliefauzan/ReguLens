"""A verdict for a product nobody saved.

The only way to answer "what if we cut it to 120 mg/kg" used to be to save a
real product, wait for the pipeline, read the answer and delete it again. These
tests pin the preview — and, more importantly, pin that it agrees with the
engine it previews and writes nothing on the way.
"""

from datetime import date, timedelta

import pytest

from app.core import simulation

TODAY = date(2026, 8, 30)
NEXT_YEAR = (TODAY + timedelta(days=365)).isoformat()

MARKETS = [
    {"id": "market_de", "label": "EU — Germany", "jurisdictions": ["EU"]},
    {"id": "market_id", "label": "Indonesia", "jurisdictions": ["ID_BPOM"]},
]


def clause(**overrides) -> dict:
    base = {
        "id": "clause_eu",
        "document_id": "doc_eu",
        "jurisdiction": "EU",
        "clause_type": "numeric_limit",
        "substance_normalized": "sodium_benzoate",
        "limit_value": 150.0,
        "unit": "mg_per_kg",
        "product_type": "food_beverage_liquid",
        "effective_date": None,
        "confidence": 0.9,
    }
    return base | overrides


def product(amount: float | None = 300.0, markets=("market_de",)) -> dict:
    return {
        "name": "hypothetical",
        "product_type": "food_beverage_liquid",
        "target_markets": list(markets),
        "ingredients": [
            {"name": "sodium benzoate", "normalized": "sodium_benzoate",
             "amount": amount, "unit": "mg_per_kg"}
        ],
    }


@pytest.fixture
def graph(monkeypatch):
    def install(clauses: list[dict], markets: list[dict] | None = None):
        monkeypatch.setattr(simulation, "clauses_active", lambda: clauses)
        monkeypatch.setattr(simulation, "markets_all", lambda: markets or MARKETS)

    return install


def test_an_over_limit_recipe_fails_without_being_saved(graph):
    graph([clause()])
    result = simulation.simulate(product(300.0), TODAY)
    assert result["statuses"] == {"market_de": "non_compliant"}
    assert result["simulated"] is True


def test_the_reformulation_that_fixes_it_reads_compliant(graph):
    """The sentence the feature exists for: cut it to 120 and you may ship."""
    graph([clause()])
    assert simulation.simulate(product(120.0), TODAY)["statuses"] == {"market_de": "compliant"}


def test_the_strictest_limit_across_target_markets_is_returned(graph):
    graph([
        clause(),
        clause(id="clause_id", jurisdiction="ID_BPOM", limit_value=400.0, document_id="doc_id"),
    ])
    result = simulation.simulate(product(300.0, ("market_de", "market_id")), TODAY)
    row = result["binding_limits"]["substances"][0]
    assert row["binding_limit"] == 150.0
    assert row["verdict"] == "fail"


def test_a_rule_not_yet_in_force_does_not_fail_the_hypothetical(graph):
    """Consistent with the real engine, or the preview is not a preview."""
    graph([clause(limit_value=50.0, effective_date=NEXT_YEAR)])
    assert simulation.simulate(product(120.0), TODAY)["statuses"] == {"market_de": "compliant"}


def test_a_rule_for_another_kind_of_product_does_not_bind(graph):
    """Same guardrail as the engine: a dairy-dessert limit is not a drink rule."""
    graph([clause(product_type="food_solid")])
    assert simulation.simulate(product(300.0), TODAY)["statuses"] == {"market_de": "unknown"}


def test_a_market_the_product_does_not_target_is_not_evaluated(graph):
    graph([clause(), clause(id="clause_id", jurisdiction="ID_BPOM", limit_value=400.0)])
    result = simulation.simulate(product(300.0, ("market_de",)), TODAY)
    assert set(result["statuses"]) == {"market_de"}


def test_an_unknown_amount_needs_a_person_rather_than_passing(graph):
    graph([clause()])
    assert simulation.simulate(product(None), TODAY)["statuses"] == {
        "market_de": "attention_required"
    }


def test_simulating_writes_nothing(monkeypatch, graph):
    """The whole point of being callable from a form on every keystroke."""
    import app.core.repository as repository

    def explode(*_a, **_k):  # pragma: no cover - the assertion is that it never runs
        raise AssertionError("a simulation must not write")

    monkeypatch.setattr(repository, "write_with_event", explode)
    graph([clause()])
    simulation.simulate(product(300.0), TODAY)
