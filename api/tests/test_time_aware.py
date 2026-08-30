"""A rule that has not entered into force yet is not a rule you are breaking.

Before this, `effective_date` was extracted, stored, and used only to order
supersessions. The impact engine never read it, so a limit adopted now and
binding in 2027 marked a product `non_compliant` today — and, worse in the other
direction, a limit binding in 60 days was invisible for 60 days, which is exactly
the window in which a company could still have reformulated.

These tests pin both halves: what binds today, and what changes on a date.
"""

from datetime import date, timedelta

import pytest

from app.core import impact

TODAY = date(2026, 8, 30)
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()
NEXT_YEAR = (TODAY + timedelta(days=365)).isoformat()
IN_SIXTY_DAYS = (TODAY + timedelta(days=60)).isoformat()

MARKET = {"id": "market_de", "label": "European Union — Germany"}


def requirement(**overrides) -> dict:
    base = {
        "market_id": "market_de",
        "evaluation": "pass",
        "effective_date": None,
        "clause_id": "clause_now",
        "document_id": "doc_now",
    }
    return base | overrides


@pytest.fixture
def graph(monkeypatch):
    """Install a product's requirements without a database."""

    def install(requirements: list[dict], markets: list[dict] | None = None):
        monkeypatch.setattr(impact, "_requirements_for", lambda _pid: requirements)
        monkeypatch.setattr(impact, "_target_markets", lambda _pid: markets or [MARKET])

    return install


# ---------------------------------------------------------------------------
# _in_force — the whole feature rests on this one predicate


def test_absent_date_binds_now():
    """Most stored clauses carry no date. Treating that as "not yet" would hide
    every limit the system already knows about."""
    assert impact._in_force(None, TODAY) is True
    assert impact._in_force("", TODAY) is True


def test_past_and_present_dates_bind_now():
    assert impact._in_force(YESTERDAY, TODAY) is True
    assert impact._in_force(TODAY.isoformat(), TODAY) is True


def test_future_date_does_not_bind_yet():
    assert impact._in_force(NEXT_YEAR, TODAY) is False


def test_unreadable_date_fails_open():
    """Failing closed would drop a real limit from a verdict because a string was
    malformed. That is the failure this system is least allowed to have."""
    assert impact._in_force("not-a-date", TODAY) is True
    assert impact._in_force("2026-13-45", TODAY) is True


def test_timestamp_shaped_date_is_read_by_its_date_part():
    assert impact._in_force("2026-01-01T00:00:00Z", TODAY) is True


# ---------------------------------------------------------------------------
# rollup_status — what is true today


def test_a_future_rule_does_not_make_a_product_illegal_today(graph):
    """The headline defect. Over the limit, but the limit starts next year."""
    graph([requirement(evaluation="fail", effective_date=NEXT_YEAR)])
    assert impact.rollup_status("prod_1", TODAY) == {"market_de": "compliant"}


def test_a_rule_already_in_force_still_fails_the_product(graph):
    """Regression guard: the behaviour that was already right."""
    graph([requirement(evaluation="fail", effective_date=YESTERDAY)])
    assert impact.rollup_status("prod_1", TODAY) == {"market_de": "non_compliant"}


def test_a_rule_with_no_date_still_fails_the_product(graph):
    """Every clause stored before this change looks like this one."""
    graph([requirement(evaluation="fail")])
    assert impact.rollup_status("prod_1", TODAY) == {"market_de": "non_compliant"}


def test_an_unreadable_date_still_fails_the_product(graph):
    graph([requirement(evaluation="fail", effective_date="not-a-date")])
    assert impact.rollup_status("prod_1", TODAY) == {"market_de": "non_compliant"}


def test_no_requirements_at_all_is_unknown_not_compliant(graph):
    """"We have read no regulation for this market" and "nothing you break" are
    different sentences and must not share a status."""
    graph([])
    assert impact.rollup_status("prod_1", TODAY) == {"market_de": "unknown"}


def test_a_failing_rule_in_force_outranks_a_passing_one(graph):
    graph([
        requirement(evaluation="pass"),
        requirement(evaluation="fail", effective_date=YESTERDAY),
    ])
    assert impact.rollup_status("prod_1", TODAY) == {"market_de": "non_compliant"}


# ---------------------------------------------------------------------------
# upcoming_changes — what changes, and when


def test_the_date_a_passing_product_starts_failing_is_reported(graph):
    graph([
        requirement(evaluation="pass"),
        requirement(
            evaluation="fail",
            effective_date=IN_SIXTY_DAYS,
            clause_id="clause_2027",
            document_id="doc_2027",
        ),
    ])
    assert impact.upcoming_changes("prod_1", TODAY) == {
        "market_de": {
            "effective_date": IN_SIXTY_DAYS,
            "status": "non_compliant",
            # Named, because an alert that cannot say which rule moved the
            # verdict looks exactly like one whose rule was deleted.
            "clause_id": "clause_2027",
            "document_id": "doc_2027",
        }
    }


def test_a_future_rule_the_product_already_satisfies_is_not_a_deadline(graph):
    """Presenting every future rule as a deadline trains people to ignore the
    ones that are."""
    graph([
        requirement(evaluation="pass"),
        requirement(evaluation="pass", effective_date=IN_SIXTY_DAYS),
    ])
    assert impact.upcoming_changes("prod_1", TODAY) == {}


def test_the_earliest_changing_date_wins(graph):
    graph([
        requirement(evaluation="pass"),
        requirement(
            evaluation="needs_review",
            effective_date=IN_SIXTY_DAYS,
            clause_id="clause_sixty",
            document_id="doc_sixty",
        ),
        requirement(evaluation="fail", effective_date=NEXT_YEAR),
    ])
    assert impact.upcoming_changes("prod_1", TODAY) == {
        "market_de": {
            "effective_date": IN_SIXTY_DAYS,
            "status": "attention_required",
            "clause_id": "clause_sixty",
            "document_id": "doc_sixty",
        }
    }


def test_a_rule_already_in_force_is_not_upcoming(graph):
    graph([requirement(evaluation="fail", effective_date=YESTERDAY)])
    assert impact.upcoming_changes("prod_1", TODAY) == {}


def test_today_and_the_deadline_are_reported_together(graph):
    """The pair is the point: neither word alone describes this product."""
    graph([
        requirement(evaluation="pass"),
        requirement(evaluation="fail", effective_date=IN_SIXTY_DAYS),
    ])
    assert impact.rollup_status("prod_1", TODAY) == {"market_de": "compliant"}
    assert impact.upcoming_changes("prod_1", TODAY)["market_de"]["status"] == "non_compliant"


def test_the_worst_rule_starting_that_day_is_the_one_named(graph):
    """Two rules start together; the alert must point at the one that decides
    the verdict, not whichever was written first."""
    graph([
        requirement(evaluation="pass"),
        requirement(
            evaluation="needs_review",
            effective_date=IN_SIXTY_DAYS,
            clause_id="clause_soft",
            document_id="doc_soft",
        ),
        requirement(
            evaluation="fail",
            effective_date=IN_SIXTY_DAYS,
            clause_id="clause_hard",
            document_id="doc_hard",
        ),
    ])
    entry = impact.upcoming_changes("prod_1", TODAY)["market_de"]
    assert entry["status"] == "non_compliant"
    assert entry["clause_id"] == "clause_hard"
