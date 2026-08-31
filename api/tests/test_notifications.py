"""A verdict that never leaves the app is a dashboard, not a monitor.

These tests pin the delivery path: off unless configured, sent once per alert
even when Pub/Sub redelivers, capped so a first ingestion cannot flood a channel,
and loud rather than silent when the channel is down.
"""

import pytest

from app.core import notifications


def alert(alert_id="evt_1", **context) -> dict:
    base_context = {
        "product_id": "prod_1",
        "product_name": "Herbal Drink Powder",
        "market_id": "market_de",
        "market_label": "European Union — Germany",
        "unprompted": True,
        "source_name": "Commission Regulation (EU) 2023/2108",
        "scheduled": False,
        "effective_date": None,
    }
    return {
        "id": alert_id,
        "event_type": "product_status_changed",
        "before": {"status": "compliant"},
        "after": {"status": "non_compliant"},
        "context": base_context | context,
    }


@pytest.fixture
def channel(monkeypatch):
    """A configured webhook that records what it was sent."""
    posted: list[tuple[str, dict]] = []
    marked: list[str] = []

    class Doc:
        def __init__(self, doc_id):
            self.doc_id = doc_id

        def set(self, _data, merge=False):
            marked.append(self.doc_id)

    class Collection:
        def document(self, doc_id):
            return Doc(doc_id)

    class DB:
        def collection(self, _name):
            return Collection()

    def install(alerts, *, url="https://hooks.example.com/x", fails=False, cap=5):
        settings = notifications.get_settings()
        monkeypatch.setattr(settings, "alert_webhook_url", url, raising=False)
        monkeypatch.setattr(settings, "alert_webhook_max_per_run", cap, raising=False)
        monkeypatch.setattr(notifications, "get_settings", lambda: settings)
        monkeypatch.setattr(notifications, "get_db", lambda: DB())
        monkeypatch.setattr(notifications, "firestore_now", lambda: "now")
        import app.core.alerts as alerts_core

        monkeypatch.setattr(alerts_core, "list_alerts", lambda *a, **k: alerts)

        def post(url_, payload, _timeout):
            if fails:
                raise RuntimeError("channel down")
            posted.append((url_, payload))

        monkeypatch.setattr(notifications, "_post", post)
        return posted, marked

    return install


def test_nothing_is_sent_when_no_channel_is_configured(channel):
    posted, _ = channel([alert()], url="")
    result = notifications.deliver_pending()
    assert result == {"configured": False, "sent": 0, "failed": 0}
    assert posted == []


def test_a_worsening_verdict_is_pushed_out(channel):
    posted, _ = channel([alert()])
    assert notifications.deliver_pending()["sent"] == 1
    _, payload = posted[0]
    assert "Herbal Drink Powder" in payload["text"]
    assert payload["to_status"] == "non_compliant"
    assert payload["unprompted"] is True


def test_an_already_notified_alert_is_not_sent_again(channel):
    """Pub/Sub delivers at least once. A channel must not."""
    posted, _ = channel([alert() | {"notified_at": "yesterday"}])
    assert notifications.deliver_pending()["sent"] == 0
    assert posted == []


def test_delivery_is_marked_on_the_event_that_caused_it(channel):
    _, marked = channel([alert("evt_7")])
    notifications.deliver_pending()
    assert marked == ["evt_7"]


def test_a_burst_is_capped_so_a_channel_stays_readable(channel):
    """A first ingestion can move dozens of verdicts. Delivering all of them is
    how a useful channel becomes one people mute."""
    posted, _ = channel([alert(f"evt_{i}") for i in range(20)], cap=5)
    assert notifications.deliver_pending()["sent"] == 5
    assert len(posted) == 5


def test_a_dead_channel_is_reported_and_left_unmarked_for_retry(channel):
    """Silently dropping it would make a broken channel look like a quiet one."""
    _, marked = channel([alert()], fails=True)
    result = notifications.deliver_pending()
    assert result["failed"] == 1
    assert result["sent"] == 0
    assert marked == []


def test_a_scheduled_alert_says_it_is_a_deadline_not_a_breach(channel):
    posted, _ = channel([
        alert(scheduled=True, effective_date="2027-01-12")
        | {"event_type": "product_status_scheduled"}
    ])
    notifications.deliver_pending()
    _, payload = posted[0]
    assert payload["scheduled"] is True
    assert "2027-01-12" in payload["text"]
    assert "change" in payload["text"]
