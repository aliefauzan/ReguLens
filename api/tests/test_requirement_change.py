"""A requirement row is what the product page quotes back to the reader, so
"nothing changed" has to mean nothing the reader can see changed.

This is the second bug of exactly this shape. The first showed `product_value`
against the clause's unit; this one skipped the write entirely when a corrected
ingredient did not flip the verdict, leaving the old amount on screen under the
new one's verdict. Both were invisible to a test that only checked pass/fail.
"""

from app.core.impact import REPORTED_FIELDS, requirement_changed

BASELINE = {
    "clause_id": "clause_1",
    "limit_value": 400.0,
    "unit": "mg_per_kg",
    "evaluation": "pass",
    "severity": "none",
    "reason": None,
    "product_value": 300.0,
    "product_unit": "mg_per_kg",
    "comparable_value": 300.0,
    "comparable_limit": 400.0,
    "comparable_unit": "mg_per_kg",
    "evaluated_at": "2026-08-01T00:00:00Z",
}


def test_identical_evaluation_writes_nothing():
    assert requirement_changed(BASELINE, dict(BASELINE)) is False


def test_timestamps_alone_are_not_a_change():
    """Otherwise every re-run would put a meaningless event in the audit trail."""
    later = dict(BASELINE) | {"evaluated_at": "2026-08-28T09:00:00Z"}
    assert requirement_changed(BASELINE, later) is False


def test_corrected_amount_is_a_change_even_when_the_verdict_holds():
    """The regression. 300 → 100 still passes under a 400 limit, and the row
    used to keep saying 300."""
    corrected = dict(BASELINE) | {"product_value": 100.0, "comparable_value": 100.0}
    assert requirement_changed(BASELINE, corrected) is True


def test_unit_change_is_a_change():
    """0.03% and 300 mg/kg are the same quantity; showing the wrong unit next
    to the number is how the earlier four-orders-of-magnitude bug read."""
    same_amount_other_unit = dict(BASELINE) | {"product_unit": "percent_w_w", "product_value": 0.03}
    assert requirement_changed(BASELINE, same_amount_other_unit) is True


def test_verdict_change_is_a_change():
    assert requirement_changed(BASELINE, dict(BASELINE) | {"evaluation": "fail"}) is True


def test_reason_change_is_a_change():
    """"We do not know how much" and "the unit does not convert" are different
    sentences on screen."""
    assert requirement_changed(BASELINE, dict(BASELINE) | {"reason": "unit_unconvertible"}) is True


def test_every_reported_field_is_watched():
    """Each field the page reads must be in the set — this is the check that
    would have caught both bugs."""
    for field in REPORTED_FIELDS:
        changed = dict(BASELINE) | {field: "something else entirely"}
        assert requirement_changed(BASELINE, changed) is True, f"{field} is not watched"


def test_a_corrected_effective_date_is_a_change():
    """The date decides whether the row counts toward today's verdict at all, so
    a clause re-read with a corrected date must rewrite the requirement — not
    leave last night's deadline on the page."""
    assert "effective_date" in REPORTED_FIELDS
    moved = dict(BASELINE) | {"effective_date": "2027-01-12"}
    assert requirement_changed(dict(BASELINE) | {"effective_date": None}, moved) is True
