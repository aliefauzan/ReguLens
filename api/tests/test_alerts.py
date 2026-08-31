"""Alerts, and whether they can say why.

The banner said "Herbal Drink Powder changed" and left out the one fact worth
reading: nobody asked for this. The regulation arrived on its own, overnight,
from an address the app watches. These tests pin the resolution of an event's
two bare ids into the facts that sentence needs — and pin the refusal to invent
them when the cause is gone.
"""

from app.core import alerts


def event(**overrides) -> dict:
    base = {
        "id": "evt_1",
        "entity_id": "prod_1",
        "event_type": "product_status_changed",
        "before": {"market": "market_de", "status": "compliant"},
        "after": {"market": "market_de", "status": "non_compliant"},
        "cause": {"clause_id": "clause_1", "document_id": "doc_1"},
    }
    return base | overrides


PRODUCTS = {"prod_1": {"id": "prod_1", "name": "Herbal Drink Powder"}}
MARKETS = {"market_de": {"id": "market_de", "label": "European Union — Germany", "country": "Germany"}}


def install(monkeypatch, *, document=None, clause=None):
    monkeypatch.setattr(alerts, "_document", lambda _id: document)
    monkeypatch.setattr(alerts, "_clause", lambda _id: clause)


def test_only_a_worsening_transition_is_an_alert():
    assert alerts.worsened(event())
    assert not alerts.worsened(
        event(before={"market": "market_de", "status": "non_compliant"},
              after={"market": "market_de", "status": "compliant"})
    )


def test_arriving_at_a_verdict_from_unknown_counts_as_worse():
    """A product that had no verdict and now fails is news, not a downgrade."""
    assert alerts.worsened(
        event(before={"market": "market_de", "status": "unknown"},
              after={"market": "market_de", "status": "attention_required"})
    )


def test_a_change_caused_by_a_watched_source_is_marked_unprompted(monkeypatch):
    """The headline fact, and the entire difference between a compliance checker
    and a regulatory monitor: nobody uploaded this."""
    install(
        monkeypatch,
        document={
            "origin": "watched_source",
            "source_name": "COMMISSION REGULATION (EU) 2026/1860",
            "jurisdiction": "EU",
        },
        clause={"substance_normalized": "sodium_benzoate", "limit_value": 150, "unit": "mg_per_kg",
                "text": "E 210-213 Benzoic acid - benzoates 150"},
    )
    context = alerts.explain(event(), products_by_id=PRODUCTS, markets_by_id=MARKETS)

    assert context["unprompted"] is True
    assert context["source_name"] == "COMMISSION REGULATION (EU) 2026/1860"
    assert context["product_name"] == "Herbal Drink Powder"
    assert context["market_country"] == "Germany"
    assert context["substance"] == "sodium_benzoate"
    assert context["limit_value"] == 150
    assert context["to_status"] == "non_compliant"


def test_a_change_caused_by_an_upload_is_not_marked_unprompted(monkeypatch):
    """Overclaiming here would put "nobody uploaded this" under a document the
    user uploaded thirty seconds earlier."""
    install(monkeypatch, document={"origin": "upload", "source_name": "My PDF"}, clause=None)
    context = alerts.explain(event(), products_by_id=PRODUCTS, markets_by_id=MARKETS)
    assert context["unprompted"] is False
    assert context["origin"] == "upload"


def test_a_library_load_is_not_unprompted_either(monkeypatch):
    install(monkeypatch, document={"origin": "library"}, clause=None)
    assert alerts.explain(event(), products_by_id=PRODUCTS, markets_by_id=MARKETS)["unprompted"] is False


def test_a_deleted_cause_is_admitted_not_invented(monkeypatch):
    """An alert that explains itself wrongly is worse than one that says it
    cannot. Deleting a document is allowed; its alerts outlive it."""
    install(monkeypatch, document=None, clause=None)
    context = alerts.explain(event(), products_by_id=PRODUCTS, markets_by_id=MARKETS)

    assert context["cause_available"] is False
    assert context["unprompted"] is False
    assert "source_name" not in context
    # The transition itself is still known and still worth showing.
    assert context["to_status"] == "non_compliant"
    assert context["product_name"] == "Herbal Drink Powder"


def test_an_event_with_no_cause_at_all_still_explains_the_transition(monkeypatch):
    """`run_impact_for_product` writes status changes with cause=None — a
    product edit, not a regulation. Those must not crash the banner."""
    install(monkeypatch)
    context = alerts.explain(event(cause=None), products_by_id=PRODUCTS, markets_by_id=MARKETS)
    assert context["cause_available"] is False
    assert context["from_status"] == "compliant"


# ---------------------------------------------------------------------------
# Autonomy counting
# ---------------------------------------------------------------------------


