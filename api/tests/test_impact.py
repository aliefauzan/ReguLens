"""The impact engine's account of itself.

Arithmetic decides the verdict; this file is about what the verdict says it
rests on, which is what a reader acts on.
"""

from __future__ import annotations


class TestTheCauseNamed:
    """Which rule the alert quotes.

    `run_impact` knows the clause whose change started the run. That is not
    always the clause the verdict rests on: reconciling the nitrates row of
    Commission Regulation (EU) 2023/2108 set a cured sausage to
    `non_compliant` on its nitrites row, and the alert read "it sets nitrates
    at 150 mg/kg" above a verdict about 30 mg/kg of nitrites.
    """

    def test_the_deciding_rule_wins_over_the_triggering_one(self, monkeypatch):
        from app.core import impact

        monkeypatch.setattr(
            impact,
            "_requirements_for",
            lambda pid: [
                {"market_id": "market_de", "evaluation": "pass",
                 "clause_id": "clause_nitrates", "document_id": "doc_1"},
                {"market_id": "market_de", "evaluation": "fail",
                 "clause_id": "clause_nitrites", "document_id": "doc_1"},
            ],
        )
        cause = impact._cause_of("prod_1", "market_de", "clause_trigger", "doc_1")
        assert cause == {"clause_id": "clause_nitrites", "document_id": "doc_1"}

    def test_a_market_with_nothing_in_force_falls_back_to_the_trigger(self, monkeypatch):
        """Better a rule that is merely related than no cause at all — an alert
        with an empty cause says nothing about why anything moved."""
        from app.core import impact

        monkeypatch.setattr(impact, "_requirements_for", lambda pid: [])
        cause = impact._cause_of("prod_1", "market_de", "clause_trigger", "doc_9")
        assert cause == {"clause_id": "clause_trigger", "document_id": "doc_9"}

    def test_a_rule_not_yet_in_force_does_not_get_the_blame(self, monkeypatch):
        """The same rule `rollup_status` applies: a limit that starts next year
        did not cause today's verdict."""
        from app.core import impact

        monkeypatch.setattr(
            impact,
            "_requirements_for",
            lambda pid: [
                {"market_id": "market_de", "evaluation": "fail",
                 "effective_date": "2099-01-01",
                 "clause_id": "clause_future", "document_id": "doc_1"},
                {"market_id": "market_de", "evaluation": "needs_review",
                 "clause_id": "clause_now", "document_id": "doc_1"},
            ],
        )
        cause = impact._cause_of("prod_1", "market_de", "clause_trigger", "doc_1")
        assert cause["clause_id"] == "clause_now"

    def test_a_recipe_change_still_names_the_rule_it_broke(self, monkeypatch):
        """A verdict that moved because the recipe changed still rests on a
        rule. Recording no cause made the alert say "the rule behind this has
        since been removed" — nothing was removed; it was never written down."""
        from app.core import impact

        monkeypatch.setattr(
            impact,
            "_requirements_for",
            lambda pid: [
                {"market_id": "market_de", "evaluation": "fail",
                 "clause_id": "clause_nitrites", "document_id": "doc_1"},
            ],
        )
        assert impact._cause_of("prod_1", "market_de", None, None) == {
            "clause_id": "clause_nitrites",
            "document_id": "doc_1",
        }

    def test_a_market_with_no_rule_at_all_records_no_cause(self, monkeypatch):
        """The one case "we cannot find the rule behind this" is true for."""
        from app.core import impact

        monkeypatch.setattr(impact, "_requirements_for", lambda pid: [])
        assert impact._cause_of("prod_1", "market_de", None, None) == {}


