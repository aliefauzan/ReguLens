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


# Firestore's per-document ceiling is 1 MiB and the rest of the record has to
# fit beside this. 200k characters is about 80 pages of annex.
MAX_STORED_TEXT = 200_000


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
            # The whole text, so "where this came from" can show the passage
            # instead of asking the reader to find it in the PDF themselves.
            # Capped: a Firestore document is 1 MiB and a long annex would eat
            # it. What is cut is recorded, never silently dropped.
            "text_extracted": extraction.text[:MAX_STORED_TEXT],
            "text_truncated": len(extraction.text) > MAX_STORED_TEXT,
        },
    )
    return extraction.text, extraction.method


def _direct_samples(text: str) -> list[list[dict[str, Any]]]:
    """Both samples of one piece of text at once. They are independent by
    construction — the second exists only to disagree with the first — so
    running them in sequence spent a whole extra model pass of wall clock for
    nothing. Order is preserved: sample 0 stays the primary one whose
    candidates become clauses."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=_SAMPLES) as pool:
        futures = [
            pool.submit(generate_candidates, text, sample_index=i) for i in range(_SAMPLES)
        ]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except TransientLLMError as exc:
                raise TransientExtractionError(str(exc)) from exc
            except PermanentLLMError as exc:
                raise PermanentExtractionError(str(exc)) from exc
    return results


def _direct_pairs(text: str) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    """Every chunk's two samples, all in flight together.

    A four-page annex is one model pass emitting fifty-five verbatim clauses,
    and that pass is output-token bound: nothing about it is faster than the
    tokens leaving the model. Splitting the document does not make the model
    faster, it makes the passes concurrent — and a document that fits in one
    chunk takes exactly the path it took before, one pair, unchanged.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.core.extraction.text import split_for_extraction

    chunks = split_for_extraction(text)
    if len(chunks) <= 1:
        samples = _direct_samples(text)
        return [(samples[0] if samples else [], samples[1] if len(samples) > 1 else [])]

    log(logger, logging.INFO, "extraction_chunked", chunks=len(chunks), chars=len(text))
    with ThreadPoolExecutor(max_workers=len(chunks) * _SAMPLES) as pool:
        futures = [
            [pool.submit(generate_candidates, chunk, sample_index=i) for i in range(_SAMPLES)]
            for chunk in chunks
        ]
        pairs: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
        for chunk_futures in futures:
            try:
                primary, secondary = (f.result() for f in chunk_futures)
            except TransientLLMError as exc:
                raise TransientExtractionError(str(exc)) from exc
            except PermanentLLMError as exc:
                raise PermanentExtractionError(str(exc)) from exc
            pairs.append((primary, secondary))
    return pairs


def _apply(
    document: RegulatoryDocument,
    pairs: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    parse_quality: float,
    text: str,
) -> ExtractionResult:
    """The single gate from model output to Firestore state.

    One `(primary, secondary)` pair per piece of the document. Self-consistency
    is scored inside a pair and never across them: two samples of the same text
    agreeing means something, a sample of page one agreeing with a sample of
    page four means nothing at all.
    """
    log(
        logger, logging.INFO, "extraction_candidates",
        document_id=document.id,
        parts=len(pairs),
        sample_a=sum(len(p) for p, _ in pairs),
        sample_b=sum(len(s) for _, s in pairs),
    )

    candidates: list[Any] = []
    rejected: list[dict[str, Any]] = []
    for primary, secondary in pairs:
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
        _embed_batch(candidates, clause_ids)
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

    return _apply(document, _direct_pairs(text), _parse_quality(document, text, method), text)


async def run_extraction_via_agent(document_id: str) -> ExtractionResult:
    """ADK-agent extraction: the agent loads the text itself via its tool and
    emits candidates through `emit_clause_candidates`. Two agent runs feed the
    self-consistency term. Empty emissions degrade to the direct path."""
    import asyncio

    # Everything in this function except the agent runs is blocking I/O:
    # Firestore, GCS, pdf parsing, the direct-path model calls. On the worker's
    # event loop that stalls every other push delivery in flight, so each piece
    # goes to a thread.
    document = await asyncio.to_thread(_begin, document_id)
    if document is None:
        return ExtractionResult(document_id=document_id, skipped=True)
    try:
        text, method = await asyncio.to_thread(_load_text, document)
    except PermanentExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 - unreadable bytes are permanent
        raise PermanentExtractionError(f"text extraction failed: {exc}") from exc

    import time

    from app.adk.extraction_agent import run_extraction_agent
    from app.core.extraction.text import split_for_extraction

    part_count = max(1, len(split_for_extraction(text)))
    pairs: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
    try:
        # Every part's two samples at once. The two samples are independent by
        # construction and the parts are independent of each other, so the whole
        # grid runs concurrently; in sequence it was the sum of all of them.
        async def timed(part: int, sample: int) -> list[dict]:
            begun = time.monotonic()
            emitted = await run_extraction_agent(document_id, part)
            log(
                logger, logging.INFO, "adk_sample_timing",
                document_id=document_id, part=part, sample=sample,
                seconds=round(time.monotonic() - begun, 1), candidates=len(emitted),
            )
            return emitted

        gather_started = time.monotonic()
        runs = await asyncio.gather(
            *(
                timed(part, sample)
                for part in range(part_count)
                for sample in range(_SAMPLES)
            ),
            return_exceptions=True,
        )
        log(
            logger, logging.INFO, "adk_samples_complete",
            document_id=document_id, parts=part_count,
            seconds=round(time.monotonic() - gather_started, 1),
        )
        for part in range(part_count):
            pair = runs[part * _SAMPLES : part * _SAMPLES + _SAMPLES]
            cleaned: list[list[dict]] = []
            for emitted in pair:
                if isinstance(emitted, BaseException):
                    log(
                        logger, logging.WARNING, "adk_path_failed",
                        document_id=document_id, part=part, error=str(emitted),
                    )
                    continue
                if emitted:
                    cleaned.append(emitted)
            if len(cleaned) == _SAMPLES:
                pairs.append((cleaned[0], cleaned[1]))
            else:
                # A part the agent did not answer for is a part whose rules
                # would silently not exist. Fall back for the whole document
                # rather than store a document that is quietly missing pages.
                pairs = []
                break
    except Exception as exc:  # noqa: BLE001 - any ADK failure degrades, never aborts
        log(logger, logging.WARNING, "adk_path_failed", document_id=document_id, error=str(exc))
        pairs = []

    if not pairs:
        log(
            logger, logging.WARNING, "adk_fallback_to_direct",
            document_id=document_id, parts=part_count,
        )
        pairs = await asyncio.to_thread(_direct_pairs, text)

    quality = _parse_quality(document, text, method)
    return await asyncio.to_thread(_apply, document, pairs, quality, text)


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


def _embed_batch(candidates: list[Any], clause_ids: list[str]) -> None:
    """Embed the whole document's clauses in one place, before reconciliation
    asks for them.

    Reconciliation still embeds a clause it finds without a vector, so this is
    a fast path and not a new dependency: if the batch call fails the pipeline
    carries on exactly as it did before, one clause at a time.
    """
    from app.core.clauses import store_embeddings
    from app.core.reconciliation import embed_texts

    try:
        vectors = embed_texts([c.text or "" for c in candidates])
        store_embeddings(dict(zip(clause_ids, vectors, strict=False)))
    except Exception as exc:  # noqa: BLE001 - retrieval degrades, extraction does not fail
        log(
            logger, logging.WARNING, "batch_embed_failed",
            count=len(clause_ids), error=str(exc)[:200],
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
