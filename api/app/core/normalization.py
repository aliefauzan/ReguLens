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
        # Annex II writes the group as "Sorbic acid – potassium sorbate".
        "sorbic acid - potassium sorbate",
    ],
    "potassium_sorbate": ["potassium sorbate", "kalium sorbat", "e202", "ins 202"],
    "sulphur_dioxide": [
        "sulphur dioxide",
        "sulfur dioxide",
        "sulfur dioksida",
        "belerang dioksida",
        "sulphur dioxide - sulphites",
        "e220",
        "e 220",
        "ins 220",
    ],
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
    # Everything below is here because the bundled library quotes it. A limit
    # for a substance the dictionary cannot match is a limit nobody is ever
    # compared against, which reads on screen exactly like passing. Each entry
    # is checked against the E number in the EU Annex II row and the INS number
    # in the BPOM section heading — both name themselves in the source text.
    "acesulfame_k": [
        "acesulfame k",
        "acesulfame potassium",
        "asesulfam-k",
        "asesulfam k",
        "e950",
        "e 950",
        "ins 950",
    ],
    "saccharin": [
        "saccharin",
        "sakarin",
        "sodium saccharin",
        "natrium sakarin",
        "calcium saccharin",
        "kalsium sakarin",
        "potassium saccharin",
        "kalium sakarin",
        "e954",
        "e 954",
        "ins 954",
    ],
    "cyclamate": [
        "cyclamate",
        "cyclamic acid",
        "asam siklamat",
        "sodium cyclamate",
        "natrium siklamat",
        "calcium cyclamate",
        "kalsium siklamat",
        "e952",
        "e 952",
        "ins 952",
    ],
    "sucralose": ["sucralose", "sukralosa", "e955", "e 955", "ins 955"],
    "neotame": ["neotame", "neotam", "e961", "e 961", "ins 961"],
    "sunset_yellow": [
        "sunset yellow fcf",
        "sunset yellow",
        "kuning fcf",
        "orange yellow s",
        "e110",
        "e 110",
        "ins 110",
    ],
    "ponceau_4r": ["ponceau 4r", "cochineal red a", "e124", "e 124", "ins 124"],
    "allura_red": ["allura red ac", "allura red", "merah allura", "e129", "e 129", "ins 129"],
    "brilliant_blue": [
        "brilliant blue fcf",
        "biru berlian fcf",
        "biru berlian",
        "e133",
        "e 133",
        "ins 133",
    ],
    "erythrosine": ["erythrosine", "eritrosin", "e127", "e 127", "ins 127"],
    "quinoline_yellow": ["quinoline yellow", "kuning kuinolin", "e104", "e 104", "ins 104"],
    "bha": [
        "bha",
        "butylated hydroxyanisole",
        "butylated hydroxy anisole",
        "butil hidroksianisol",
        "e320",
        "e 320",
        "ins 320",
    ],
    "bht": [
        "bht",
        "butylated hydroxytoluene",
        "butylated hydroxy toluene",
        "butil hidroksitoluen",
        "e321",
        "e 321",
        "ins 321",
    ],
    "sodium_nitrite": ["sodium nitrite", "natrium nitrit", "e250", "e 250", "ins 250"],
    "potassium_nitrite": ["potassium nitrite", "kalium nitrit", "e249", "e 249", "ins 249"],
    "sodium_nitrate": ["sodium nitrate", "natrium nitrat", "e251", "e 251", "ins 251"],
    "potassium_nitrate": ["potassium nitrate", "kalium nitrat", "e252", "e 252", "ins 252"],
    # The curing-salt group names, as the EU Annex II tables print them on the
    # limit rows themselves ("E 249-250 Nitrites", "E 251-252 Nitrates"). An
    # extractor reading those rows normalizes to the group, so the group has to
    # be a name the dictionary knows or the row binds nothing.
    # The singular is here because a person writes it. The annex prints the
    # group plural on the limit row, and a question asking about "nitrite" is
    # asking about that row.
    "nitrites": ["nitrites", "nitrite", "nitrit", "e249-250", "e 249-250"],
    "nitrates": ["nitrates", "nitrate", "nitrat", "e251-252", "e 251-252"],
    "sodium_metabisulphite": [
        "sodium metabisulphite",
        "sodium metabisulfite",
        "natrium metabisulfit",
        "e223",
        "e 223",
        "ins 223",
    ],
    "potassium_metabisulphite": [
        "potassium metabisulphite",
        "kalium metabisulfit",
        "e224",
        "e 224",
        "ins 224",
    ],
    "calcium_sorbate": ["calcium sorbate", "kalsium sorbat", "e203", "e 203", "ins 203"],
    "sodium_sorbate": ["sodium sorbate", "natrium sorbat", "e201", "e 201", "ins 201"],
    "propionic_acid": ["propionic acid", "asam propionat", "e280", "e 280", "ins 280"],
    "calcium_propionate": ["calcium propionate", "kalsium propionat", "e282", "e 282", "ins 282"],
    "natamycin": ["natamycin", "natamisin", "e235", "e 235", "ins 235"],
    "nisin": ["nisin", "e234", "e 234", "ins 234"],
    "dimethyl_dicarbonate": ["dimethyl dicarbonate", "e242", "e 242", "ins 242"],
    "lycopene": ["lycopene", "likopen", "e160d", "e 160d", "ins 160d"],
    "anthocyanins": ["anthocyanins", "antosianin", "e163", "e 163", "ins 163"],
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
    # The live extractions write the pair in both orders, and a header saying
    # "or" states one basis, not two.
    "mg/kg or mg/l": Unit.MG_PER_KG,
    "mg/kg or mg/l as appropriate": Unit.MG_PER_KG,
    "mg per l": Unit.MG_PER_KG,
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
