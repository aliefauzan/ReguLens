"""Understanding what a user meant by an ingredient name.

`normalization.normalize_substance` answers one question — is this exactly a
name we know? — and answers it strictly, because a wrong mapping silently
compares two different substances. That strictness is right, and it is also why
typing "sodium benzoat" or "meat" into the ingredient list produces a row that
matches nothing and reads on screen exactly like passing.

This module is the other half: when the strict answer is no, work out what the
person probably meant and say so, without ever deciding for them. Three kinds of
"no":

  a near miss     "sodium benzoat", "E-211", "tartrazin" — offer the name
  a food          "meat", "daging ayam", "wheat flour" — not an additive at all,
                  which is normal and worth saying out loud
  genuinely new   nothing close — record it, flag it, check nothing against it

Nothing here mutates a product. It returns suggestions; the user picks.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

from app.core.normalization import SYNONYMS, normalize_substance

# Ordinary foods. Not additives, so no additive annex has a limit for them, and
# a user typing one has not made a mistake — they have listed an ingredient.
# Saying "we do not recognise this" would be true and useless; saying "this is
# food, not an additive" is the actual answer.
FOODS: dict[str, str] = {
    "meat": "meat",
    "daging": "meat",
    "beef": "beef",
    "sapi": "beef",
    "pork": "pork",
    "babi": "pork",
    "chicken": "chicken",
    "ayam": "chicken",
    "fish": "fish",
    "ikan": "fish",
    "shrimp": "shrimp",
    "udang": "shrimp",
    "milk": "milk",
    "susu": "milk",
    "egg": "egg",
    "telur": "egg",
    "rice": "rice",
    "beras": "rice",
    "nasi": "rice",
    "flour": "flour",
    "tepung": "flour",
    "wheat": "wheat",
    "gandum": "wheat",
    "corn": "corn",
    "jagung": "corn",
    "soy": "soy",
    "kedelai": "soy",
    "cocoa": "cocoa",
    "cokelat": "cocoa",
    "chocolate": "cocoa",
    "coffee": "coffee",
    "kopi": "coffee",
    "tea": "tea",
    "teh": "tea",
    "water": "water",
    "air": "water",
    "oil": "oil",
    "minyak": "oil",
    "butter": "butter",
    "mentega": "butter",
    "cheese": "cheese",
    "keju": "cheese",
    "yeast": "yeast",
    "ragi": "yeast",
    "fruit": "fruit",
    "buah": "fruit",
    "vegetable": "vegetable",
    "sayur": "vegetable",
    "starch": "starch",
    "pati": "starch",
}

# Entries the dictionary knows that are foods rather than additives. They
# normalize (so a clause naming them would bind), but no additive annex sets a
# limit for them, and telling a user their ginger "will be checked" promises
# something no regulation offers.
FOOD_CANONICALS: frozenset[str] = frozenset(
    {"ginger", "turmeric", "honey_powder", "cinnamon", "sucrose", "salt", "maltodextrin"}
)

# Words that describe what an additive *does* rather than which one it is. A
# label saying "preservative" hides the name we would need.
FUNCTION_WORDS: dict[str, str] = {
    "preservative": "preservative",
    "pengawet": "preservative",
    "sweetener": "sweetener",
    "pemanis": "sweetener",
    "colour": "colour",
    "color": "colour",
    "pewarna": "colour",
    "antioxidant": "antioxidant",
    "antioksidan": "antioxidant",
    "flavour": "flavouring",
    "flavor": "flavouring",
    "perisa": "flavouring",
    "emulsifier": "emulsifier",
    "pengemulsi": "emulsifier",
    "stabiliser": "stabiliser",
    "stabilizer": "stabiliser",
    "penstabil": "stabiliser",
    "thickener": "thickener",
    "pengental": "thickener",
    "additive": "additive",
    "bahan tambahan pangan": "additive",
    "btp": "additive",
}

# Below this, a "did you mean" is noise: it offers a name the user did not type
# and did not mean, and inviting a wrong pick is worse than offering nothing.
_SUGGEST_RATIO = 0.72
_MAX_SUGGESTIONS = 4


@dataclass(frozen=True)
class Suggestion:
    canonical: str
    label: str
    why: str  # spelling | contains | number


@dataclass(frozen=True)
class Resolution:
    query: str
    recognised: bool
    canonical: str | None
    label: str | None
    kind: str  # additive | food | function | unknown
    message: str
    suggestions: list[Suggestion]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"suggestions": [asdict(s) for s in self.suggestions]}


def _clean(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip().lower())
    return text.replace("—", "-").replace("–", "-")


def label_for(canonical: str) -> str:
    """The plain name of a canonical substance. Every entry's first synonym is
    written to be the readable one."""
    synonyms = SYNONYMS.get(canonical)
    return synonyms[0] if synonyms else canonical.replace("_", " ")


def _numbered(query: str) -> str | None:
    """An E number or INS number written in any of the ways people write them:
    "E211", "e-211", "INS211", "211"."""
    match = re.fullmatch(r"(?:e|ins)?[\s.\-]?(\d{3}[a-z]?)(?:\([iv]+\))?", query)
    if not match:
        return None
    number = match.group(1)
    for canonical, synonyms in SYNONYMS.items():
        if any(re.fullmatch(rf"(?:e|ins)\s?{number}", synonym) for synonym in synonyms):
            return canonical
    return None


def suggest(query: str, *, limit: int = _MAX_SUGGESTIONS) -> list[Suggestion]:
    """Names close enough to what was typed to be worth offering."""
    cleaned = _clean(query)
    if not cleaned:
        return []
    scored: dict[str, tuple[float, str]] = {}
    for canonical, synonyms in SYNONYMS.items():
        best = 0.0
        why = "spelling"
        for synonym in synonyms:
            if cleaned == synonym:
                best, why = 1.0, "spelling"
                break
            # A word that appears inside a name is a strong signal:
            # "benzoate" belongs to four entries and the user wants the list.
            if len(cleaned) >= 4 and (cleaned in synonym or synonym in cleaned):
                if best < 0.9:
                    best, why = 0.9, "contains"
                continue
            ratio = SequenceMatcher(None, cleaned, synonym).ratio()
            if ratio > best:
                best, why = ratio, "spelling"
        if best >= _SUGGEST_RATIO:
            scored[canonical] = (best, why)
    ranked = sorted(scored.items(), key=lambda item: item[1][0], reverse=True)[:limit]
    return [
        Suggestion(canonical=canonical, label=label_for(canonical), why=why)
        for canonical, (_, why) in ranked
    ]


def resolve(query: str) -> Resolution:
    """What we think this ingredient is, and what we will do about it.

    The message is written to be shown as-is. It is the part a user reads, and
    every branch of it has to be true whether or not they read the rest.
    """
    cleaned = _clean(query)
    if not cleaned:
        return Resolution(
            query=query,
            recognised=False,
            canonical=None,
            label=None,
            kind="unknown",
            message="Type an ingredient name.",
            suggestions=[],
        )

    canonical, unnormalized = normalize_substance(cleaned)
    if not unnormalized:
        if canonical in FOOD_CANONICALS:
            return Resolution(
                query=query,
                recognised=True,
                canonical=canonical,
                label=label_for(canonical),
                kind="food",
                message=(
                    f"Recognised as {label_for(canonical)} — a food, not an additive. "
                    "The rules we hold set limits on additives, so nothing here is checked "
                    "against it. That is normal."
                ),
                suggestions=[],
            )
        return Resolution(
            query=query,
            recognised=True,
            canonical=canonical,
            label=label_for(canonical),
            kind="additive",
            message=f"Recognised as {label_for(canonical)}. Rules for it will be checked.",
            suggestions=[],
        )

    numbered = _numbered(cleaned)
    if numbered:
        return Resolution(
            query=query,
            recognised=True,
            canonical=numbered,
            label=label_for(numbered),
            kind="additive",
            message=f"That number is {label_for(numbered)}. Rules for it will be checked.",
            suggestions=[],
        )

    food = FOODS.get(cleaned) or next(
        (name for word, name in FOODS.items() if re.search(rf"\b{re.escape(word)}\b", cleaned)),
        None,
    )
    if food:
        return Resolution(
            query=query,
            recognised=False,
            canonical=None,
            label=None,
            kind="food",
            message=(
                f"That is a food, not an additive. The rules we hold set limits on additives, "
                f"so there is nothing to check {cleaned} against — that is normal, and it does "
                f"not mean the product passed."
            ),
            suggestions=[],
        )

    function = FUNCTION_WORDS.get(cleaned) or next(
        (
            name
            for word, name in FUNCTION_WORDS.items()
            if re.search(rf"\b{re.escape(word)}\b", cleaned)
        ),
        None,
    )
    if function:
        return Resolution(
            query=query,
            recognised=False,
            canonical=None,
            label=None,
            kind="function",
            message=(
                f"That says what the ingredient does ({function}), not which one it is. "
                "Limits are set per substance, so we need the name or the E/INS number from "
                "the label."
            ),
            suggestions=[],
        )

    close = suggest(cleaned)
    if close:
        names = ", ".join(item.label for item in close)
        return Resolution(
            query=query,
            recognised=False,
            canonical=None,
            label=None,
            kind="unknown",
            message=f"We do not know that name. Did you mean {names}?",
            suggestions=close,
        )

    return Resolution(
        query=query,
        recognised=False,
        canonical=None,
        label=None,
        kind="unknown",
        message=(
            "We have no rules keyed to that name, so nothing will be checked against it. "
            "It stays on the product, and everything else is still checked."
        ),
        suggestions=[],
    )
