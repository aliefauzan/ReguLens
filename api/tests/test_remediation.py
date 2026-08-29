"""The draft fix plan.

Every assertion here is about one of two failure modes, because the arithmetic
itself is trivial:

  the wrong number   quoting the limit that happens to be on screen instead of
                     the strictest one across the markets they actually sell
                     into. A person who hits it still cannot ship.

  a quiet omission   a market we hold no rule for, or an ingredient nothing was
                     checked against, dropping out of the answer. Both read on
                     the page exactly like a pass.

The stand-in Firestore is the same shape as the one in `test_document_delete`;
it is duplicated rather than shared because the two tests need different
document lookups and a shared fake would grow to serve both.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import remediation
from app.main import app


class _Snapshot:
    def __init__(self, doc_id: str, data: dict | None) -> None:
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict | None:
        return self._data


class _DocRef:
    """Read-only on purpose: no `set`, no `update`, no `delete`. If this feature
    ever grows a write, the test suite fails with an AttributeError rather than
    quietly mutating state."""

    def __init__(self, doc_id: str, data: dict | None) -> None:
        self._doc_id = doc_id
        self._data = data

    def get(self) -> _Snapshot:
        return _Snapshot(self._doc_id, self._data)


class _Query:
    def __init__(self, rows: list[_Snapshot]) -> None:
        self._rows = rows

    def where(self, filter=None):  # noqa: A002 - mirrors the Firestore signature
        field, op, value = filter.field_path, filter.op_string, filter.value
        kept = []
        for row in self._rows:
            actual = (row.to_dict() or {}).get(field)
            if op == "==" and actual == value:
                kept.append(row)
            elif op == "in" and actual in value:
                kept.append(row)
        return _Query(kept)

    def limit(self, n: int):
        return _Query(self._rows[:n])

    def stream(self):
        return iter(self._rows)


class _Collection:
    def __init__(self, rows: dict[str, dict]) -> None:
        self._rows = rows

    def _snapshots(self) -> list[_Snapshot]:
        return [_Snapshot(doc_id, data) for doc_id, data in self._rows.items()]

    def where(self, filter=None):  # noqa: A002
        return _Query(self._snapshots()).where(filter=filter)

    def limit(self, n: int):
        return _Query(self._snapshots()).limit(n)

    def stream(self):
        return iter(self._snapshots())

    def document(self, doc_id: str) -> _DocRef:
        return _DocRef(doc_id, self._rows.get(doc_id))


class _DB:
    def __init__(self, collections: dict[str, dict[str, dict]]) -> None:
        self._collections = collections

    def collection(self, name: str):
        return _Collection(self._collections.get(name, {}))


def _requirement(
    req_id: str,
    *,
    market_id: str,
    clause_id: str,
    substance: str = "benzoic_acid",
    limit: float | None = 150.0,
    product_value: float | None = 400.0,
    evaluation: str = "fail",
    reason: str | None = None,
) -> tuple[str, dict]:
    return req_id, {
        "product_id": "prod_1",
        "market_id": market_id,
        "clause_id": clause_id,
        "document_id": f"doc_{market_id}",
        "substance_normalized": substance,
        "limit_value": limit,
        "unit": "mg_per_kg",
        "product_value": product_value,
        "product_unit": "mg_per_kg",
        "comparable_value": product_value,
        "comparable_limit": limit,
        "comparable_unit": "mg_per_kg" if limit is not None else None,
        "evaluation": evaluation,
        "severity": "high" if evaluation == "fail" else "medium",
        "reason": reason,
    }


PRODUCT = {
    "name": "Herbal Drink Powder",
    "product_type": "food_beverage_powder",
    "target_markets": ["market_de", "market_id"],
    "ingredients": [
        {"name": "sodium benzoate", "normalized": "sodium_benzoate", "amount": 400.0,
         "unit": "mg_per_kg", "unnormalized": False},
    ],
}

CLAUSES = {
    "clause_eu": {
        "document_id": "doc_market_de",
        "text": "| E 210-213 | Benzoic acid — benzoates | 150 |",
        "effective_date": "2011-12-02",
    },
    "clause_bpom": {
        "document_id": "doc_market_id",
        "text": "Natrium benzoat, dihitung sebagai asam benzoat: 400 mg/kg.",
        "effective_date": "2019-01-01",
    },
}


def _wire(monkeypatch, *, product: dict, requirements: dict, clauses: dict | None = None):
    db = _DB(
        {
            "products": {"prod_1": product},
            "requirements": requirements,
            "clauses": clauses if clauses is not None else CLAUSES,
        }
    )
    monkeypatch.setattr(remediation, "get_db", lambda: db)
    return db


# --- the number ------------------------------------------------------------


def test_two_markets_two_limits_gives_the_strictest_and_names_it(monkeypatch):
    """Meeting Indonesia's 400 still fails Germany. The plan has to say 150,
    and say whose rule that is — a target with no market behind it cannot be
    checked by the person approving it."""
    _wire(
        monkeypatch,
        product=PRODUCT,
        requirements=dict(
            [
                _requirement("req_de", market_id="market_de", clause_id="clause_eu", limit=150.0),
                _requirement(
                    "req_id", market_id="market_id", clause_id="clause_bpom",
                    limit=400.0, evaluation="pass",
                ),
            ]
        ),
    )
    plan = remediation.build_remediation("prod_1")
    assert plan is not None
    [target] = plan["targets"]
    assert target["target_value"] == 150.0
    assert target["target_unit"] == "mg_per_kg"
    assert target["strictest_market_id"] == "market_de"
    assert target["coverage"] == "full"
    assert target["no_target_reason"] is None
    strictest = [limit for limit in target["limits"] if limit["is_strictest"]]
    assert [limit["market_id"] for limit in strictest] == ["market_de"]


def test_each_limit_carries_the_words_it_was_read_from(monkeypatch):
    """A number a reader cannot trace is a number they cannot sign off."""
    _wire(
        monkeypatch,
        product=PRODUCT,
        requirements=dict(
            [
                _requirement("req_de", market_id="market_de", clause_id="clause_eu", limit=150.0),
                _requirement(
                    "req_id", market_id="market_id", clause_id="clause_bpom",
                    limit=400.0, evaluation="pass",
                ),
            ]
        ),
    )
    [target] = remediation.build_remediation("prod_1")["targets"]
    quoted = {limit["market_id"]: limit for limit in target["limits"]}
    assert "Benzoic acid" in quoted["market_de"]["quote"]
    assert quoted["market_de"]["effective_date"] == "2011-12-02"
    assert quoted["market_de"]["citation_href"] == "/documents/doc_market_de?cite=clause_eu"
    assert quoted["market_id"]["quote"].startswith("Natrium benzoat")


def test_a_limit_for_a_market_they_left_does_not_tighten_the_target(monkeypatch):
    """Requirements outlive a market being removed from the product. Asking
    somebody to hit a number no market of theirs requires is a wrong answer."""
    _wire(
        monkeypatch,
        product=PRODUCT | {"target_markets": ["market_id"]},
        requirements=dict(
            [
                _requirement("req_de", market_id="market_de", clause_id="clause_eu", limit=150.0),
                _requirement(
                    "req_id", market_id="market_id", clause_id="clause_bpom", limit=400.0,
                    product_value=500.0,
                ),
            ]
        ),
    )
    [target] = remediation.build_remediation("prod_1")["targets"]
    assert target["target_value"] == 400.0
    assert target["strictest_market_id"] == "market_id"
    assert target["coverage"] == "full"


def test_looser_rows_in_the_same_market_are_counted_not_dropped(monkeypatch):
    """A loaded rulebook holds several rows for one substance in one market.
    The strictest decides; the others are still on the record."""
    _wire(
        monkeypatch,
        product=PRODUCT,
        requirements=dict(
            [
                _requirement("req_de1", market_id="market_de", clause_id="clause_eu", limit=150.0),
                _requirement("req_de2", market_id="market_de", clause_id="clause_eu", limit=300.0),
                _requirement(
                    "req_id", market_id="market_id", clause_id="clause_bpom",
                    limit=400.0, evaluation="pass",
                ),
            ]
        ),
    )
    [target] = remediation.build_remediation("prod_1")["targets"]
    germany = next(limit for limit in target["limits"] if limit["market_id"] == "market_de")
    assert germany["limit"] == 150.0
    assert germany["other_limits_in_market"] == 1


def test_one_substance_family_is_one_target(monkeypatch):
    """The EU limits "Benzoic acid — benzoates"; BPOM limits natrium benzoat
    computed as benzoic acid. Keying on the raw name split them into two
    targets, each quoting its own market's number and each claiming the other
    market had no rule. Found against live data."""
    _wire(
        monkeypatch,
        product=PRODUCT,
        requirements=dict(
            [
                _requirement(
                    "req_de", market_id="market_de", clause_id="clause_eu",
                    substance="benzoic_acid", limit=150.0,
                ),
                _requirement(
                    "req_id", market_id="market_id", clause_id="clause_bpom",
                    substance="sodium_benzoate", limit=400.0,
                ),
            ]
        ),
    )
    targets = remediation.build_remediation("prod_1")["targets"]
    assert len(targets) == 1
    [target] = targets
    assert target["coverage"] == "full"
    assert target["markets_without_rules"] == []
    assert target["target_value"] == 150.0
    assert target["strictest_market_id"] == "market_de"
    assert {limit["market_id"] for limit in target["limits"]} == {"market_de", "market_id"}


def test_unrelated_substances_stay_separate(monkeypatch):
    """The merge must be the documented family and nothing wider — a sorbate
    limit has no business setting a benzoate target."""
    _wire(
        monkeypatch,
        product=PRODUCT,
        requirements=dict(
            [
                _requirement(
                    "req_benz", market_id="market_de", clause_id="clause_eu",
                    substance="benzoic_acid", limit=150.0,
                ),
                _requirement(
                    "req_sorb", market_id="market_de", clause_id="clause_eu",
                    substance="sorbic_acid", limit=300.0,
                ),
            ]
        ),
    )
    targets = remediation.build_remediation("prod_1")["targets"]
    assert {t["substance"] for t in targets} == {"benzoic_acid", "sorbic_acid"}
    assert {t["target_value"] for t in targets} == {150.0, 300.0}


# --- the omissions ---------------------------------------------------------


def test_a_market_with_no_rule_is_named_not_left_out(monkeypatch):
    """Silence here reads as a pass. The uncovered market has to appear in the
    answer by name, and the coverage flag has to say so."""
    _wire(
        monkeypatch,
        product=PRODUCT,
        requirements=dict(
            [_requirement("req_de", market_id="market_de", clause_id="clause_eu", limit=150.0)]
        ),
    )
    [target] = remediation.build_remediation("prod_1")["targets"]
    assert target["coverage"] == "partial"
    assert target["markets_without_rules"] == ["market_id"]
    assert target["target_value"] == 150.0  # still computed from what we hold


def test_no_convertible_limit_gives_no_number_and_says_why(monkeypatch):
    """Inventing a target is the one thing this feature must never do."""
    _wire(
        monkeypatch,
        product=PRODUCT,
        requirements=dict(
            [
                _requirement(
                    "req_de", market_id="market_de", clause_id="clause_eu",
                    limit=None, reason="unit_unconvertible",
                ),
            ]
        ),
    )
    # A failing requirement with nothing comparable behind it.
    plan = remediation.build_remediation("prod_1")
    [target] = plan["targets"]
    assert target["target_value"] is None
    assert target["no_target_reason"] == remediation.NO_TARGET_NO_COMPARABLE_LIMIT
    assert target["no_target_reason_text"]


def test_an_ingredient_with_no_amount_is_listed_as_unchecked(monkeypatch):
    _wire(
        monkeypatch,
        product=PRODUCT
        | {
            "ingredients": PRODUCT["ingredients"]
            + [
                {"name": "potassium sorbate", "normalized": "potassium_sorbate",
                 "amount": None, "unit": None, "unnormalized": False}
            ]
        },
        requirements=dict(
            [
                _requirement("req_de", market_id="market_de", clause_id="clause_eu", limit=150.0),
                _requirement(
                    "req_sorb", market_id="market_de", clause_id="clause_eu",
                    substance="sorbic_acid", limit=300.0, product_value=None,
                    evaluation="needs_review", reason="product_amount_unknown",
                ),
            ]
        ),
    )
    plan = remediation.build_remediation("prod_1")
    unchecked = {row["ingredient"]: row for row in plan["not_checked"]}
    assert unchecked["potassium sorbate"]["reason_code"] == remediation.REASON_AMOUNT_MISSING
    assert "amount" in unchecked["potassium sorbate"]["reason_text"]
    assert "sodium benzoate" not in unchecked  # it was compared


def test_a_food_is_called_a_food_not_a_pass(monkeypatch):
    """`ginger` normalizes, so it looks checked. No additive annex sets a limit
    for it, and letting it disappear says the opposite of what is true."""
    _wire(
        monkeypatch,
        product=PRODUCT
        | {
            "ingredients": PRODUCT["ingredients"]
            + [{"name": "ginger", "normalized": "ginger", "amount": 5000.0,
                "unit": "mg_per_kg", "unnormalized": False}]
        },
        requirements=dict(
            [_requirement("req_de", market_id="market_de", clause_id="clause_eu", limit=150.0)]
        ),
    )
    plan = remediation.build_remediation("prod_1")
    ginger = next(row for row in plan["not_checked"] if row["ingredient"] == "ginger")
    assert ginger["reason_code"] == remediation.REASON_FOOD_NOT_ADDITIVE
    assert "food" in ginger["reason_text"].lower()


def test_an_unrecognised_name_says_so(monkeypatch):
    _wire(
        monkeypatch,
        product=PRODUCT
        | {
            "ingredients": PRODUCT["ingredients"]
            + [{"name": "zzqqx compound", "normalized": None, "amount": 10.0,
                "unit": "mg_per_kg", "unnormalized": True}]
        },
        requirements=dict(
            [_requirement("req_de", market_id="market_de", clause_id="clause_eu", limit=150.0)]
        ),
    )
    plan = remediation.build_remediation("prod_1")
    row = next(r for r in plan["not_checked"] if r["ingredient"] == "zzqqx compound")
    assert row["reason_code"] == remediation.REASON_NAME_NOT_RECOGNISED
    assert row["reason_text"]


# --- nothing to fix, and nothing there -------------------------------------


def test_a_product_that_breaks_nothing_gets_an_empty_plan(monkeypatch):
    """"Nothing to fix" is an answer, so it is a 200 with no targets — not a
    404 and not an invented one."""
    _wire(
        monkeypatch,
        product=PRODUCT,
        requirements=dict(
            [
                _requirement(
                    "req_de", market_id="market_de", clause_id="clause_eu",
                    limit=150.0, product_value=100.0, evaluation="pass",
                ),
                _requirement(
                    "req_id", market_id="market_id", clause_id="clause_bpom",
                    limit=400.0, product_value=100.0, evaluation="pass",
                ),
            ]
        ),
    )
    plan = remediation.build_remediation("prod_1")
    assert plan["targets"] == []
    assert plan["product_name"] == "Herbal Drink Powder"


def test_a_missing_product_is_none(monkeypatch):
    _wire(monkeypatch, product=PRODUCT, requirements={})
    assert remediation.build_remediation("prod_missing") is None


# --- the endpoint ----------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    _wire(
        monkeypatch,
        product=PRODUCT,
        requirements=dict(
            [
                _requirement("req_de", market_id="market_de", clause_id="clause_eu", limit=150.0),
                _requirement(
                    "req_id", market_id="market_id", clause_id="clause_bpom",
                    limit=400.0, evaluation="pass",
                ),
            ]
        ),
    )
    return TestClient(app)


def test_endpoint_returns_the_plan(client):
    response = client.get("/products/prod_1/remediation")
    assert response.status_code == 200
    body = response.json()
    assert body["targets"][0]["target_value"] == 150.0
    assert body["trace_id"]


def test_endpoint_404s_for_a_product_that_does_not_exist(client):
    response = client.get("/products/prod_missing/remediation")
    assert response.status_code == 404
    assert response.json()["detail"] == "product not found"


def test_the_plan_writes_nothing(monkeypatch):
    """The safety property, asserted rather than assumed: a stand-in Firestore
    with no write methods at all serves the whole request."""
    _wire(
        monkeypatch,
        product=PRODUCT,
        requirements=dict(
            [_requirement("req_de", market_id="market_de", clause_id="clause_eu", limit=150.0)]
        ),
    )
    published: list = []
    from app.messaging import publisher

    monkeypatch.setattr(
        publisher, "publish", lambda *a, **k: published.append(a), raising=False
    )
    assert remediation.build_remediation("prod_1") is not None
    assert published == []
