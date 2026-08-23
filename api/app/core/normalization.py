"""Substance and unit normalization.

This is the hidden load-bearing piece of the whole system. If the product says
"sodium benzoate" and a clause says "E211", nothing downstream matches and the
UI cheerfully reports no issues — a false negative that looks exactly like
success. Hence the synonym table, and hence its tests.

Unknown names pass through slugified and flagged. We never guess a mapping: a
wrong normalization is worse than an admitted unknown, because it silently
compares two different substances.
"""

from __future__ import annotations

import re

from app.models import Unit

# Canonical substance -> every spelling we expect to meet. Indonesian and
# English both appear because the source documents do.
SYNONYMS: dict[str, list[str]] = {
    "sodium_benzoate": [
        "sodium benzoate",
        "natrium benzoat",
        "natrium benzoate",
        "e211",
        "e 211",
        "ins 211",
        "benzoate of soda",
    ],
    "benzoic_acid": [
        "benzoic acid",
        "asam benzoat",
        "e210",
        "e 210",
        "ins 210",
        # The EU Annex II tables name the whole permitted group on limit rows.
        "benzoic acid - benzoates",
        "benzoic acid benzoates",
    ],
    "potassium_benzoate": ["potassium benzoate", "kalium benzoat", "e212", "ins 212"],
    "calcium_benzoate": ["calcium benzoate", "kalsium benzoat", "e213", "ins 213"],
    "sorbic_acid": [
        "sorbic acid",
        "asam sorbat",
        "e200",
        "ins 200",
        "sorbic acid - sorbates",
        "sorbic acid sorbates",
    ],
    "potassium_sorbate": ["potassium sorbate", "kalium sorbat", "e202", "ins 202"],
    "sulphur_dioxide": ["sulphur dioxide", "sulfur dioxide", "sulfur dioksida", "e220", "ins 220"],
    "citric_acid": ["citric acid", "asam sitrat", "e330", "ins 330"],
    "ascorbic_acid": ["ascorbic acid", "asam askorbat", "vitamin c", "e300", "ins 300"],
    "ginger": ["ginger", "jahe", "zingiber officinale"],
    "turmeric": ["turmeric", "kunyit", "curcuma longa"],
    "honey_powder": ["honey powder", "bubuk madu", "madu bubuk"],
    "cinnamon": ["cinnamon", "kayu manis"],
    "sucrose": ["sucrose", "sugar", "gula", "sukrosa"],
    "salt": ["salt", "garam", "sodium chloride"],
    "maltodextrin": ["maltodextrin", "maltodekstrin"],
    "stevia": ["stevia", "steviol glycosides", "e960", "ins 960"],
    "aspartame": ["aspartame", "aspartam", "e951", "ins 951"],
    "tartrazine": ["tartrazine", "tartrazin", "e102", "ins 102"],
    "carmine": ["carmine", "karmin", "cochineal", "e120", "ins 120"],
}

_LOOKUP: dict[str, str] = {
    synonym: canonical for canonical, synonyms in SYNONYMS.items() for synonym in synonyms
}

_UNITS: dict[str, Unit] = {
    "%": Unit.PERCENT_W_W,
    "percent": Unit.PERCENT_W_W,
    "percent_w_w": Unit.PERCENT_W_W,
    "% w/w": Unit.PERCENT_W_W,
    "w/w": Unit.PERCENT_W_W,
    "mg/kg": Unit.MG_PER_KG,
    "mg per kg": Unit.MG_PER_KG,
    "mg_per_kg": Unit.MG_PER_KG,
    # EU Annex II headers read "Maximum level (mg/l or mg/kg as appropriate)".
    # For aqueous products (the MVP scope) mg/l and mg/kg are numerically
    # equivalent at the density of water; the equivalence is a documented
    # modelling decision, applied identically to both sides of any comparison.
    "mg/l": Unit.MG_PER_KG,
    "mg/l or mg/kg": Unit.MG_PER_KG,
    "mg/l or mg/kg as appropriate": Unit.MG_PER_KG,
    "ppm": Unit.PPM,
    "parts per million": Unit.PPM,
}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def normalize_substance(name: str) -> tuple[str, bool]:
    """Return (normalized, unnormalized_flag).

    The flag is the honest part: a slugified passthrough is not a match, and the
    UI must be able to say so rather than implying we recognised the ingredient.
    """
    key = re.sub(r"\s+", " ", (name or "").strip().lower())
    # EU tables use em/en-dashes inside group names ("Benzoic acid — benzoates").
    key = key.replace("—", "-").replace("–", "-")
    if key in _LOOKUP:
        return _LOOKUP[key], False
    # "sodium benzoate (E211)" and "Sodium Benzoate, E211" both appear in the wild.
    for part in re.split(r"[(),/-]", key):
        part = part.strip()
        if part in _LOOKUP:
            return _LOOKUP[part], False
    return slugify(key), True


def parse_unit(raw: str | None) -> Unit:
    """Normalize a unit string, or raise. Silently coercing an unknown unit is
    how a limit comparison becomes fiction."""
    if raw is None:
        raise ValueError("unit is required when an amount is given")
    key = re.sub(r"\s+", " ", raw.strip().lower())
    if key in _UNITS:
        return _UNITS[key]
    raise ValueError(f"unrecognised unit '{raw}'. Use one of: %, mg/kg, ppm")
