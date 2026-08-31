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
