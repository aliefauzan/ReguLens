import json
import logging

from app.observability import JsonFormatter, get_trace_id, set_trace_id


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def _record(msg: str, **extra) -> logging.LogRecord:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)
    if extra:
        record.extra_fields = extra
    return record


def test_every_line_carries_a_trace_id():
    set_trace_id("abc123")
    assert _format(_record("hello"))["trace_id"] == "abc123"


def test_extra_fields_land_as_queryable_json_not_string_interpolation():
    set_trace_id("abc123")
    payload = _format(_record("published", topic="document.uploaded"))
    assert payload["topic"] == "document.uploaded"
    assert payload["message"] == "published"


def test_absent_trace_id_mints_one():
    first = set_trace_id(None)
    assert first and get_trace_id() == first
