"""Two countries disagreeing is not an answer. One number to ship is.

The graph could already say "the EU allows 150 and Indonesia allows 400, and
those disagree". A company with one recipe and two markets cannot act on that.
These tests pin the sentence it can act on — the lowest limit still in force,
and which country sets it.
"""

from datetime import date, timedelta

import pytest

from app.core import strictest

TODAY = date(2026, 8, 30)
NEXT_YEAR = (TODAY + timedelta(days=365)).isoformat()

MARKETS = [
    {"id": "market_de", "label": "European Union — Germany"},
    {"id": "market_id", "label": "Indonesia (BPOM)"},
]


def requirement(**overrides) -> dict:
    base = {
        "market_id": "market_de",
        "jurisdiction": "EU",
        "substance_normalized": "sodium_benzoate",
        "comparable_limit": 150.0,
        "comparable_value": 100.0,
        "effective_date": None,
        "clause_id": "clause_eu",
        "document_id": "doc_eu",
    }
    return base | overrides


@pytest.fixture
def graph(monkeypatch):
    def install(requirements: list[dict], markets: list[dict] | None = None):
        monkeypatch.setattr(strictest, "_requirements_for", lambda _pid: requirements)
        monkeypatch.setattr(strictest, "_target_markets", lambda _pid: markets or MARKETS)

    return install


def test_the_lowest_limit_binds_and_names_the_country_that_sets_it(graph):
    graph([
        requirement(),
        requirement(market_id="market_id", jurisdiction="ID_BPOM",
                    comparable_limit=400.0, clause_id="clause_id"),
    ])
    row = strictest.binding_limits("prod_1", TODAY)["substances"][0]
    assert row["binding_limit"] == 150.0
    assert row["binding_market_id"] == "market_de"
    assert row["binding_jurisdiction"] == "EU"
    assert row["binding_clause_id"] == "clause_eu"


def test_the_spread_is_shown_not_just_the_winner(graph):
    """A single number asks to be trusted. The spread shows the working."""
    graph([
        requirement(),
        requirement(market_id="market_id", comparable_limit=400.0),
    ])
    row = strictest.binding_limits("prod_1", TODAY)["substances"][0]
    assert [x["limit"] for x in row["limits_by_market"]] == [150.0, 400.0]


def test_the_product_is_judged_against_the_binding_limit(graph):
    graph([
        requirement(comparable_value=300.0),
        requirement(market_id="market_id", comparable_limit=400.0, comparable_value=300.0),
    ])
    row = strictest.binding_limits("prod_1", TODAY)["substances"][0]
    # 300 is legal in Indonesia and illegal in the EU. One recipe, so it fails.
    assert row["verdict"] == "fail"


def test_a_product_under_the_strictest_limit_passes(graph):
    graph([requirement(comparable_value=100.0)])
    assert strictest.binding_limits("prod_1", TODAY)["substances"][0]["verdict"] == "pass"


def test_an_unknown_product_amount_is_not_a_pass(graph):
    graph([requirement(comparable_value=None)])
    assert strictest.binding_limits("prod_1", TODAY)["substances"][0]["verdict"] == "unknown"


def test_a_rule_not_yet_in_force_does_not_bind_the_recipe(graph):
    """Consistent with the verdict engine: a 2027 limit is not today's ceiling."""
    graph([
        requirement(),
        requirement(comparable_limit=50.0, effective_date=NEXT_YEAR, clause_id="clause_2027"),
    ])
    row = strictest.binding_limits("prod_1", TODAY)["substances"][0]
    assert row["binding_limit"] == 150.0


def test_markets_with_no_rule_for_the_substance_are_named(graph):
    """"Strictest of the markets that regulate it" and "strictest of everywhere
    you sell" are different claims. Only the first is true."""
    graph([requirement()])
    row = strictest.binding_limits("prod_1", TODAY)["substances"][0]
    assert row["markets_without_a_rule"] == ["market_id"]


def test_a_rule_that_cannot_be_compared_is_counted_not_dropped(graph):
    """A labelling clause has no number. Hiding it would present a partial
    answer as a complete one."""
    graph([
        requirement(),
        requirement(comparable_limit=None, clause_id="clause_labelling"),
    ])
    result = strictest.binding_limits("prod_1", TODAY)
    assert result["skipped"]["uncomparable_rules"] == 1
    assert result["substances"][0]["uncomparable_rules"] == 1
    assert result["substances"][0]["binding_limit"] == 150.0


def test_each_substance_gets_its_own_binding_limit(graph):
    graph([
        requirement(),
        requirement(substance_normalized="sorbic_acid", comparable_limit=300.0),
    ])
    rows = strictest.binding_limits("prod_1", TODAY)["substances"]
    assert [r["substance_normalized"] for r in rows] == ["sodium_benzoate", "sorbic_acid"]


def test_a_tie_resolves_the_same_way_every_read(graph):
    """Firestore does not promise an order. A verdict that changes between two
    reads of unchanged data is its own bug."""
    graph([
        requirement(market_id="market_id", clause_id="clause_b"),
        requirement(market_id="market_de", clause_id="clause_a"),
    ])
    first = strictest.binding_limits("prod_1", TODAY)["substances"][0]
    second = strictest.binding_limits("prod_1", TODAY)["substances"][0]
    assert first["binding_market_id"] == second["binding_market_id"] == "market_de"


def test_no_requirements_is_an_empty_answer_not_a_zero_limit(graph):
    graph([])
    assert strictest.binding_limits("prod_1", TODAY)["substances"] == []