class TestRetiredRequirements:
    """A requirement is a rule applied to a product. When the rule stops being
    the one in effect, the requirement has to go with it.

    Seen in production: a cured sausage reformulated to 20 mg/kg stayed
    `non_compliant` against `E 249-250 Nitrites 100`, superseded minutes
    earlier by its own replacement, recorded against the 120 mg/kg the recipe
    no longer contained. Materialization only revisits clauses that are still
    active, so nothing ever corrected the row and nothing removed it.
    """

    def _db(self, rows):
        class _Snap:
            def __init__(self, data, ref):
                self._data, self.reference = data, ref

            def to_dict(self):
                return dict(self._data)

        class _Ref:
            def __init__(self, sink, key):
                self.sink, self.key = sink, key

            def delete(self):
                self.sink.append(self.key)

        deleted: list[str] = []

        class _Q:
            def __init__(self, rows):
                self.rows = rows

            def where(self, filter=None):
                return self

            def limit(self, n):
                return self

            def stream(self):
                return iter(
                    [_Snap(r, _Ref(deleted, r["clause_id"])) for r in self.rows]
                )

        class _DB:
            def collection(self, name):
                return _Q(rows)

        return _DB(), deleted

    def test_a_requirement_whose_clause_was_superseded_is_removed(self, monkeypatch):
        from app.core import impact

        db, deleted = self._db(
            [{"clause_id": "clause_superseded"}, {"clause_id": "clause_active"}]
        )
        monkeypatch.setattr(impact, "get_db", lambda: db)

        removed = impact._retire_orphans("prod_1", {"clause_active"})

        assert removed == 1
        assert deleted == ["clause_superseded"]

    def test_a_requirement_whose_clause_still_stands_is_left_alone(self, monkeypatch):
        from app.core import impact

        db, deleted = self._db([{"clause_id": "clause_active"}])
        monkeypatch.setattr(impact, "get_db", lambda: db)

        assert impact._retire_orphans("prod_1", {"clause_active"}) == 0
        assert deleted == []

    def test_a_requirement_with_no_clause_is_an_orphan(self, monkeypatch):
        """Nothing can re-evaluate it, so nothing can ever correct it."""
        from app.core import impact

        db, deleted = self._db([{"clause_id": None}])
        monkeypatch.setattr(impact, "get_db", lambda: db)

        assert impact._retire_orphans("prod_1", {"clause_active"}) == 1


def test_the_strictest_failing_rule_is_the_one_named(monkeypatch):
    """Several rows can fail one product at once. The one that decides whether
    it can be sold is the lowest number — and it is the one the product page
    already shows, so the alert has to agree with it."""
    from app.core import impact

    monkeypatch.setattr(
        impact,
        "_requirements_for",
        lambda pid: [
            {"market_id": "market_de", "evaluation": "fail", "comparable_limit": 50.0,
             "clause_id": "clause_veal", "document_id": "doc_1"},
            {"market_id": "market_de", "evaluation": "fail", "comparable_limit": 30.0,
             "clause_id": "clause_traditional", "document_id": "doc_1"},
            {"market_id": "market_de", "evaluation": "fail", "comparable_limit": 105.0,
             "clause_id": "clause_bacon", "document_id": "doc_1"},
        ],
    )
    assert impact._cause_of("prod_1", "market_de", None, None)["clause_id"] == (
        "clause_traditional"
    )


def test_a_rule_with_no_number_is_not_the_strictest_anything(monkeypatch):
    """Sorting a limit nobody could read to the front would put the clause the
    guardrail gave up on ahead of the one it evaluated."""
    from app.core import impact

    monkeypatch.setattr(
        impact,
        "_requirements_for",
        lambda pid: [
            {"market_id": "market_de", "evaluation": "fail", "comparable_limit": None,
             "clause_id": "clause_unreadable", "document_id": "doc_1"},
            {"market_id": "market_de", "evaluation": "fail", "comparable_limit": 30.0,
             "clause_id": "clause_traditional", "document_id": "doc_1"},
        ],
    )
    assert impact._cause_of("prod_1", "market_de", None, None)["clause_id"] == (
        "clause_traditional"
    )
