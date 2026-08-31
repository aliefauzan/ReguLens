"""Gemini extraction calls. Structured output only — never prose parsing.

Two independent samples at low temperature feed the self-consistency term of
the composite confidence. `FAKE_LLM=1` returns canned candidates so integration
tests and offline work cost nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
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
def _owned_transport():
    """A transport this process owns.

    `google.genai`'s `BaseApiClient` closes its httpx client when it is garbage
    collected — and its own source says so, noting that ADK cannot rely on that
    behaviour. It guards the close with `if not self._http_options.httpx_client`:
    a client the caller supplied is the caller's to close. Supplying one is
    therefore the documented way to opt out of having the transport closed under
    us, and opting out is not optional here. Three times in production a
    document was recorded `failed` with "Cannot send a request, as the client
    has been closed" — the ADK extraction path emitted nothing for one part of
    a long regulation, the pipeline degraded to the direct path exactly as
    designed, and the fallback died on a transport somebody else's finished
    object had shut.

    The cache is load-bearing: it is what keeps the client alive, and it is
    also why nothing here closes it. It lives as long as the process.
    """
    import httpx

    return httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(600.0, connect=30.0),
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
    )


def _http_options():
    """`HttpOptions` carrying the transport we own."""
    from google.genai import types

    return types.HttpOptions(httpx_client=_owned_transport())


@lru_cache
def _client():
    """One client for every generation call in the app. An API key routes to
    the Gemini Developer API and its free tier; without one we fall back to
    Vertex, which bills per token."""
    from google import genai

    settings = get_settings()
    if settings.use_gemini_api:
        # vertexai=False is explicit on purpose: GOOGLE_GENAI_USE_VERTEXAI is
        # still set in the Cloud Run env, and the SDK reads it as the default.
        return genai.Client(
            vertexai=False, api_key=settings.gemini_api_key, http_options=_http_options()
        )
    return genai.Client(
        vertexai=True,
        project=settings.project_id,
        location=settings.gemini_location,
        http_options=_http_options(),
    )


# The SDK's own words when the transport under a cached client has been closed
# by something else in the process.
_CLOSED_CLIENT = "client has been closed"


@lru_cache
def _keyed_client(api_key: str):
    """A client for one specific key, separate from the app-wide one.

    Country discovery needs the Gemini Developer API because Vertex does not
    serve Gemma, while the rest of the app may be deliberately on Vertex. Two
    clients keep those choices independent — and this one is built with the same
    owned transport, because the SDK closing a transport it created is the bug
    that killed the direct extraction path three times in production.
    """
    from google import genai

    return genai.Client(vertexai=False, api_key=api_key, http_options=_http_options())


def _generate(*, _client_for: Any = None, **kwargs: Any):
    """One generation call, surviving a client that something else closed.

    The cached client holds an httpx transport, and the ADK runner's own genai
    client shares enough of that machinery that when a finished runner is
    collected, our cached client can come back closed. It shows up in exactly
    the worst place: the ADK path emits nothing for one part of a document, the
    pipeline degrades to this direct path on purpose — and the fallback dies
    with "Cannot send a request, as the client has been closed", so a document
    that had a working path left is recorded as `failed`.

    Observed in production on 23, 28 and 29 August. Rebuilding once and
    retrying is the whole fix; a second closure inside one call is a real fault
    and is raised.
    """
    # Bound to a local first. `_client().models.generate_content(...)` leaves
    # the client itself unreferenced the moment `.models` is read, and a
    # concurrent `cache_clear()` then makes it collectable mid-call — the same
    # closed-transport failure arriving by a second route.
    factory = _client_for or _client
    client = factory()
    try:
        return client.models.generate_content(**kwargs)
    except Exception as exc:  # noqa: BLE001 - re-raised below unless it is the one case
        if _CLOSED_CLIENT not in str(exc).lower():
            raise
        # Should now be unreachable: the transport is ours and nothing closes
        # it. Kept because the failure it covers was silent, cost a whole
        # document, and took three production runs to see.
        log(logger, logging.WARNING, "genai_client_reopened", error=str(exc)[:200])
        _client.cache_clear()
        _keyed_client.cache_clear()
        return factory().models.generate_content(**kwargs)


def generate_structured(
    *,
    model: str,
    contents: str,
    system_instruction: str,
    response_schema: dict[str, Any],
    temperature: float = 0.0,
    api_key: str | None = None,
) -> str:
    """One JSON generation call against an arbitrary model. Returns raw text.

    Here rather than in the caller because of `_generate`: the closed-transport
    workaround above cost three production runs to find, and a second call site
    that built its own client would reintroduce the bug it fixes. Callers get
    the text and do their own parsing — a model that ignores the schema is the
    caller's problem to detect, not something to paper over here.
    """
    from google.genai import types

    response = _generate(
        _client_for=(lambda: _keyed_client(api_key)) if api_key else None,
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=response_schema,
        ),
    )
    return response.text or ""


def generate_candidates(text: str, *, sample_index: int) -> list[dict[str, Any]]:
    """One structured extraction pass. Returns raw dicts; validation is NOT done
    here — that is candidates.build_candidate's job."""
    settings = get_settings()
    if settings.fake_llm:
        return fake_candidates(text)

    from google.genai import types

    started = time.monotonic()
    try:
        response = _generate(
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


# A limit table states its unit once, in a header. Rows that say "quantum
# satis" or "CPPB" carry no number and are not numeric limits.
_EU_ROW = re.compile(r"^\|?\s*(E\s?[\d\-–—\s()a-z]+?)\s*\|\s*([^|]{3,90}?)\s*\|\s*([^|]*?)\s*(?:\||$)")
_BPOM_ROW = re.compile(r"^(\d{2}(?:\.\d+)*)\s+(.{6,120}?)\s+(\d[\d\s.]*)$")
_BPOM_SUBSTANCE = re.compile(r"—\s*([^,]{3,80}?),\s*INS")
# A ceiling, not a filter: a long annex section runs to hundreds of rows and
# nobody needs all of them offline. High enough that the categories the demo
# turns on — the flavoured-drink rows, two thirds of the way down the BPOM
# tables — are always inside it.
_FAKE_ROW_CAP = 60


_EU_CATEGORY = re.compile(r"[Ff]ood category (\d{1,2}(?:\.\d+)*)")


def _fake_product_type(category: str | None) -> str:
    """Which kind of product a food-category number describes.

    Read from the number, not from words in the rows: a bakery table mentions
    milk and a preservative table mentions supplements, and keyword-sniffing the
    whole block labels both wrongly.
    """
    if not category:
        return "food_solid"
    if category.startswith(("14.1", "01.1", "01.4")):
        return "food_beverage_liquid"
    if category.startswith(("13.6", "17")):
        return "supplement"
    return "food_solid"


def _fake_number(raw: str) -> float | None:
    """Table numbers are written with spaces as thousands separators."""
    cleaned = raw.replace("\u00a0", " ").replace(" ", "").replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        return None
    return float(cleaned)


# A date the document states about itself. The real prompt asks for
# `effective_date` and Gemini reads it out of prose; the fake cannot parse prose
# and does not pretend to, so it reads one explicit ISO form. That is enough for
# the local stack to exercise a rule that has not entered into force yet, which
# is otherwise only reachable against a paid model.
_FAKE_EFFECTIVE = re.compile(
    r"(?:shall\s+)?appl(?:ies|y)\s+from\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE
)


def _fake_effective_date(text: str) -> str | None:
    found = _FAKE_EFFECTIVE.search(text)
    return found.group(1) if found else None


def _fake_rows(text: str) -> list[dict[str, Any]]:
    """Read an actual limit table, without a model.

    The bundled library carries real tables, and a canned answer that ignores
    them makes every library entry look identical on the local stack — the same
    two clauses, twenty-eight times, disagreeing with themselves. This reads the
    rows that are there. It is not extraction: no judgement, no inference, only
    rows whose substance and number are both unambiguous on one line.
    """
    # An EU block names its category once, in the header carried above it; a
    # BPOM section names its substance there instead, and each row carries its
    # own category number.
    eu_category = _EU_CATEGORY.search(text)
    block_type = _fake_product_type(eu_category.group(1) if eu_category else None)
    substance_header = _BPOM_SUBSTANCE.search(text)
    rows: list[dict[str, Any]] = []
    for line in text.split("\n"):
        line = line.strip()
        if len(rows) >= _FAKE_ROW_CAP:
            break
        eu = _EU_ROW.match(line)
        if eu:
            value = _fake_number(eu.group(3))
            if value is None:
                continue
            rows.append(
                {
                    "text": line,
                    "clause_type": "numeric_limit",
                    "substance": eu.group(2).strip(),
                    "limit_value": value,
                    "unit_raw": "mg/kg",
                    "product_type": block_type,
                    "effective_date": None,
                }
            )
            continue
        bpom = _BPOM_ROW.match(line)
        if bpom and substance_header:
            value = _fake_number(bpom.group(3))
            if value is None:
                continue
            rows.append(
                {
                    # Verbatim: the citation view has to find this line in the
                    # document, so it is quoted, not annotated. The substance
                    # travels in its own field.
                    "text": line,
                    "clause_type": "numeric_limit",
                    "substance": substance_header.group(1).strip(),
                    "limit_value": value,
                    "unit_raw": "mg/kg",
                    "product_type": _fake_product_type(bpom.group(1)),
                    "effective_date": None,
                }
            )
    return rows


def fake_candidates(text: str) -> list[dict[str, Any]]:
    """Deterministic canned extraction for FAKE_LLM mode.

    Two paths. A document carrying a real limit table — every bundled library
    entry does — is read row by row, so the local stack shows the same breadth
    the deployed one does. Anything else falls back to the canned pair that
    reproduces the divergence the demo rests on: an Indonesian source yields
    400 mg/kg, an EU source 150.

    Either way one candidate is malformed on purpose, so the rejection path is
    exercised by every fake run instead of only by adversarial tests.
    """
    stated = _fake_effective_date(text)
    parsed = _fake_rows(text)
    if parsed:
        if stated:
            for row in parsed:
                row["effective_date"] = stated
        parsed.append({"text": "Malformed emission with no clause type."})
        return parsed
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
    if stated:
        for clause in clauses:
            clause["effective_date"] = stated
    # Invalid on purpose: missing required `clause_type`.
    clauses.append({"text": "Malformed emission with no clause type."})
    return clauses
