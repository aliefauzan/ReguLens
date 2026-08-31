"""Which food a clause is written about.

An additive table is not a list of competing limits. It is one limit per food
category: BPOM 11/2019 permits 400 mg/kg of benzoates in flavoured
non-carbonated water-based drinks (14.1.4.2) and 1000 mg/kg in fruit
preparations (04.1.2.8), and both numbers are correct at the same time, in the
same regulation, on the same day.

The reconciler could not see that. A clause carries a substance, a limit, a
jurisdiction and a date, but nothing that says *what food*, so every pair of
rows in one table looked like the same rule stated twice with different numbers
— a supersede question with no date to settle it, which is precisely the case
that goes to the judge and comes back `ambiguous`. Thirty-six rows of one BPOM
table therefore sat in the review queue asking a person to confirm, one at a
time, that a regulation does not contradict itself.

The category is never inferred. It is the code the regulator prints at the head
of the row, in the Codex GSFA numbering BPOM adopts verbatim ("14.1.4.2 Minuman
Berbasis Air Berperisa Tidak Berkarbonat…") and the EU annexes reuse. Reading it
is a regex, not a model call. When it is absent this module says `None` and
nothing downstream pretends otherwise — an unknown category blocks nothing, and
the pair goes to the judge exactly as it did before.
"""

from __future__ import annotations

import re

# A GSFA code is dotted and at least two levels deep: "14.1", "04.1.2.8".
# Anchored at the start, because a code quoted mid-sentence ("… not including
# food category 12.10") is a cross-reference to somewhere else, not this row's
# own scope.
_CODE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,4})[\s ]+(?=\S)")

# "1.5 mg/kg" opens with something shaped exactly like a shallow category code.
# A row's code is followed by the category's name; a measurement is followed by
# its unit. Listing the units is narrower than guessing at names.
_UNIT_WORDS = {
    "mg", "g", "kg", "mg/kg", "g/kg", "ppm", "mgkg", "mg/l", "ml", "l",
    "percent", "%", "persen",
}


def category_code(text: str | None) -> str | None:
    """The food-category code this clause is written for, or None.

    None means "the source did not say here", not "no category" — see
    `categories_comparable`, which treats it as an unknown and blocks nothing.
    """
    if not text:
        return None
    match = _CODE.match(text)
    if not match:
        return None
    rest = text[match.end():].lstrip()
    first_word = re.split(r"[\s ]", rest, maxsplit=1)[0].strip(".,;:()").lower()
    if first_word in _UNIT_WORDS or first_word.startswith("mg/") or first_word.startswith("g/"):
        return None
    return match.group(1)


def category_of(clause: dict) -> str | None:
    """The category of a clause dict. Stored value wins if one is ever written;
    otherwise it is read from the clause's own text, every time, so it cannot
    go stale the way a copied field would."""
    stored = clause.get("category_code")
    if stored:
        return str(stored)
    return category_code(clause.get("text"))


def _levels(code: str) -> list[str]:
    return [part.lstrip("0") or "0" for part in code.split(".")]


def categories_comparable(a: str | None, b: str | None) -> bool:
    """May a rule written for category `a` be weighed against one for `b`?

    - Unknown on either side → yes. This module never turns silence into a
      finding; the pair proceeds down the path it took before this file existed.
    - The same category → yes. Two limits for 14.1.4.2 are a real supersede
      question and still reach the judge.
    - One containing the other ("14.1" and "14.1.4.2") → yes. A limit for all
      soft drinks and a limit for one kind of soft drink genuinely overlap.
    - Different branches ("14.1.4.2" and "04.1.2.8") → no. Not a conflict, not
      an ambiguity, not a question for a person: two different foods.
    """
    if not a or not b:
        return True
    la, lb = _levels(a), _levels(b)
    shorter, longer = (la, lb) if len(la) <= len(lb) else (lb, la)
    return longer[: len(shorter)] == shorter
