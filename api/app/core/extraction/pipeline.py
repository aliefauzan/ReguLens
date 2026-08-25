"""The extraction pipeline: document → text → candidates → clauses + messages.

Plain functions end to end; nothing here imports ADK. Two entry points share
one validation-and-persistence gate:

- `run_extraction` — direct structured-output path (and the FAKE_LLM path).
- `run_extraction_via_agent` — drives the ADK Extraction Agent; if the agent
  emits nothing usable it degrades to the direct path and logs why.

The worker picks per deployment config. Either way, a model emission becomes a
stored clause only through `build_candidate`, never by trust.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core import documents as documents_core
from app.core.clauses import persist_clauses
from app.core.extraction.candidates import best_consistency, build_candidate, finalize_confidence
from app.core.extraction.llm import (
    PermanentLLMError,
    TransientLLMError,
    generate_candidates,
)
from app.models import DocumentStatus, RegulatoryDocument
from app.observability import get_trace_id, log
from app.settings import get_settings

logger = logging.getLogger(__name__)

_SAMPLES = 2


class PermanentExtractionError(Exception):
    """Acks and marks the document failed — retrying cannot help."""


class TransientExtractionError(Exception):
    """Nacks: the message redelivers and extraction runs again later."""


@dataclass
class ExtractionResult:
    document_id: str
    skipped: bool = False  # idempotent no-op: document already past extraction
    accepted: int = 0
    rejected: list[dict[str, Any]] = field(default_factory=list)
    clauses: list[Any] = field(default_factory=list)


def _load_text(document: RegulatoryDocument) -> tuple[str, str]:
    """Return (text, method). Pasted-text documents carry their content inline;
    PDFs are re-fetched from GCS and parsed here, in the worker."""
    if document.text_inline:
        return document.text_inline, "pasted_text"
    if not document.storage_uri:
        raise PermanentExtractionError("document has neither inline text nor a storage URI")

    from app.storage import download

    data = download(document.storage_uri)

    from app.core.extraction.text import extract_pdf

    extraction = extract_pdf(data)
    documents_core.set_status(
        document.id,
        document.status,
        extra={
            "page_count": extraction.page_count,
            "char_count": extraction.char_count,
            "text_method": extraction.method,
            "text_preview": extraction.text[:500],
        },
    )
    return extraction.text, extraction.method


def _direct_samples(text: str) -> list[list[dict[str, Any]]]:
    samples: list[list[dict[str, Any]]] = []
    for sample_index in range(_SAMPLES):
        try:
            samples.append(generate_candidates(text, sample_index=sample_index))
        except TransientLLMError as exc:
            raise TransientExtractionError(str(exc)) from exc
        except PermanentLLMError as exc:
            raise PermanentExtractionError(str(exc)) from exc
    return samples


def _apply(
    document: RegulatoryDocument,
    samples: list[list[dict[str, Any]]],
    parse_quality: float,
    text: str,
) -> ExtractionResult:
    """The single gate from model output to Firestore state."""
    raw_a, raw_b = (list(samples) + [[], []])[:_SAMPLES]
    primary, secondary = raw_a or [], raw_b or []
    log(
        logger, logging.INFO, "extraction_candidates",
        document_id=document.id, sample_a=len(primary), sample_b=len(secondary),
    )

    candidates: list[Any] = []
    rejected: list[dict[str, Any]] = []
    for raw in primary:
        candidate, rejection = build_candidate(
            raw,
            document_id=document.id,
            source_type=str(document.source_type),
            declared_effective_date=document.declared_effective_date,
            source_jurisdiction=str(document.jurisdiction or ""),
        )
        if rejection:
            rejected.append(rejection)
            log(
                logger, logging.INFO, "candidate_rejected",
                document_id=document.id,
                reason=rejection.get("reason"), detail=rejection.get("detail"),
            )
            continue
        assert candidate is not None
        consistency = best_consistency(raw, secondary)
        candidate = candidate.model_copy(
            update={"parse_quality": parse_quality, "self_consistency": consistency}
        )
        candidates.append(finalize_confidence(candidate))

    mean_consistency = (
        round(sum(c.self_consistency for c in candidates) / len(candidates), 4)
        if candidates
        else 0.0
    )
    log(
        logger, logging.INFO, "confidence_computed",
        document_id=document.id,
        parse_quality=parse_quality,
        self_consistency=mean_consistency,
        accepted=len(candidates),
        rejected=len(rejected),
    )

    if candidates:
        # persist_clauses assigns the Firestore ids and echoes them back in
        # order — the publish below depends on them being real.
        clause_ids = persist_clauses(candidates)
    else:
        clause_ids = []

    documents_core.set_status(
        document.id,
        DocumentStatus.EXTRACTED,
        extra={"parse_quality": parse_quality},
    )
    documents_core.append_stage_log(
        document.id,
        "extracted",
        ok=True,
        detail={"clause_count": len(candidates), "rejected": len(rejected)},
    )
    _record_debug(document.id, parse_quality, mean_consistency, rejected)
    _publish_clause_messages(document.id, clause_ids)
    for candidate, cid in zip(candidates, clause_ids, strict=False):
        candidate.id = cid

    return ExtractionResult(
        document_id=document.id,
        accepted=len(candidates),
        rejected=rejected,
        clauses=candidates,
    )


def run_extraction(document_id: str) -> ExtractionResult:
    """Direct-path extraction. Idempotent by document state: anything already
    past `extracting` is a skipped no-op. Raises Permanent/Transient so the
    caller decides ack-vs-nack."""
    document = _begin(document_id)
    if document is None:
        return ExtractionResult(document_id=document_id, skipped=True)
    try:
        text, method = _load_text(document)
    except PermanentExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 - unreadable bytes are permanent
        raise PermanentExtractionError(f"text extraction failed: {exc}") from exc

    return _apply(document, _direct_samples(text), _parse_quality(document, text, method), text)


async def run_extraction_via_agent(document_id: str) -> ExtractionResult:
    """ADK-agent extraction: the agent loads the text itself via its tool and
    emits candidates through `emit_clause_candidates`. Two agent runs feed the
    self-consistency term. Empty emissions degrade to the direct path."""
    document = _begin(document_id)
    if document is None:
        return ExtractionResult(document_id=document_id, skipped=True)
    try:
        text, method = _load_text(document)
    except PermanentExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 - unreadable bytes are permanent
        raise PermanentExtractionError(f"text extraction failed: {exc}") from exc

    from app.adk.extraction_agent import run_extraction_agent

    samples: list[list[dict[str, Any]]] = []
    try:
        for _ in range(_SAMPLES):
            emitted = await run_extraction_agent(document_id)
            if emitted:
                samples.append(emitted)
    except Exception as exc:  # noqa: BLE001 - any ADK failure degrades, never aborts
        log(logger, logging.WARNING, "adk_path_failed", document_id=document_id, error=str(exc))

    if len(samples) < _SAMPLES:
        log(
            logger, logging.WARNING, "adk_fallback_to_direct",
            document_id=document_id, adk_samples=len(samples),
        )
        samples.extend(_direct_samples(text))

    return _apply(document, samples[:_SAMPLES], _parse_quality(document, text, method), text)


def _begin(document_id: str) -> RegulatoryDocument | None:
    """State check + transition to `extracting`. Returns None when the document
    is already past extraction — an idempotent no-op for a redelivered
    message."""
    document = documents_core.get_document(document_id)
    if document is None:
        raise PermanentExtractionError(f"document {document_id} does not exist")
    if document.status in (
        DocumentStatus.EXTRACTED,
        DocumentStatus.RECONCILING,
        DocumentStatus.RECONCILED,
    ):
        log(logger, logging.INFO, "idempotent_skip", stage="extract", document_id=document_id)
        return None
    documents_core.set_status(document_id, DocumentStatus.EXTRACTING)
    documents_core.append_stage_log(document_id, "extracting", ok=True)
    return document


def _parse_quality(document: RegulatoryDocument, text: str, method: str) -> float:
    from app.core.extraction.text import compute_parse_quality

    return compute_parse_quality(
        char_count=document.char_count or len(text),
        page_count=max(document.page_count or 1, 1),
        method=method,
        text=text[:5000],
    )


def _publish_clause_messages(document_id: str, clause_ids: list[str]) -> None:
    """One `clause.extracted` per clause, published only after the batch commit
    so a consumer can never read a half-written set."""
    if not clause_ids:
        return
    from app.messaging.publisher import publish

    topic = get_settings().topic_clause_extracted
    for clause_id in clause_ids:
        publish(topic, {"clause_id": clause_id, "document_id": document_id})


def _record_debug(
    document_id: str,
    parse_quality: float,
    consistency: float,
    rejected: list[dict[str, Any]],
) -> None:
    """Dev-only debug record backing GET /debug/documents/{id}."""
    from google.cloud import firestore

    from app.db import get_db

    get_db().collection("extraction_debug").document(document_id).set(
        {
            "parse_quality": parse_quality,
            "self_consistency": consistency,
            "rejected": rejected,
            "trace_id": get_trace_id(),
            "at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
