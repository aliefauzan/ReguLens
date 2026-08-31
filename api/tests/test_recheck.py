"""The review queue answering itself.

Thirty-six rows of one BPOM additive table sat in the queue asking a person to
confirm that a regulation does not contradict itself. The guardrail can now see
that 14.1.4.2 and 04.1.2.8 are different foods, so those questions have
deterministic answers — but only those. What must never happen is a recheck
that quietly clears a clause parked because nobody could read it.
"""

from __future__ import annotations

import pytest

from app.core.reconciliation import (
    AUTO_RECHECKABLE_REASONS,
    _reason_counts,
    recheck_review_queue,
)


class _Snapshot:
    def __init__(self, doc_id: str, data: dict) -> None:
        self.id = doc_id
        self._data = data

    def to_dict(self) -> dict:
        return dict(self._data)


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def where(self, filter=None):  # noqa: A002 - mirrors the Firestore signature
        kept = [r for r in self._rows if r.to_dict().get(filter.field_path) == filter.value]
        return _Query(kept)

    def limit(self, n: int):
        return _Query(self._rows[:n])

    def stream(self):
        return iter(self._rows)


class _DB:
    def __init__(self, rows):
        self._rows = rows

    def collection(self, name: str):
        assert name == "clauses"
        return _Query(self._rows)


@pytest.fixture
def queue(monkeypatch):
    """A queue holding both kinds of entry: questions code can now settle, and
    questions only a person can."""
    rows = [
        _Snapshot("c1", {"status": "needs_review", "review_reason": "judge_ambiguous"}),
        _Snapshot("c2", {"status": "needs_review", "review_reason": "judge_ambiguous"}),
        _Snapshot("c3", {"status": "needs_review", "review_reason": "judge_ambiguous"}),
        _Snapshot("c4", {"status": "needs_review", "review_reason": "low_confidence_or_flagged"}),
        _Snapshot("c5", {"status": "needs_review", "review_reason": None}),
    ]
    from app.core import reconciliation

    monkeypatch.setattr(reconciliation, "get_db", lambda: _DB(rows))
    return reconciliation


def test_only_judge_ambiguous_is_ever_reopened():
    """The policy itself, pinned. Adding low confidence here would mean the app
    clearing a number it admits it could not read."""
    assert set(AUTO_RECHECKABLE_REASONS) == {"judge_ambiguous"}


def test_a_clause_a_person_must_answer_is_never_touched(queue, monkeypatch):
    seen: list[str] = []

    def fake_recheck(clause_id: str) -> dict:
        seen.append(clause_id)
        return {"status": "active"}

    monkeypatch.setattr(queue, "recheck_clause", fake_recheck)
    summary = recheck_review_queue()

    assert seen == ["c1", "c2", "c3"]
    assert summary["eligible"] == 3
    assert summary["examined"] == 5


def test_resolved_and_still_waiting_add_up(queue, monkeypatch):
    outcomes = {"c1": "active", "c2": "superseded_by_existing", "c3": "ambiguous_needs_review"}
    monkeypatch.setattr(
        queue, "recheck_clause", lambda cid: {"status": outcomes[cid]}
    )
    summary = recheck_review_queue()

    assert summary["resolved"] == 2
    # c3 came back ambiguous and the two nobody can settle automatically.
    assert summary["still_waiting"] == 3
    assert summary["outcomes"]["ambiguous_needs_review"] == 1


def test_a_clause_that_is_still_ambiguous_goes_back_in_the_queue(queue, monkeypatch):
    """Landing back in the queue is a real outcome, not a failure — the recheck
    must not count it as settled."""
    monkeypatch.setattr(
        queue, "recheck_clause", lambda cid: {"status": "ambiguous_needs_review"}
    )
    summary = recheck_review_queue()
    assert summary["resolved"] == 0
    assert summary["still_waiting"] == 5


def test_what_it_could_not_settle_is_named_not_just_counted(queue, monkeypatch):
    monkeypatch.setattr(queue, "recheck_clause", lambda cid: {"status": "active"})
    summary = recheck_review_queue()
    assert summary["needs_a_person"] == {"low_confidence_or_flagged": 1, "unstated": 1}


def test_reason_counts_never_drops_a_blank_reason():
    counted = _reason_counts([{"review_reason": None}, {"review_reason": "low_authority"}])
    assert counted == {"unstated": 1, "low_authority": 1}
