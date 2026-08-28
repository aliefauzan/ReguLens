"""Find each clause's sentence inside the document it was read from.

A limit is only as good as the reader's ability to check it. "Where this came
from" that answers with a document name is better than an id, but it still asks
the reader to go and find the sentence themselves in a hundred pages of annex.
This module locates the passage, so the UI can open the document at it and
highlight it.

Matching is deliberate about its own uncertainty. Three outcomes:

  exact        the clause text appears in the document, whitespace aside
  approximate  a long enough run of it appears, or the row it names is found by
               its identifier and its number, and we say so
  not_found    we could not locate it, and we say that too

The third is a real answer. Highlighting the wrong paragraph would be worse than
highlighting nothing: the whole point of the citation is that the reader can
trust what it points at.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

# Below this share of the clause matched, an approximate hit is not worth
# showing — it points somewhere the reader would have to argue with.
_MIN_RATIO = 0.6
# Long clause texts are expensive to align and rarely need it; the opening of a
# sentence is enough to place it.
_ALIGN_WINDOW = 400

# A table row opens with its own identifier — an EU E number, a BPOM food
# category number. Together with the row's limit it names one row and no other,
# which is what makes the structured fallback safe.
_ROW_ID = re.compile(r"^\s*((?:E\s?\d{3}[a-z]?(?:\s?[-–—]\s?\d{3}[a-z]?)?)|(?:\d{2}(?:\.\d+)+))\b")
_NUMBER = re.compile(r"\d[\d\s.,]*")


@dataclass(frozen=True)
class Citation:
    clause_id: str
    start: int
    end: int
    match: str  # exact | approximate | not_found

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace, keeping a map from each kept character back to its
    offset in the original. Documents wrap lines where clauses do not."""
    out: list[str] = []
    offsets: list[int] = []
    previous_space = True  # skip leading whitespace
    for index, character in enumerate(text):
        if character.isspace():
            if previous_space:
                continue
            out.append(" ")
            offsets.append(index)
            previous_space = True
            continue
        # Dashes are the punctuation a model is most likely to tidy: the EU
        # tables use an em dash where a quote of them often carries a hyphen.
        out.append("-" if character in "–—‐‑‒−" else character.lower())
        offsets.append(index)
        previous_space = False
    return "".join(out), offsets


def _span(offsets: list[int], start: int, length: int, original_length: int) -> tuple[int, int]:
    """Translate a span in normalized space back to the original text."""
    if not offsets or start >= len(offsets):
        return 0, 0
    end_index = min(start + length, len(offsets)) - 1
    return offsets[start], min(offsets[end_index] + 1, original_length)


def locate(document_text: str, clause_text: str, clause_id: str) -> Citation:
    """Where in `document_text` this clause was read from."""
    if not document_text or not clause_text:
        return Citation(clause_id=clause_id, start=0, end=0, match="not_found")

    haystack, offsets = _normalize(document_text)
    needle, _ = _normalize(clause_text)
    if not needle:
        return Citation(clause_id=clause_id, start=0, end=0, match="not_found")

    found = haystack.find(needle)
    if found >= 0:
        start, end = _span(offsets, found, len(needle), len(document_text))
        return Citation(clause_id=clause_id, start=start, end=end, match="exact")

    # Not verbatim. Try the precise fallback first: a row named by its own
    # identifier and its own number is one row, where character alignment over a
    # window would drag in the rows on either side of it.
    row = _locate_row(document_text, clause_text, clause_id)
    if row.match != "not_found":
        return row

    # Otherwise align the opening of the clause against the document — a model
    # that tidied a dash, a line-wrapped sentence — and accept it only if most
    # of it lines up.
    probe = needle[:_ALIGN_WINDOW]
    anchor = SequenceMatcher(None, haystack, probe, autojunk=False).find_longest_match(
        0, len(haystack), 0, len(probe)
    )
    if not anchor.size:
        return Citation(clause_id=clause_id, start=0, end=0, match="not_found")

    # Score the whole passage around the anchor, not the anchor alone. A quote
    # that differs in three places has a short longest-run and still matches the
    # row it came from; a quote from another document does not.
    window_start = max(0, anchor.a - anchor.b)
    window_end = min(len(haystack), window_start + int(len(probe) * 1.4) + 8)
    window = haystack[window_start:window_end]
    if SequenceMatcher(None, window, probe, autojunk=False).ratio() >= _MIN_RATIO:
        start, end = _span(offsets, window_start, len(window), len(document_text))
        return Citation(clause_id=clause_id, start=start, end=end, match="approximate")

    return Citation(clause_id=clause_id, start=0, end=0, match="not_found")


def _digits(value: str) -> str:
    """A table number with its thousands spacing removed: "10 000" and "10000"
    are the same number written two ways."""
    return re.sub(r"[\s.,]", "", value)


def _locate_row(document_text: str, clause_text: str, clause_id: str) -> Citation:
    """Find the row a clause describes, when it does not quote it word for word.

    A model reading a table writes the row back as a sentence: it reflows the
    wrapped category name and appends the basis from the column header. That is
    a faithful reading and an unfindable string, so character alignment gives up
    on it.

    The row itself is still identifiable: it opens with a number that appears
    once in the table — an E number or a food-category number — and it carries
    the limit. Both together name one row. Either alone would not, and this
    returns nothing rather than guess.
    """
    identifier = _ROW_ID.match(clause_text.strip())
    if not identifier:
        return Citation(clause_id=clause_id, start=0, end=0, match="not_found")
    wanted = re.sub(r"\s+", " ", identifier.group(1)).lower()

    numbers = {_digits(match.group(0)) for match in _NUMBER.finditer(clause_text[len(wanted):])}
    numbers.discard("")
    if not numbers:
        return Citation(clause_id=clause_id, start=0, end=0, match="not_found")

    lines = document_text.split("\n")
    starts: list[int] = []
    position = 0
    for line in lines:
        starts.append(position)
        position += len(line) + 1

    for index, line in enumerate(lines):
        opener = _ROW_ID.match(line)
        if not opener or re.sub(r"\s+", " ", opener.group(1)).lower() != wanted:
            continue
        # The row runs until the next line that opens a row of its own; a
        # wrapped category name belongs to the row above it.
        end_index = index + 1
        while end_index < len(lines) and not _ROW_ID.match(lines[end_index]):
            end_index += 1
        block = "\n".join(lines[index:end_index])
        block_numbers = {_digits(m.group(0)) for m in _NUMBER.finditer(block[len(wanted):])}
        if numbers & block_numbers:
            start = starts[index]
            return Citation(
                clause_id=clause_id,
                start=start,
                end=min(start + len(block), len(document_text)),
                match="approximate",
            )

    return Citation(clause_id=clause_id, start=0, end=0, match="not_found")


def locate_all(document_text: str, clauses: list[dict[str, Any]]) -> list[Citation]:
    """One citation per clause, in the order the clauses were given."""
    return [
        locate(document_text, str(clause.get("text") or ""), str(clause.get("id") or ""))
        for clause in clauses
    ]


def snippet(document_text: str, citation: Citation, *, context: int = 220) -> str:
    """The cited passage with a little of what surrounds it, for a preview."""
    if citation.match == "not_found":
        return ""
    start = max(0, citation.start - context)
    end = min(len(document_text), citation.end + context)
    body = document_text[start:end].strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    return ("… " if start > 0 else "") + body + (" …" if end < len(document_text) else "")
