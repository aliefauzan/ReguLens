"""Taking a rule back out of the graph.

A clause the reader judged wrong could be parked only while it sat in the
review queue. Once active there was no way out but deleting the document it
came from — which, for an annex, means deleting the eighty-seven rules that
were right along with the one that was not.
"""

from __future__ import annotations

import pytest

from app.core.reconciliation import DISMISSABLE_STATUSES, dismiss_clause


class _Ref:
    def __init__(self, store, path):
        self.store, self.path = store, path
        self.deleted = False

    def get(self, transaction=None):
        return _Snap(self.path, self.store.get(self.path))

    def delete(self):
        self.deleted = True
        self.store.pop(self.path, None)


class _Snap:
    def __init__(self, path, data):
        self.id = path.split("/")[-1]
        self._data = data
        self.reference = None

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data or {})


class _Collection:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def document(self, doc_id):
        return _Ref(self.db.store, f"{self.name}/{doc_id}")

    def where(self, filter=None):
        self.db.queries.append((self.name, filter.field_path, filter.value))
        return self

    def stream(self):
        return iter(self.db.rows.get(self.name, []))


class _Transaction:
    def __init__(self, db):
        self.db = db

    def set(self, ref, payload, merge=False):
        current = self.db.store.get(ref.path, {}) if merge else {}
        self.db.store[ref.path] = {**current, **payload}


class _DB:
    def __init__(self, store, rows=None):
        self.store, self.rows, self.queries = store, rows or {}, []

    def collection(self, name):
        return _Collection(self, name)

    def transaction(self):
        return _Transaction(self)


@pytest.fixture
def firestore_transactional(monkeypatch):
    """`@firestore.transactional` wraps the function; here it just calls it."""
    from app.core import reconciliation

    class _Shim:
        FieldFilter = staticmethod(
            lambda field_path=None, op_string=None, value=None: type(
                "F", (), {"field_path": field_path, "value": value}
            )()
        )

        @staticmethod
        def transactional(fn):
            return fn

    monkeypatch.setattr(reconciliation, "firestore", _Shim)
    return reconciliation


def test_an_active_clause_can_be_withdrawn(firestore_transactional, monkeypatch):
    """The whole point. A laboratory drying method stored as a 2 500 mg/kg
    ceiling was binding a cured sausage and could not be taken out."""
    store = {"clauses/c1": {"status": "active", "confidence": 1.0}}
    db = _DB(store)
    monkeypatch.setattr(firestore_transactional, "get_db", lambda: db)
    monkeypatch.setattr(
        firestore_transactional, "_withdraw_derived_state", lambda cid: {"derived_removed": 0}
    )

    result = dismiss_clause("c1")

    assert result["status"] == "dismissed"
    assert result["was"] == "active"
    assert store["clauses/c1"]["status"] == "dismissed"


def test_the_event_records_what_it_was_before(firestore_transactional, monkeypatch):
    """`before` must be the status it actually held. An event that says every
    withdrawal came from the review queue makes the trail a fiction."""
    store = {"clauses/c1": {"status": "active", "confidence": 1.0}}
    db = _DB(store)
    monkeypatch.setattr(firestore_transactional, "get_db", lambda: db)
    monkeypatch.setattr(
        firestore_transactional, "_withdraw_derived_state", lambda cid: {}
    )

    dismiss_clause("c1")
    events = [v for k, v in store.items() if k.startswith("graph_events/")]
    assert len(events) == 1
    assert events[0]["before"] == {"status": "active"}
    assert events[0]["after"] == {"status": "dismissed"}


def test_a_dismissed_clause_is_not_dismissed_twice(firestore_transactional, monkeypatch):
    """Terminal and inert. Idempotent for the same reason every handler is."""
    store = {"clauses/c1": {"status": "dismissed"}}
    monkeypatch.setattr(firestore_transactional, "get_db", lambda: _DB(store))

    assert dismiss_clause("c1")["status"] == "unchanged"


def test_a_superseded_clause_is_left_alone(firestore_transactional, monkeypatch):
    """Superseded is a decision reconciliation made, not a rule anybody is
    acting on. Withdrawing it would rewrite history to no effect."""
    store = {"clauses/c1": {"status": "superseded"}}
    monkeypatch.setattr(firestore_transactional, "get_db", lambda: _DB(store))

    assert dismiss_clause("c1")["status"] == "unchanged"
    assert "superseded" not in DISMISSABLE_STATUSES


def test_a_missing_clause_is_a_404_not_a_silent_success(
    firestore_transactional, monkeypatch
):
    monkeypatch.setattr(firestore_transactional, "get_db", lambda: _DB({}))
    assert dismiss_clause("nope") is None


def test_withdrawing_takes_its_requirements_with_it(firestore_transactional, monkeypatch):
    """A withdrawal that leaves a stale verdict on screen is worse than no
    withdrawal — the same duty a document delete carries."""
    from app.core import reconciliation

    rows = {
        "requirements": [_Snap("requirements/r1", {"product_id": "prod_1"})],
        "conflicts": [],
    }
    db = _DB({}, rows)
    for snap in rows["requirements"]:
        snap.reference = _Ref(db.store, "requirements/r1")
    db.store["requirements/r1"] = {"product_id": "prod_1"}
    monkeypatch.setattr(reconciliation, "get_db", lambda: db)

    reevaluated: list[str] = []
    import app.core.impact as impact

    monkeypatch.setattr(impact, "run_impact_for_product", lambda pid: reevaluated.append(pid))

    summary = reconciliation._withdraw_derived_state("c1")

    assert reevaluated == ["prod_1"]
    assert summary["products_reevaluated"] == 1
    assert "requirements/r1" not in db.store
