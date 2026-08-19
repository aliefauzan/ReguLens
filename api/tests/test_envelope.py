import base64
import json

from app.messaging.envelope import parse_push_request


def _push(payload: dict, **attributes: str) -> dict:
    return {
        "message": {
            "data": base64.b64encode(json.dumps(payload).encode()).decode(),
            "attributes": attributes,
            "messageId": "msg-1",
            "publishTime": "2026-08-19T00:00:00Z",
        },
        "subscription": "projects/p/subscriptions/s",
    }


def test_decodes_double_wrapped_payload():
    envelope = parse_push_request(_push({"document_id": "abc"}))
    assert envelope.payload == {"document_id": "abc"}
    assert envelope.message_id == "msg-1"


def test_carries_trace_id_attribute():
    envelope = parse_push_request(_push({}, trace_id="t-123"))
    assert envelope.trace_id == "t-123"


def test_missing_trace_id_is_none_not_an_error():
    assert parse_push_request(_push({})).trace_id is None


def test_empty_data_yields_empty_payload():
    body = {"message": {"attributes": {}, "messageId": "m"}, "subscription": "s"}
    assert parse_push_request(body).payload == {}
