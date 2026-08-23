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
    producing garbage downstream."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    text = "\n\n".join(pages)
    return TextExtraction(
        text=text,
        page_count=len(pages),
        method="pdfplumber",
        char_count=len(text),
    )


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
