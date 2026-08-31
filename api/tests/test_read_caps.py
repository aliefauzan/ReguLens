"""The reads that decide a verdict, and what they do when there is more to see.

Each of these used to carry a bare `.limit(N)` with no ordering and no count.
The failure is silent by construction: the rows that come back are real, the
arithmetic over them is right, and the screen shows a verdict indistinguishable
from one computed against the whole rulebook.
"""

from __future__ import annotations

import pytest

from app.core import alerts, impact
from app.core.paging import SCAN_CAP, overflows, reset_overflows


class _Snapshot:
    def __init__(self, doc_id: str, data: dict) -> None:
        self.id = doc_id
        self._data = data

    def to_dict(self) -> dict:
        return self._data


class _Query:
    def __init__(self, rows: list[_Snapshot]) -> None:
        self._rows = rows

    def where(self, filter=None):  # noqa: A002 - mirrors the Firestore signature
        field, op, value = filter.field_path, filter.op_string, filter.value
        kept = [
            row for row in self._rows
            if (op == "==" and (row.to_dict() or {}).get(field) == value)
            or (op == "in" and (row.to_dict() or {}).get(field) in value)
        ]
        return _Query(kept)

    def limit(self, n: int):
        return _Query(self._rows[:n])

    def stream(self):
        return iter(self._rows)


class _DB:
    def __init__(self, collections: dict[str, list[_Snapshot]]) -> None:
        self._collections = collections

    def collection(self, name: str):
        return _Query(self._collections.get(name, []))


@pytest.fixture(autouse=True)
def _clean():
    reset_overflows()
    yield
    reset_overflows()


def _clauses(count: int) -> list[_Snapshot]:
    return [
        _Snapshot(f"clause_{i:06d}", {"status": "active", "substance_normalized": "x"})
        for i in range(count)
    ]


class TestTheRulebook:
    """`clauses_active` is the whole input to every verdict the product makes."""

    def test_a_rulebook_larger_than_the_old_cap_is_read_whole(self, monkeypatch):
        """The bundled starter library alone is around 406 rule rows. Under the
        old `.limit(200)` more than half of it never reached the evaluator."""
        db = _DB({"clauses": _clauses(406)})
        monkeypatch.setattr(impact, "get_db", lambda: db)
        assert len(impact.clauses_active()) == 406
        assert overflows() == []

    def test_a_rulebook_past_the_cap_says_so(self, monkeypatch):
        db = _DB({"clauses": _clauses(SCAN_CAP + 10)})
        monkeypatch.setattr(impact, "get_db", lambda: db)
        impact.clauses_active()
        assert [o["what"] for o in overflows()] == ["clauses"]

    def test_requirements_past_the_cap_say_so(self, monkeypatch):
        rows = [
            _Snapshot(f"req_{i:06d}", {"product_id": "prod_1", "evaluation": "pass"})
            for i in range(SCAN_CAP + 1)
        ]
        db = _DB({"requirements": rows})
        monkeypatch.setattr(impact, "get_db", lambda: db)
        impact._requirements_for("prod_1")
        assert [o["what"] for o in overflows()] == ["requirements"]


class TestTheAlertList:
    """The sort that makes these "the latest alerts" runs after the read."""

    def test_the_newest_alert_survives_a_long_event_log(self, monkeypatch):
        # 400 acknowledged events written before the one that matters. The old
        # `.limit(50)` took an arbitrary fifty of these and sorted those.
        noise = [
            _Snapshot(
                f"evt_{i:06d}",
                {
                    "entity_id": "prod_1",
                    "event_type": "product_status_changed",
                    "before": {"market": "m", "status": "compliant"},
                    "after": {"market": "m", "status": "non_compliant"},
                    "acknowledged": True,
                    "occurred_at": i,
                },
            )
            for i in range(400)
        ]
        newest = _Snapshot(
            "evt_zzzzzz",
            {
                "entity_id": "prod_1",
                "event_type": "product_status_changed",
                "before": {"market": "m", "status": "compliant"},
                "after": {"market": "m", "status": "non_compliant"},
                "occurred_at": 9999,
            },
        )
        db = _DB({"graph_events": noise + [newest]})
        monkeypatch.setattr(alerts, "get_db", lambda: db)
        monkeypatch.setattr(alerts, "_document", lambda _id: None)
        monkeypatch.setattr(alerts, "_clause", lambda _id: None)

        class _Product:
            id = "prod_1"

            def model_dump(self, mode=None):
                return {"id": "prod_1", "name": "Herbal Drink Powder"}

        from app.core import markets as markets_core
        from app.core import products as products_core

        monkeypatch.setattr(products_core, "list_products", lambda: [_Product()])
        monkeypatch.setattr(
            markets_core,
            "list_markets",
            lambda: [{"id": "m", "label": "European Union — Germany", "country": "Germany"}],
        )

        result = alerts.list_alerts()
        assert [a["id"] for a in result] == ["evt_zzzzzz"]
