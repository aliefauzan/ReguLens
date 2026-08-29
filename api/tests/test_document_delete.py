"""Deleting a document must take its derived state with it.

Found by running the verification drills against the deployed stack: six latency
measurements left six near-identical copies of the same EU regulation in the
demo workspace, the next `verify_e2e.sh` run counted nine open conflicts and six
"EU benzoate 150 mg/kg" clauses, and there was no way to remove any of it —
a product could be deleted, the document you uploaded by mistake could not.

These tests pin the cascade. They exercise the reference-collecting logic
against a stand-in Firestore, because what went wrong in practice was never the
happy path — it was a conflict between two clauses of the same document being
collected twice and Firestore rejecting the batch.
"""

from __future__ import annotations

import pytest


class _Ref:
    def __init__(self, path: str) -> None:
        self.path = path

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return f"<ref {self.path}>"


class _Snapshot:
    def __init__(self, doc_id: str, data: dict, path: str) -> None:
        self.id = doc_id
        self._data = data
        self.reference = _Ref(path)

    def to_dict(self) -> dict:
        return self._data


class _Query:
    def __init__(self, rows: list[_Snapshot]) -> None:
        self._rows = rows

    def where(self, filter=None):  # noqa: A002 - mirrors the Firestore signature
        field = filter.field_path
        op = filter.op_string
        value = filter.value
        kept = []
        for row in self._rows:
            actual = row.to_dict().get(field)
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
    def __init__(self, name: str, rows: list[_Snapshot]) -> None:
        self.name = name
        self._rows = rows

    def where(self, filter=None):  # noqa: A002
        return _Query(self._rows).where(filter=filter)

    def limit(self, n: int):
        return _Query(self._rows).limit(n)

    def stream(self):
        return iter(self._rows)

    def document(self, doc_id: str) -> _Ref:
        return _Ref(f"{self.name}/{doc_id}")


class _DB:
    def __init__(self, collections: dict[str, list[_Snapshot]]) -> None:
        self._collections = collections

    def collection(self, name: str) -> _Collection:
        return _Collection(name, self._collections.get(name, []))


def _snap(collection: str, doc_id: str, **data) -> _Snapshot:
    return _Snapshot(doc_id, data, f"{collection}/{doc_id}")


@pytest.fixture
def wired(monkeypatch):
    """A document with two clauses, a requirement, and a conflict between its
    own two clauses — the shape that produced a duplicate reference."""
    from app.core import documents as documents_core

    db = _DB(
        {
            "clauses": [
                _snap("clauses", "clause_a", document_id="doc_1"),
                _snap("clauses", "clause_b", document_id="doc_1"),
                _snap("clauses", "clause_other", document_id="doc_2"),
            ],
            "requirements": [
                _snap("requirements", "req_1", clause_id="clause_a", product_id="prod_1"),
                _snap("requirements", "req_2", clause_id="clause_b", product_id="prod_1"),
                _snap("requirements", "req_3", clause_id="clause_other", product_id="prod_2"),
            ],
            "conflicts": [
                _snap("conflicts", "conf_1", clause_a="clause_a", clause_b="clause_b"),
            ],
        }
    )
    monkeypatch.setattr(documents_core, "get_db", lambda: db)

    captured: dict = {}

    def fake_delete_with_event(collection, doc_id, **kwargs):
        captured["collection"] = collection
        captured["doc_id"] = doc_id
        captured["also_delete"] = kwargs.get("also_delete") or []
        captured["event_type"] = kwargs.get("event_type")
        return "evt_1"

    monkeypatch.setattr(documents_core, "delete_with_event", fake_delete_with_event)

    reevaluated: list[str] = []
    import app.core.impact as impact

    monkeypatch.setattr(
        impact, "run_impact_for_product", lambda pid: reevaluated.append(pid)
    )

    class _Doc:
        id = "doc_1"

        def model_dump(self, mode="json"):
            return {"id": "doc_1"}

    monkeypatch.setattr(documents_core, "get_document", lambda did: _Doc() if did == "doc_1" else None)
    return documents_core, captured, reevaluated


def test_missing_document_is_a_404_not_a_delete(wired):
    documents_core, captured, _ = wired
    assert documents_core.delete_document("doc_missing") is None
    assert captured == {}, "nothing may be deleted for a document that does not exist"


def test_clauses_requirements_and_conflicts_all_go(wired):
    documents_core, captured, _ = wired
    summary = documents_core.delete_document("doc_1")

    paths = {ref.path for ref in captured["also_delete"]}
    assert "clauses/clause_a" in paths
    assert "clauses/clause_b" in paths
    assert "requirements/req_1" in paths
    assert "requirements/req_2" in paths
    assert "conflicts/conf_1" in paths
    assert "extraction_debug/doc_1" in paths
    assert summary["clauses"] == 2


def test_another_document_is_left_alone(wired):
    documents_core, captured, _ = wired
    documents_core.delete_document("doc_1")

    paths = {ref.path for ref in captured["also_delete"]}
    assert "clauses/clause_other" not in paths
    assert "requirements/req_3" not in paths


def test_a_conflict_between_two_of_its_own_clauses_is_collected_once(wired):
    """Found once per side. Firestore rejects a batch deleting one reference
    twice, so the whole delete would fail on exactly the documents this was
    written to clean up."""
    documents_core, captured, _ = wired
    documents_core.delete_document("doc_1")

    paths = [ref.path for ref in captured["also_delete"]]
    assert len(paths) == len(set(paths)), f"duplicate reference in batch: {paths}"


def test_affected_products_are_reevaluated_once_each(wired):
    """A market that read non_compliant only because of this document has to
    stop saying so. Once per product, not once per requirement."""
    documents_core, _, reevaluated = wired
    summary = documents_core.delete_document("doc_1")

    assert reevaluated == ["prod_1"]
    assert summary["products_reevaluated"] == 1


def test_the_deletion_is_recorded_as_an_event(wired):
    from app.models import EventType

    documents_core, captured, _ = wired
    documents_core.delete_document("doc_1")
    assert captured["event_type"] == EventType.DOCUMENT_DELETED
    assert captured["collection"] == "documents"
