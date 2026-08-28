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


def extract_text(document_id: str, part: int = 0) -> dict[str, Any]:
    """Fetch a document's text for extraction.

    A long document is served one part at a time: `part` selects which, and
    `parts` says how many there are. A document that fits in one part ignores
    the argument entirely and behaves as it always did.

    Returns a structured result rather than raising for a miss — an agent
    handles an explicit not-found far better than an exception.
    """
    document = documents_core.get_document(document_id)
    if document is None:
        return {"found": False, "document_id": document_id, "text": "", "parts": 0}
    if document.text_inline:
        return _part(document_id, document.text_inline, part)

    # The pipeline parses the PDF once, before the agent runs, and stores the
    # text on the document so the citation view can show the passage. Re-parsing
    # it here meant a 700 KB download and a pdfplumber pass per agent run — the
    # same bytes, three times, on the critical path of every upload.
    # Capped at MAX_STORED_TEXT, which is also roughly where the direct path
    # truncates its prompt, so the agent sees what the direct path would.
    stored = document.text_extracted
    if stored:
        return _part(document_id, stored, part)

    from app.core.extraction.text import extract_pdf
    from app.storage import download

    data = download(document.storage_uri)
    extraction = extract_pdf(data)
    return _part(document_id, extraction.text, part)


def _part(document_id: str, text: str, part: int) -> dict[str, Any]:
    from app.core.extraction.text import split_for_extraction

    chunks = split_for_extraction(text) or [""]
    index = part if 0 <= part < len(chunks) else 0
    piece = chunks[index]
    return {
        "found": True,
        "document_id": document_id,
        "text": piece,
        "char_count": len(piece),
        "part": index,
        "parts": len(chunks),
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
