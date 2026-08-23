"""Extraction tool bodies.

Plain functions, plain arguments, plain returns — importable and testable with
no ADK, no FastAPI, no network beyond Firestore/GCS. `app/adk/` registers them.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core import documents as documents_core
from app.observability import log

logger = logging.getLogger(__name__)


def extract_text(document_id: str) -> dict[str, Any]:
    """Fetch a document's text for extraction.

    Returns a structured result rather than raising for a miss — an agent
    handles an explicit not-found far better than an exception.
    """
    document = documents_core.get_document(document_id)
    if document is None:
        return {"found": False, "document_id": document_id, "text": ""}
    if document.text_inline:
        return {
            "found": True,
            "document_id": document_id,
            "text": document.text_inline,
            "char_count": len(document.text_inline),
        }

    from app.core.extraction.text import extract_pdf
    from app.settings import get_settings

    settings = get_settings()
    _, _, path = document.storage_uri.partition(f"gs://{settings.uploads_bucket}/")
    from google.cloud import storage

    data = storage.Client(project=settings.project_id).bucket(
        settings.uploads_bucket
    ).blob(path).download_as_bytes()
    extraction = extract_pdf(data)
    return {
        "found": True,
        "document_id": document_id,
        "text": extraction.text,
        "char_count": extraction.char_count,
    }


def emit_clause_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Receive the model's proposed clauses.

    Deliberately does NOT persist anything. This tool is the model's only
    output channel; the pipeline re-validates every element through
    `build_candidate` before anything reaches Firestore, so even a hallucinated
    tool call cannot write state.
    """
    if not isinstance(candidates, list):
        return {"received": 0, "error": "candidates must be a JSON array"}
    log(logger, logging.INFO, "candidates emitted", count=len(candidates))
    return {"received": len(candidates)}
