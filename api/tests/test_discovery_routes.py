"""The discovery endpoints.

No Firestore and no Pub/Sub: the writes and the publish are stubbed, because
what these tests are for is the contract the UI depends on — a 202 with a job
id, a second press that joins rather than duplicates, and a stream that closes
itself instead of hanging a browser connection open forever.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core import discovery
from app.main import app
from app.settings import get_settings

client = TestClient(app)


@pytest.fixture
def available(monkeypatch):
    """Discovery configured. `discovery_available` is a property on a cached
    settings object, so it is patched on the class."""
    monkeypatch.setattr(
        type(get_settings()), "discovery_available", property(lambda _self: True)
    )


@pytest.fixture
def no_writes(monkeypatch):
    saved: dict = {}
    published: list = []
    monkeypatch.setattr(discovery, "save_job", lambda job_id, job: saved.update({job_id: job}))
    monkeypatch.setattr(discovery, "active_job_for", lambda _code: None)
    monkeypatch.setattr(
        "app.messaging.publisher.publish",
        lambda topic, payload, **attrs: published.append((topic, payload)) or "mid-1",
    )
    return saved, published


def test_countries_are_served_without_the_network() -> None:
    body = client.get("/countries").json()
    assert len(body["countries"]) > 200
    assert {"code": "ID", "name": "Indonesia"} in body["countries"]
    assert "available" in body
    assert body["model"] == get_settings().discovery_model


def test_discovering_queues_a_job(available, no_writes) -> None:
    saved, published = no_writes
    response = client.post("/countries/discover", json={"country_code": "JP"})
    assert response.status_code == 202
    body = response.json()
    assert body["joined"] is False
    assert body["job"]["country_code"] == "JP"
    assert body["job"]["status"] == "queued"
    # The row exists before the message does, so the worker can never be handed
    # a job id that does not resolve.
    assert body["job_id"] in saved
    topic, payload = published[0]
    assert topic == get_settings().topic_country_requested
    assert payload["country_code"] == "JP"
    assert payload["job_id"] == body["job_id"]


def test_pressing_discover_twice_joins_the_run_in_flight(available, monkeypatch) -> None:
    """Two runs would fetch the same regulator twice and spend twice the model
    budget arriving at the same source."""
    running = {"id": "job_existing", "country_code": "JP", "status": "reading"}
    monkeypatch.setattr(discovery, "active_job_for", lambda _code: running)

    def explode(*_a, **_k):
        raise AssertionError("a second job must not be published")

    monkeypatch.setattr("app.messaging.publisher.publish", explode)
    response = client.post("/countries/discover", json={"country_code": "JP"})
    assert response.status_code == 200
    assert response.json()["joined"] is True
    assert response.json()["job_id"] == "job_existing"


def test_an_unknown_country_is_rejected_before_any_work(available, no_writes) -> None:
    assert client.post("/countries/discover", json={"country_code": "ZZ"}).status_code == 404
    assert no_writes[1] == []


def test_a_malformed_code_never_reaches_the_handler(available) -> None:
    assert client.post("/countries/discover", json={"country_code": "JPN"}).status_code == 422


def test_discovery_off_says_so_rather_than_failing_later(monkeypatch) -> None:
    """Gemma is served by the Developer API, not Vertex. A deployment without a
    key has no model for this flow, and saying so here beats a button that
    always fails."""
    monkeypatch.setattr(
        type(get_settings()), "discovery_available", property(lambda _self: False)
    )
    assert client.post("/countries/discover", json={"country_code": "JP"}).status_code == 503


def test_a_missing_job_is_a_404(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "get_job", lambda _id: None)
    assert client.get("/discovery/job_nope").status_code == 404


def test_the_stream_sends_a_snapshot_and_closes_on_a_terminal_status(monkeypatch) -> None:
    """A client that connects late still gets the current state, and a finished
    job does not hold the connection open."""
    monkeypatch.setattr(
        discovery,
        "get_job",
        lambda _id: {"id": "job_1", "status": "done", "committed": 1, "candidates": []},
    )
    with client.stream("GET", "/discovery/job_1/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        payloads = [
            json.loads(line[len("data: ") :])
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]
    assert payloads[-1]["status"] == "done"


def test_the_stream_reports_a_job_that_disappeared(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "get_job", lambda _id: None)
    with client.stream("GET", "/discovery/job_gone/events") as response:
        body = "".join(response.iter_text())
    assert "event: error" in body
    assert "no such job" in body


def test_the_stream_gives_up_out_loud(monkeypatch) -> None:
    """A stream that ends without a word is indistinguishable from a crash."""
    monkeypatch.setattr(discovery, "get_job", lambda _id: {"id": "job_1", "status": "reading"})
    monkeypatch.setattr(get_settings(), "discovery_stream_seconds", 0.0)
    monkeypatch.setattr(get_settings(), "discovery_poll_seconds", 0.01)
    with client.stream("GET", "/discovery/job_1/events") as response:
        body = "".join(response.iter_text())
    assert "event: timeout" in body
