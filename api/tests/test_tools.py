"""The point of this test: the tool body is callable directly, with no ADK
runner, no agent, and no network. If this ever needs a framework to run, the
core/adk separation has been broken."""

import app.core.tools as tools

MARKETS = [
    {"id": "market_de", "country": "Germany", "country_code": "DE", "jurisdictions": ["EU"]},
    {"id": "market_id", "country": "Indonesia", "country_code": "ID", "jurisdictions": ["ID_BPOM"]},
]


def test_lookup_market_finds_by_country_code(monkeypatch):
    monkeypatch.setattr(tools, "list_markets", lambda: MARKETS)
    result = tools.lookup_market("id")
    assert result["found"] is True
    assert result["market"]["country"] == "Indonesia"


def test_lookup_market_finds_by_jurisdiction(monkeypatch):
    monkeypatch.setattr(tools, "list_markets", lambda: MARKETS)
    assert tools.lookup_market("ID_BPOM")["market"]["id"] == "market_id"


def test_lookup_market_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(tools, "list_markets", lambda: MARKETS)
    assert tools.lookup_market("Eu")["found"] is True


def test_miss_returns_structured_result_rather_than_raising(monkeypatch):
    monkeypatch.setattr(tools, "list_markets", lambda: MARKETS)
    result = tools.lookup_market("US")
    assert result == {"found": False, "jurisdiction": "US"}
