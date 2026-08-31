"""A read that cannot see everything has to say so.

The bug this file exists for is silent: a bare `.limit(200)` on the clause
collection returned an arbitrary two hundred rules, the impact engine evaluated
a product against exactly those, and the screen showed a verdict that looked
identical to one computed against the whole rulebook.
"""

from __future__ import annotations

import pytest

from app.core.paging import (
    SCAN_CAP,
    overflows,
    read_capped,
    reset_overflows,
)


class _Snapshot:
    def __init__(self, doc_id: str, data: dict) -> None:
        self.id = doc_id
        self._data = data

    def to_dict(self) -> dict:
        return self._data


class _Query:
    """Only what `read_capped` is allowed to use: `limit` then `stream`."""

    def __init__(self, rows: list[_Snapshot]) -> None:
        self._rows = rows

    def limit(self, n: int) -> _Query:
        return _Query(self._rows[:n])

    def stream(self):
        return iter(self._rows)


def _rows(count: int) -> _Query:
    return _Query([_Snapshot(f"row_{i:05d}", {"n": i}) for i in range(count)])


@pytest.fixture(autouse=True)
def _clean():
    reset_overflows()
    yield
    reset_overflows()


class TestWhatFits:
    def test_everything_under_the_cap_comes_back_and_nothing_is_reported(self):
        rows = read_capped(_rows(10), what="clauses", cap=100)
        assert len(rows) == 10
        assert overflows() == []

    def test_the_id_travels_with_the_row(self):
        rows = read_capped(_rows(2), what="clauses", cap=100)
        assert [r["id"] for r in rows] == ["row_00000", "row_00001"]

    def test_a_collection_of_exactly_the_cap_is_not_an_overflow(self):
        """The off-by-one that would make every full page look truncated."""
        rows = read_capped(_rows(100), what="clauses", cap=100)
        assert len(rows) == 100
        assert overflows() == []


class TestWhatDoesNot:
    def test_an_overflow_is_reported_with_its_size_and_its_name(self):
        read_capped(_rows(150), what="clauses", cap=100)
        assert overflows() == [{"what": "clauses", "cap": 100, "seen": 101}]

    def test_the_caller_still_gets_the_rows_it_can_have(self):
        rows = read_capped(_rows(150), what="clauses", cap=100)
        assert len(rows) == 100

    def test_two_overflowing_reads_are_both_named(self):
        read_capped(_rows(150), what="clauses", cap=100)
        read_capped(_rows(150), what="requirements", cap=100)
        assert [o["what"] for o in overflows()] == ["clauses", "requirements"]

    def test_a_reset_clears_the_previous_request(self):
        read_capped(_rows(150), what="clauses", cap=100)
        reset_overflows()
        assert overflows() == []


class TestTheCapItself:
    def test_it_is_far_above_the_bundled_library(self):
        """The starter set alone is ~406 rule rows, and the whole bundled
        library ~593. A cap anywhere near those is the bug again with a bigger
        number."""
        assert SCAN_CAP >= 5000
