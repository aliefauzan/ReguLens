"""Adding a market for a country the product form offers.

The form lists every country, not only the ones somebody has watched. Selecting
one has to create its market first: `impact.evaluate` keeps only the target
markets it finds in the `markets` collection, so a product pointed at a market
with no document loses that country entirely — no verdict row, not even
`unknown`, and no error anywhere. These tests hold that contract.

No Firestore: `ensure_market` is stubbed, because what is under test is the
route — the country name comes from the bundled ISO list, an unknown code is
refused, and a repeat press is not an error.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def ensured(monkeypatch):
    """Records every ensure_market call and serves the market back."""
    calls: list[dict] = []

    def fake_ensure(**kwargs):
        calls.append(kwargs)
        code = kwargs["country_code"].lower()
        return f"market_{code}", len(calls) == 1

    monkeypatch.setattr("app.core.markets.ensure_market", fake_ensure)
    monkeypatch.setattr(
        "app.core.markets.list_markets",
        lambda: [
            {
                "id": "market_fr",
                "country": "France",
                "country_code": "FR",
                "jurisdictions": ["FR"],
                "label": "France",
                "regulator": None,
            }
        ],
    )
    return calls


def test_adding_a_country_creates_its_market(ensured) -> None:
    response = client.post("/markets", json={"country_code": "FR"})
    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["market"]["id"] == "market_fr"
    # The name is taken from the bundled list, never from the caller.
    assert ensured == [{"country_code": "FR", "country_name": "France"}]


def test_a_market_added_by_hand_names_no_regulator(ensured) -> None:
    """Nobody has looked for France's regulator yet, and the label must not
    pretend otherwise. The verdict for such a market reads "no rules added
    yet" until a source is watched."""
    client.post("/markets", json={"country_code": "FR"})
    assert "regulator" not in ensured[0]


def test_adding_the_same_country_twice_is_not_an_error(ensured) -> None:
    client.post("/markets", json={"country_code": "FR"})
    second = client.post("/markets", json={"country_code": "fr"})
    assert second.status_code == 201
    assert second.json()["created"] is False


def test_an_unknown_country_is_refused(ensured) -> None:
    response = client.post("/markets", json={"country_code": "ZZ"})
    assert response.status_code == 400
    assert ensured == []


def test_a_malformed_code_never_reaches_the_write(ensured) -> None:
    assert client.post("/markets", json={"country_code": "FRANCE"}).status_code == 422
    assert ensured == []
