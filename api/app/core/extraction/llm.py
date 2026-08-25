"""Gemini extraction calls. Structured output only — never prose parsing.

Two independent samples at low temperature feed the self-consistency term of
the composite confidence. `FAKE_LLM=1` returns canned candidates so integration
tests and offline work cost nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from functools import lru_cache
from typing import Any

from app.models import ClauseType
from app.observability import log
from app.settings import get_settings

logger = logging.getLogger(__name__)

_SYSTEM = """You are a regulatory-clause extraction engine. From the document
text, extract every distinct regulatory statement that imposes a requirement on
food, beverage, cosmetic or supplement products.

CRITICAL RULE about units: regulatory tables state the measurement unit in the
column header, for example "Maximum level (mg/l or mg/kg as appropriate)".
That header applies to every numeric value in the table below it. When you emit
a numeric_limit clause from such a table, set unit_raw to "mg/kg" (or whatever
the header says) even though the number's own cell does not repeat it. A
numeric_limit without a unit_raw is an incomplete extraction.

Return a JSON array. Each element has exactly these fields:
- text: the verbatim source sentence(s) for this clause
- clause_type: one of numeric_limit | documentation | labeling | certification | other
- substance: substance name as written in the document, or null for non-substance rules
- limit_value: the number in the limit, or null when there is no numeric limit
- unit_raw: REQUIRED whenever limit_value is set. Copy it from wherever the
  table states its basis (column headers like "Maximum level (mg/l or mg/kg)"
  count). Use "mg/kg" for milligrams per kilogram, "%" for percent, "ppm" for
  parts per million.
- product_type: one of food_beverage_powder | food_beverage_liquid | food_solid |
  supplement | cosmetic — pick the closest match, or null when unclear
- effective_date: ISO date string when the document states one, else null

Extract only what the text actually says. Never invent limits."""


class TransientLLMError(Exception):
    """Quota, timeout, 5xx — worth a nack and a redelivery."""


class PermanentLLMError(Exception):
    """Malformed beyond repair — nacking would burn five retries for nothing."""


@lru_cache
def _client():
    from google import genai

    settings = get_settings()
    return genai.Client(
        vertexai=True,
        project=settings.project_id,
        location=settings.gemini_location,
    )


def generate_candidates(text: str, *, sample_index: int) -> list[dict[str, Any]]:
    """One structured extraction pass. Returns raw dicts; validation is NOT done
    here — that is candidates.build_candidate's job."""
    settings = get_settings()
    if settings.fake_llm:
        return fake_candidates(text)

    from google.genai import types

    started = time.monotonic()
    try:
        response = _client().models.generate_content(
            model=settings.gemini_model,
            contents=f"{text[:120_000]}",
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                temperature=0.1 + 0.05 * sample_index,
                response_mime_type="application/json",
                response_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "clause_type": {
                                "type": "string",
                                "enum": [c.value for c in ClauseType],
                            },
                            "substance": {"type": "string", "nullable": True},
                            "limit_value": {"type": "number", "nullable": True},
                            "unit_raw": {"type": "string", "nullable": True},
                            "product_type": {"type": "string", "nullable": True},
                            "effective_date": {"type": "string", "nullable": True},
                        },
                        "required": ["text", "clause_type"],
                    },
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001 - classified below
        raise _classify(exc) from exc

    latency_ms = int((time.monotonic() - started) * 1000)
    raw_text = response.text or ""
    prompt_hash = hashlib.sha256(f"{_SYSTEM}{text[:2000]}".encode()).hexdigest()[:16]
    log(
        logger, logging.INFO, "vertex_call",
        stage="extraction", model=settings.gemini_model, sample=sample_index,
        prompt_hash=prompt_hash, latency_ms=latency_ms,
        usage_metadata=str(getattr(response, "usage_metadata", None))[:300],
    )

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PermanentLLMError(f"model returned unparseable JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise PermanentLLMError("model returned JSON that is not an array")
    return payload


def _classify(exc: Exception) -> Exception:
    message = str(exc).lower()
    transient_markers = (
        "429", "quota", "rate", "timeout", "timed out", "503", "500",
        "unavailable", "deadline", "connection", "reset",
    )
    if any(marker in message for marker in transient_markers):
        return TransientLLMError(str(exc))
    return PermanentLLMError(str(exc))


def fake_candidates(text: str) -> list[dict[str, Any]]:
    """Deterministic canned extraction for FAKE_LLM mode.

    Keyed on the document's own text, so the local stack reproduces the real
    divergence: an Indonesian/BPOM source yields 400 mg/kg, an EU source 150
    mg/kg. Deliberately includes one candidate that fails validation, so the
    rejection path is exercised by every fake run instead of only by
    adversarial tests.
    """
    lowered = text.lower()
    clauses: list[dict[str, Any]] = []
    indonesian = any(m in lowered for m in ("bpom", "badan pom", "natrium benzoat", "batas maksimal"))
    if indonesian:
        clauses.append(
            {
                "text": (
                    "Natrium benzoat (INS 211) dalam minuman berbasis air berperisa: "
                    "batas maksimal 400 mg/kg dihitung sebagai asam benzoat."
                ),
                "clause_type": "numeric_limit",
                "substance": "natrium benzoat",
                "limit_value": 400,
                "unit_raw": "mg/kg",
                "product_type": "food_beverage_liquid",
                "effective_date": None,
            }
        )
    elif any(m in lowered for m in ("benzoate", "benzoat", "e211", "e 211")):
        clauses.append(
            {
                "text": (
                    "The maximum permitted level of E 211 sodium benzoate "
                    "in flavoured drinks is 150 mg/kg."
                ),
                "clause_type": "numeric_limit",
                "substance": "sodium benzoate",
                "limit_value": 150,
                "unit_raw": "mg/kg",
                "product_type": "food_beverage_liquid",
                "effective_date": None,
            }
        )
    if not indonesian:
        # EU sources carry a labeling clause too; it has no numeric limit, so it
        # lands in review. Kept off the BPOM baseline so the seeded product
        # reads compliant there, exactly as it does against live Vertex.
        clauses.append(
            {
                "text": (
                    "Food business operators shall ensure that additives are labelled "
                    "in accordance with Regulation (EU) No 1169/2011."
                ),
                "clause_type": "labeling",
                "substance": None,
                "limit_value": None,
                "unit_raw": None,
                "product_type": None,
                "effective_date": None,
            }
        )
    # Invalid on purpose: missing required `clause_type`.
    clauses.append({"text": "Malformed emission with no clause type."})
    return clauses
