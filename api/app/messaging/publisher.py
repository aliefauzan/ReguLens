"""Publish helper. Every message carries the current trace_id as an attribute so
the worker can adopt it and the whole pipeline stays queryable by one id."""

from __future__ import annotations

import json
import logging
from functools import lru_cache

from google.cloud import pubsub_v1

from app.observability import get_trace_id, log
from app.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


def publish(topic: str, payload: dict, **attributes: str) -> str:
    settings = get_settings()
    client = _publisher()
    path = client.topic_path(settings.project_id, topic)
    trace_id = get_trace_id()
    future = client.publish(
        path,
        json.dumps(payload).encode("utf-8"),
        trace_id=trace_id,
        **attributes,
    )
    message_id = future.result(timeout=30)
    log(logger, logging.INFO, "published", topic=topic, message_id=message_id)
    return message_id
