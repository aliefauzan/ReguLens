"""Rows that state no number, and whether the system can still read them.

Every string quoted here is verbatim from the bundled corpus — EU Annex II Part
E food category 14.1.3, which is the table the acesulfame K card came from.
"""

from __future__ import annotations

from app.core.clause_kind import (
    BASIS_NOTE,
    NO_MAXIMUM,
    PROHIBITION,
    classify,
    is_basis_note,
    kind_of,
)


class TestFootnotesAreNotRequirements:
    def test_a_marked_footnote_is_a_basis_note(self):
        kind, matched = classify(
            "(49):  The maximum usable levels are derived from the maximum usable "
            "levels for its constituent parts, aspartame (E 951) and acesulfame-K (E 950)"
        )
        assert kind == BASIS_NOTE
        assert matched == "(49):"

    def test_the_lettered_marker_is_a_footnote_too(self):
        kind, _ = classify(
            "(11): Limits are expressed as (a) acesulfame K equivalent or (b) aspartame equivalent"
        )
        assert kind == BASIS_NOTE

    def test_a_basis_sentence_without_its_marker_is_still_one(self):
        """Extraction sometimes emits the sentence and drops the marker."""
        kind, matched = classify("Maximum usable levels are expressed in free acid")
        assert kind == BASIS_NOTE
        assert matched == "expressed in free"

    def test_a_limit_row_is_not_a_footnote(self):
        assert classify("| E 950 | Acesulfame K | 350 | | only energy-reduced |") is None


class TestTheDecidableOnes:
    def test_quantum_satis_is_a_stated_absence_of_a_maximum(self):
        kind, matched = classify("| E 300 | Ascorbic acid | quantum satis |  |  |")
        assert (kind, matched) == (NO_MAXIMUM, "quantum satis")

    def test_the_indonesian_wording_reads_the_same(self):
        kind, _ = classify("Batas maksimum: secukupnya")
        assert kind == NO_MAXIMUM

    def test_may_not_be_used_is_a_limit_of_zero(self):
        kind, matched = classify(
            "| Group I | Additives |  |  | only vegetable nectars, E 420, E421, E 953, "
            "E965, E 966, E 967 and E 968 may not be used |"
        )
        assert (kind, matched) == (PROHIBITION, "may not be used")

    def test_a_row_stating_both_is_read_as_the_prohibition(self):
        """Annex II group rows carry a permission and a carve-out in one line.
        The half that forbids is the half that binds."""
        kind, _ = classify(
            "| Group II | Colours at quantum satis | quantum satis | | "
            "E 968 may not be used except where specifically provided |"
        )
        assert kind == PROHIBITION


class TestWhatItRefusesToSay:
    def test_an_unrecognised_row_stays_unrecognised(self):
        assert classify("The competent authority shall be notified before placing on the market") is None

    def test_empty_text_is_not_a_kind(self):
        assert classify(None) is None
        assert classify("") is None

    def test_a_clause_that_has_a_number_is_left_alone(self):
        """`kind_of` is only asked about rows the evaluator could not compare."""
        assert kind_of({"clause_type": "numeric_limit", "text": "quantum satis"}) is None

    def test_is_basis_note_reads_the_clause_not_a_stored_flag(self):
        footnote = (
            "(50):  The levels for both E 951 and E 950 are not to be exceeded "
            "by use of the salt of aspartame-acesulfame"
        )
        assert is_basis_note({"clause_type": "other", "text": footnote})
        assert not is_basis_note({"clause_type": "other", "text": "quantum satis"})
