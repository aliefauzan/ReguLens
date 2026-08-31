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


# ---------------------------------------------------------------------------
# The other way a queue empties itself: a name the dictionary has since learned


def test_the_conditional_reason_is_exactly_one_and_is_not_unconditional():
    """Pinned separately from `AUTO_RECHECKABLE_REASONS` on purpose. The two
    sets mean different things — one reason is always settleable by code, the
    other only when a re-run of the strict matcher says so — and collapsing
    them would turn "we learned this name" into "we cleared this name"."""
    from app.core.reconciliation import CONDITIONAL_RECHECK_REASON

    assert CONDITIONAL_RECHECK_REASON == "substance_not_recognized"
    assert CONDITIONAL_RECHECK_REASON not in AUTO_RECHECKABLE_REASONS


def test_a_name_the_dictionary_now_knows_is_reopened():
    """The live case: EU 2023/2108 was read before the curing-salt entries
    existed, so `Nitrites` parked as unrecognised. The dictionary knows it now,
    and the same strict matcher — not a relaxed one — says so."""
    from app.core.reconciliation import _renormalized

    correction = _renormalized(
        {
            "substance": "Nitrites",
            "confidence": 1.0,
            "review_reasons": ["substance_not_recognized"],
        }
    )
    assert correction is not None
    assert correction["substance_normalized"] == "nitrites"
    assert correction["unnormalized_substance"] is False


def test_the_authority_flag_is_cleared_with_the_same_write():
    """`reconcile_clause` parks anything carrying `needs_review` before it looks
    at anything else. A correction that left the flag standing would reopen the
    clause and park it again one line later, for the reason it just cleared."""
    from app.core.reconciliation import _renormalized

    correction = _renormalized(
        {
            "substance": "Nitrates",
            "confidence": 1.0,
            "review_reasons": ["substance_not_recognized"],
        }
    )
    assert correction["needs_review"] is False
    assert correction["review_reasons"] == []


def test_a_name_the_dictionary_still_refuses_stays_with_a_person():
    """The gate. Without it this reason would be a way of clearing the queue by
    asking the same question twice."""
    from app.core.reconciliation import _renormalized

    assert (
        _renormalized(
            {"substance": "Narasin", "review_reasons": ["substance_not_recognized"]}
        )
        is None
    )


def test_settling_one_of_two_reasons_settles_nothing():
    """A clause whose unit is also unreadable is not released by its substance
    resolving — the number is still one nobody can compare."""
    from app.core.reconciliation import _renormalized

    assert (
        _renormalized(
            {
                "substance": "Nitrites",
                "confidence": 1.0,
                "review_reasons": ["substance_not_recognized", "unit_not_normalizable"],
            }
        )
        is None
    )


def test_a_reason_written_by_extraction_is_read_from_the_list():
    """Extraction writes `review_reasons`; reconciliation writes
    `review_reason`. Reading one field only is how a queue reports every
    extraction-parked clause as `unstated`."""
    from app.core.reconciliation import _park_reasons

    assert _park_reasons({"review_reasons": ["substance_not_recognized"]}) == {
        "substance_not_recognized"
    }
    assert _park_reasons({"review_reason": "judge_ambiguous"}) == {"judge_ambiguous"}
    assert _park_reasons(
        {"review_reasons": ["unit_not_normalizable"], "review_reason": "judge_ambiguous"}
    ) == {"unit_not_normalizable", "judge_ambiguous"}


def test_a_sweep_reopens_a_learned_name_and_leaves_an_unlearned_one(monkeypatch):
    """End to end over the queue: the summary and the work agree, and the row
    nobody can read is still named in `needs_a_person`."""
    rows = [
        _Snapshot("known", {
            "status": "needs_review",
            "substance": "Nitrites",
            "confidence": 1.0,
            "review_reasons": ["substance_not_recognized"],
        }),
        _Snapshot("unknown", {
            "status": "needs_review",
            "substance": "Narasin",
            "confidence": 1.0,
            "review_reasons": ["substance_not_recognized"],
        }),
    ]
    from app.core import reconciliation

    monkeypatch.setattr(reconciliation, "get_db", lambda: _DB(rows))
    seen: list[str] = []
    monkeypatch.setattr(
        reconciliation,
        "recheck_clause",
        lambda cid: (seen.append(cid), {"status": "active"})[1],
    )

    summary = recheck_review_queue()

    assert seen == ["known"]
    assert summary["eligible"] == 1
    assert summary["resolved"] == 1
    assert summary["needs_a_person"] == {"substance_not_recognized": 1}


def test_a_recheck_is_not_a_way_in_that_an_upload_would_refuse():
    """A purity criterion parked before `specification_not_food_limit` existed
    carries no such reason. Releasing it on its substance alone would put "Loss
    on drying — not more than 3 %" into the graph as a food limit, with no food
    category, comparable to every cured meat in the annex."""
    from app.core.reconciliation import _renormalized

    assert (
        _renormalized(
            {
                "substance": "potassium nitrite",
                "confidence": 1.0,
                "clause_type": "numeric_limit",
                "text": "Loss on drying Not more than 3 % (4 hours, over silica gel)",
                "review_reasons": ["substance_not_recognized"],
            }
        )
        is None
    )
