"""Pub/Sub push envelope parsing.

Push delivery wraps the payload twice: a JSON envelope containing a
base64-encoded `data` field. Getting this shape wrong is a day-one time sink, so
it lives in one tested place rather than in each handler.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import BaseModel, Field


class PubSubMessage(BaseModel):
    data: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    message_id: str = Field(default="", alias="messageId")
    publish_time: str | None = Field(default=None, alias="publishTime")

    model_config = {"populate_by_name": True}


class PubSubPushEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str = ""

    @property
    def payload(self) -> dict[str, Any]:
        if not self.message.data:
            return {}
        return json.loads(base64.b64decode(self.message.data).decode("utf-8"))

    @property
    def trace_id(self) -> str | None:
        return self.message.attributes.get("trace_id")

    @property
    def message_id(self) -> str:
        return self.message.message_id


def parse_push_request(body: dict[str, Any]) -> PubSubPushEnvelope:
    return PubSubPushEnvelope.model_validate(body)
