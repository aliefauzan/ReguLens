"""Reading a document that does not fit in one request.

The worker answers a Pub/Sub push inside 300 seconds. A dense four-page annex
already takes 174 of them, so a three-hundred-page one cannot be read inside a
single request no matter how the work is arranged inside it — chunking and
in-request concurrency were already there and do not move that wall. Until now
the honest answer was to refuse the document, which is better than truncating it
but is still a regulation nobody read.

So a long document becomes one message per piece. Each piece gets its own
request budget, each writes its own candidates, and the last piece to finish
reduces them through the same gate a short document goes through.

Three things this has to survive, all of them consequences of at-least-once
delivery:

* **A piece delivered twice.** Each piece writes to a document keyed by its own
  index, so the second delivery overwrites identical content.
* **Two pieces finishing at the same instant.** The reduce is claimed in a
  Firestore transaction; exactly one caller wins it and the other returns.
* **A piece that never arrives.** The job records how many pieces it expects, so
  an incomplete document stays `extracting` with a count rather than silently
  producing clauses from the part that happened to land.
"""

from __future__ import annotations

import logging
from typing import Any

from google.cloud import firestore

from app.core.extraction.pipeline import (
    ExtractionResult,
    PermanentExtractionError,
    _apply,
    _begin,
    _load_text,
    _parse_quality,
)
from app.core.extraction.text import split_for_extraction
from app.db import get_db
from app.messaging.publisher import publish
from app.models import RegulatoryDocument
from app.observability import log
from app.settings import get_settings

logger = logging.getLogger(__name__)

JOBS = "extraction_jobs"
PARTS = "extraction_parts"


def should_fan_out(document: dict[str, Any]) -> bool:
    """Decided from the character count stored at upload, so an ordinary
    document never pays a text extraction just to answer the question."""
    return int(document.get("char_count") or 0) >= get_settings().extraction_fanout_min_chars


def _job_ref(document_id: str):
    return get_db().collection(JOBS).document(document_id)


def _part_ref(document_id: str, index: int):
    return get_db().collection(PARTS).document(f"{document_id}_{index:04d}")


def plan(document_id: str) -> dict[str, Any]:
    """Split a long document and publish one message per piece.

    Returns `{"chunks": n}`. Raises `PermanentExtractionError` when the document
    is longer than the ceiling — refused, not truncated, and named so the page
    can say why rather than showing a document stuck in `extracting`.
    """
    settings = get_settings()
    document = _begin(document_id)
    if document is None:
        return {"skipped": True, "chunks": 0}

    text, method = _load_text(document)
    chunks = split_for_extraction(text)
    if len(chunks) > settings.extraction_max_chunks:
        raise PermanentExtractionError(
            f"this document is {len(text):,} characters, which is "
            f"{len(chunks)} pieces — more than the {settings.extraction_max_chunks} "
            "we will read for one document. Nothing was read: a partly-read "
            "regulation produces a confident answer from the part we happened "
            "to reach."
        )

    _job_ref(document_id).set(
        {
            "document_id": document_id,
            "total": len(chunks),
            "method": method,
            "reduced": False,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )
    log(
        logger, logging.INFO, "extraction_fanout_planned",
        document_id=document_id, chunks=len(chunks), chars=len(text),
    )
    for index, chunk in enumerate(chunks):
        # The text travels in the message rather than being re-split by each
        # consumer: two consumers splitting the same document with different
        # settings would read different documents.
        publish(
            settings.topic_document_chunk,
            {
                "document_id": document_id,
                "chunk_index": index,
                "total": len(chunks),
                "text": chunk,
            },
        )
    return {"chunks": len(chunks), "skipped": False}


def process_chunk(document_id: str, chunk_index: int, text: str) -> dict[str, Any]:
    """Run the model over one piece and store its candidates.

    Self-consistency is scored inside the piece, exactly as it is on the
    single-request path: two samples of the same text agreeing means something,
    and a sample of page one agreeing with a sample of page four means nothing.
    """
    from app.core.extraction.pipeline import _direct_samples

    primary, secondary = _direct_samples(text)
    _part_ref(document_id, chunk_index).set(
        {
            "document_id": document_id,
            "chunk_index": chunk_index,
            "primary": primary,
            "secondary": secondary,
            "stored_at": firestore.SERVER_TIMESTAMP,
        }
    )
    log(
        logger, logging.INFO, "extraction_chunk_stored",
        document_id=document_id, chunk_index=chunk_index,
        primary=len(primary), secondary=len(secondary),
    )
    return {"chunk_index": chunk_index, "candidates": len(primary) + len(secondary)}


def _claim_reduce(document_id: str, total: int) -> bool:
    """Exactly one caller reduces. Two pieces can finish in the same instant,
    and both seeing "all parts present" is the ordinary case, not the rare one."""
    db = get_db()
    job = _job_ref(document_id)

    @firestore.transactional
    def claim(transaction) -> bool:
        snapshot = job.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        if not snapshot.exists or data.get("reduced"):
            return False
        if int(data.get("total") or 0) != total:
            return False
        transaction.update(job, {"reduced": True, "reduced_at": firestore.SERVER_TIMESTAMP})
        return True

    return claim(db.transaction())


def reduce_if_complete(document_id: str) -> ExtractionResult | None:
    """Merge every piece and run it through the ordinary gate, once all pieces
    are in. Returns None while pieces are still missing."""
    snapshot = _job_ref(document_id).get()
    if not snapshot.exists:
        return None
    job = snapshot.to_dict() or {}
    total = int(job.get("total") or 0)
    if job.get("reduced") or not total:
        return None

    parts = {}
    for part in (
        get_db()
        .collection(PARTS)
        .where(filter=firestore.FieldFilter("document_id", "==", document_id))
        .limit(200)
        .stream()
    ):
        data = part.to_dict() or {}
        parts[int(data.get("chunk_index", -1))] = data
    if len(parts) < total or any(i not in parts for i in range(total)):
        log(
            logger, logging.INFO, "extraction_fanout_waiting",
            document_id=document_id, have=len(parts), total=total,
        )
        return None

    if not _claim_reduce(document_id, total):
        return None  # another piece won the race and is reducing

    document_snapshot = get_db().collection("documents").document(document_id).get()
    document = RegulatoryDocument(**((document_snapshot.to_dict() or {}) | {"id": document_id}))
    text = (document_snapshot.to_dict() or {}).get("text_extracted") or ""
    pairs = [(parts[i]["primary"], parts[i]["secondary"]) for i in range(total)]
    log(
        logger, logging.INFO, "extraction_fanout_reducing",
        document_id=document_id, parts=total,
    )
    return _apply(
        document, pairs, _parse_quality(document, text, str(job.get("method") or "unknown")), text
    )