def test_only_unprompted_origins_count_as_found_on_our_own():
    """`library` and `demo` documents were put there by a button somebody
    pressed. Counting them as autonomous work would inflate the one number the
    product's whole claim rests on."""
    from app.core import alerts as alerts_core

    assert alerts_core.UNPROMPTED_ORIGINS == {"watched_source"}
    for origin in ("upload", "library", "demo"):
        assert origin not in alerts_core.UNPROMPTED_ORIGINS


# ---------------------------------------------------------------------------
# Scheduled alerts: the verdict that changes on a date nobody has reached yet


def scheduled(**overrides) -> dict:
    base = event(
        event_type="product_status_scheduled",
        before={"market": "market_de", "status": "compliant"},
        after={
            "market": "market_de",
            "status": "non_compliant",
            "effective_date": "2027-01-12",
        },
    )
    return base | overrides


def test_a_scheduled_worsening_is_an_alert():
    """A rule adopted now and binding later is the only warning a company can
    still act on."""
    assert alerts.worsened(scheduled())


def test_a_cleared_schedule_is_not_an_alert():
    """The date arrived, or the rule that set it was superseded. It belongs in
    the audit trail, not in the banner."""
    assert not alerts.worsened(
        scheduled(after={"market": "market_de", "status": None, "effective_date": None})
    )


def test_a_scheduled_alert_carries_the_date_and_says_it_is_scheduled(monkeypatch):
    """"From 12 January" and "soon" are different sentences, and the difference
    is whether anybody can plan."""
    install(monkeypatch, document={"origin": "watched_source"}, clause=None)
    context = alerts.explain(scheduled(), products_by_id=PRODUCTS, markets_by_id=MARKETS)
    assert context["scheduled"] is True
    assert context["effective_date"] == "2027-01-12"
    assert context["to_status"] == "non_compliant"


def test_a_status_change_today_is_not_marked_scheduled(monkeypatch):
    install(monkeypatch, document={"origin": "upload"}, clause=None)
    context = alerts.explain(event(), products_by_id=PRODUCTS, markets_by_id=MARKETS)
    assert context["scheduled"] is False
    assert context["effective_date"] is None


def test_both_event_types_are_queried_for_alerts():
    """A scheduled verdict that never reaches the query is a deadline nobody is
    told about."""
    assert "product_status_changed" in alerts.ALERTING_EVENTS
    assert "product_status_scheduled" in alerts.ALERTING_EVENTS


class TestCauseDocument:
    """Which regulation moved this verdict.

    `graph.changed` carried the clause and nothing else, so every event written
    from reconciliation recorded a null document — and every fact an alert
    reports about its cause hangs off the document. A verdict moved by a
    regulation the scheduler found reported `unprompted: false`.
    """

    def test_a_stated_document_is_used_as_it_stands(self, monkeypatch):
        from app.core import alerts

        monkeypatch.setattr(alerts, "_clause", lambda cid: {"document_id": "doc_other"})
        event = {"cause": {"clause_id": "clause_1", "document_id": "doc_stated"}}
        assert alerts.cause_document_id(event) == "doc_stated"

    def test_a_missing_document_is_followed_through_the_clause(self, monkeypatch):
        from app.core import alerts

        monkeypatch.setattr(alerts, "_clause", lambda cid: {"document_id": "doc_found"})
        event = {"cause": {"clause_id": "clause_1", "document_id": None}}
        assert alerts.cause_document_id(event) == "doc_found"

    def test_a_cause_that_no_longer_exists_says_nothing(self, monkeypatch):
        """A deleted clause goes back to saying nothing rather than borrowing
        another document's story."""
        from app.core import alerts

        monkeypatch.setattr(alerts, "_clause", lambda cid: None)
        assert alerts.cause_document_id({"cause": {"clause_id": "gone"}}) is None
        assert alerts.cause_document_id({}) is None

    def test_the_context_carries_the_document_the_reader_can_follow(self, monkeypatch):
        """The alert names a regulation; the link under it has to reach the
        same one. Echoing the null the event stored names it and links nowhere."""
        from app.core import alerts

        monkeypatch.setattr(alerts, "_clause", lambda cid: {"document_id": "doc_found"})
        monkeypatch.setattr(
            alerts, "_document", lambda did: {"origin": "watched_source", "source_name": "X"}
        )
        context = alerts.explain(
            {
                "entity_id": "prod_1",
                "cause": {"clause_id": "clause_1", "document_id": None},
                "after": {"market": "market_de", "status": "non_compliant"},
                "before": {"status": "attention_required"},
            },
            products_by_id={},
            markets_by_id={},
        )
        assert context["document_id"] == "doc_found"
        assert context["unprompted"] is True
