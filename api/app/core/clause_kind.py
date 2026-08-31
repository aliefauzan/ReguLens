"""What kind of statement a clause is when it states no number.

The evaluator has one question — is the product under the limit — and one
answer for everything that is not a limit: `non_numeric_clause`, which reaches
the screen as *"This rule has no number in it, so a person has to read it."*

That sentence is the product's motto inverted. It hands the reading back to the
user, and it does so over rows whose meaning is perfectly decidable without a
model: a footnote that explains how another row's number is expressed is not a
requirement at all, "quantum satis" is a stated absence of a maximum, and "may
not be used" is a limit of zero written in words.

This module names those kinds. It reads, it never interprets: each kind is
recognised by the phrasing the regulator actually used, quoted back in
`matched`, so a reader can check the classification the same way they would
check a limit. Anything it does not recognise stays unrecognised — an honest
`None` — and travels the path it travelled before this file existed.
"""

from __future__ import annotations

import re

# Annex II prints its footnotes as a marker and a colon: "(49): The maximum
# usable levels are derived from …". They qualify the numbered rows above them
# and impose nothing by themselves, so a footnote that reaches a product page as
# its own requirement is a rule the regulator never wrote.
_FOOTNOTE_MARKER = re.compile(r"^\s*\(\s*\d{1,3}\s*\)\s*[a-z]?\s*:", re.IGNORECASE)

# The same sentence without the marker, for extractions that dropped it. Each of
# these says "here is how to read a number stated elsewhere", which is the
# defining property of a basis note.
_BASIS_PHRASES = (
    "are expressed as",
    "is expressed as",
    "expressed as steviol",
    "expressed in free",
    "maximum usable levels are derived",
    "are not to be exceeded by use of",
    "limits are expressed",
)

# A stated absence of a maximum. The regulator is not silent here and the row is
# not unreadable — it says the additive may be used at the level needed to do
# its job, which is a decidable answer for any amount.
_NO_MAXIMUM_PHRASES = (
    "quantum satis",
    "secukupnya",
    "cara produksi pangan yang baik",
    "good manufacturing practice",
)

# A limit of zero, written in words.
_PROHIBITION_PHRASES = (
    "may not be used",
    "shall not be used",
    "must not be used",
    "is not permitted",
    "are not permitted",
    "tidak boleh digunakan",
    "dilarang",
)

BASIS_NOTE = "basis_note"
NO_MAXIMUM = "no_maximum"
PROHIBITION = "prohibition"


def _find(text: str, phrases: tuple[str, ...]) -> str | None:
    lowered = " ".join(text.split()).lower()
    return next((phrase for phrase in phrases if phrase in lowered), None)


def classify(text: str | None) -> tuple[str, str] | None:
    """`(kind, the phrase it was read from)`, or None for "not one of these".

    The phrase is half the answer. A classification a reader cannot check is
    the same trust-me the bare `non_numeric_clause` reason was.
    """
    if not text:
        return None
    flat = " ".join(text.split())

    marker = _FOOTNOTE_MARKER.match(flat)
    if marker:
        return BASIS_NOTE, marker.group(0).strip()
    phrase = _find(flat, _BASIS_PHRASES)
    if phrase:
        return BASIS_NOTE, phrase

    # Prohibition is tested before "no maximum" on purpose: an Annex II group
    # row states both at once ("Colours at quantum satis … E 420 may not be
    # used"), and the half that forbids something is the half that binds.
    phrase = _find(flat, _PROHIBITION_PHRASES)
    if phrase:
        return PROHIBITION, phrase
    phrase = _find(flat, _NO_MAXIMUM_PHRASES)
    if phrase:
        return NO_MAXIMUM, phrase
    return None


def kind_of(clause: dict) -> tuple[str, str] | None:
    """The kind of a clause dict, read from its own text every time.

    Read rather than stored, for the reason `scope.category_of` gives: a copied
    field goes stale, and every clause already in Firestore predates this file.
    """
    if clause.get("clause_type") == "numeric_limit":
        return None  # it has a number; nothing here applies
    return classify(clause.get("text"))


def is_basis_note(clause: dict) -> bool:
    """Does this clause explain another clause's number rather than set one?"""
    kind = kind_of(clause)
    return kind is not None and kind[0] == BASIS_NOTE
