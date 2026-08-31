"""Text-layer extraction and parse-quality scoring.

Deterministic. No model involvement: parse quality is a property of the bytes,
not of what the model thinks of them.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TextExtraction:
    text: str
    page_count: int
    method: str  # pdfplumber | ocr | pasted_text
    char_count: int


def extract_pdf(data: bytes) -> TextExtraction:
    """pdfplumber over the text layer. OCR is deliberately cut from the MVP —
    documents without a usable text layer fail loudly here rather than quietly
    producing garbage downstream.

    Each page is flushed as soon as its text is out. pdfplumber caches every
    character object it parses on the page, and the cache belongs to the page,
    which belongs to the document, which is held open for the whole loop — so
    without the flush the peak is the *entire* PDF parsed into objects, not the
    one page being read. That is not a theoretical ceiling: a BPOM annex found
    by the nightly sweep took the container past 512 MiB, and again past 1 GiB
    once it was raised, killing the process mid-check both times. The fetch cap
    bounds the download at 20 MB; nothing bounded what parsing it cost.
    """
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
            page.flush_cache()
            # The text map is a separate per-instance cache and only exists once
            # something has asked for it. Guarded because it is not part of the
            # documented surface and a future release may drop it — losing the
            # clear costs memory, raising here would cost the document.
            textmap = getattr(page, "get_textmap", None)
            if hasattr(textmap, "cache_clear"):
                textmap.cache_clear()
    text = "\n\n".join(pages)
    return TextExtraction(
        text=text,
        page_count=len(pages),
        method="pdfplumber",
        char_count=len(text),
    )


# One model pass over a four-page annex spends two minutes emitting fifty-five
# verbatim clauses, and almost all of that is output tokens leaving the model
# one after another. Splitting the document lets those passes run at the same
# time. 12,000 characters is roughly a page and a half of annex — small enough
# to shorten each pass materially, large enough that a limit table and the
# header stating its unit stay in the same piece.
CHUNK_CHARS = 12_000


def split_for_extraction(text: str, max_chars: int | None = None) -> list[str]:
    """Split a document into extraction-sized pieces on blank lines.

    Never mid-line: a limit table row carries its number and its substance on
    one line, and half a row is a wrong clause rather than a missing one. A
    single paragraph longer than the budget is left whole for the same reason —
    the budget is a target, not a guarantee.

    A document that fits returns as one piece, so short uploads take exactly the
    path they took before chunking existed.
    """
    # Read at call time, not bound as a default, so the budget stays one knob.
    max_chars = CHUNK_CHARS if max_chars is None else max_chars
    if len(text) <= max_chars:
        return [text] if text else []

    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for block in text.split("\n\n"):
        block_size = len(block) + 2
        if current and size + block_size > max_chars:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += block_size
    if current:
        chunks.append("\n\n".join(current))
    return [c for c in chunks if c.strip()]


def compute_parse_quality(
    *,
    char_count: int,
    page_count: int,
    method: str = "pdfplumber",
    text: str = "",
) -> float:
    """Deterministic composite of characters-per-page density and the
    non-decodable-character proportion. The OCR penalty is a term so the
    formula is complete even though OCR itself is cut."""
    if page_count <= 0 or char_count == 0:
        return 0.05  # nothing usable came out; extraction will likely fail validation

    chars_per_page = char_count / page_count
    # Saturating ramp: full marks at 1500 chars/page, zero at 50.
    density = min(1.0, max(0.0, (chars_per_page - 50) / (1500 - 50)))

    penalty = (0.15 if method == "ocr" else 0.0) + 0.5 * decode_penalty(text)
    return round(max(0.0, min(1.0, density - penalty)), 4)


def decode_penalty(text: str) -> float:
    """Proportion of replacement / non-printable characters in a text sample.
    High values mean the text layer is corrupt even when dense."""
    if not text:
        return 1.0
    bad = sum(1 for ch in text if ch == "�" or (ch.isprintable() is False and ch not in "\n\t\r"))
    return bad / len(text)
