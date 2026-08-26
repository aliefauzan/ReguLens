"""Bundled sample regulations and the demo product.

A first-time user has no regulation PDF to hand. Without something to ingest,
the whole product is a set of empty pages and the only way through is for
someone to explain it out loud. These samples are the way through on your own:
real excerpts from the corpus in `data/regulations/` (see SOURCES.md), carried
in the image because only `app/` is copied into it.

Nothing here is synthetic. The text below is quoted verbatim from the source
documents; if a sample ever needs different wording, change the corpus, not
this file.
"""

from __future__ import annotations

from typing import Any

from app.models import SourceType

# Verbatim from BPOM Perka 11/2019 annex (data/regulations/bpom/).
BPOM_EXCERPT = """Peraturan Badan POM Nomor 11 Tahun 2019 tentang Bahan Tambahan Pangan.

Natrium benzoat (Sodium benzoate), INS: 211. Golongan: Pengawet.

Nomor Kategori Pangan 14.1.4.1 - Minuman Berbasis Air Berperisa yang Berkarbonat:
Batas Maksimal (mg/kg) dihitung sebagai asam benzoat: 400.
"""

# Verbatim from Commission Regulation (EU) No 1129/2011, Annex II, the 14.1.4
# rows (data/regulations/excerpts/EU-annex-II-14.1.4-flavoured-drinks-excerpt.pdf).
EU_EXCERPT = """COMMISSION REGULATION (EU) No 1129/2011 of 11 November 2011
amending Annex II to Regulation (EC) No 1333/2008 of the European Parliament and
of the Council by establishing a Union list of food additives

14.1.4 Flavoured drinks

E-number | Name | Maximum level (mg/l or mg/kg as appropriate) | Restrictions/exceptions
E 160d | Lycopene | 12 | excluding dilutable drinks
E 200-203 | Sorbic acid - sorbates | 300 | excluding dairy-based drinks
E 210-213 | Benzoic acid - benzoates | 150 | excluding dairy-based drinks
E 242 | Dimethyl dicarbonate | 250
"""

# The order matters: the EU sample is listed first because on the seeded
# baseline it is the one that changes an answer.
SAMPLES: list[dict[str, Any]] = [
    {
        "id": "eu_1129_2011_14_1_4",
        "title": "EU limit for preservatives in flavoured drinks",
        "summary": (
            "The Annex II rows for category 14.1.4. Sets benzoates at 150 mg/kg — "
            "stricter than Indonesia, so adding this can change a verdict."
        ),
        "source_type": str(SourceType.OFFICIAL_REGULATION),
        "source_name": "Commission Regulation (EU) No 1129/2011",
        "jurisdiction": "EU",
        "citation": "OJ L 295, 12.11.2011, p. 1 (CELEX 32011R1129)",
        "text": EU_EXCERPT,
    },
    {
        "id": "bpom_perka_11_2019",
        "title": "Indonesian limit for sodium benzoate in drinks",
        "summary": (
            "The BPOM additive annex for category 14.1.4.1. Sets natrium benzoat "
            "at 400 mg/kg."
        ),
        "source_type": str(SourceType.OFFICIAL_REGULATION),
        "source_name": "BPOM Perka 11/2019",
        "jurisdiction": "ID_BPOM",
        "citation": "JDIH BPOM, Peraturan Badan POM No. 11 Tahun 2019",
        "text": BPOM_EXCERPT,
    },
]


def list_samples() -> list[dict[str, Any]]:
    return SAMPLES


def get_sample(sample_id: str) -> dict[str, Any] | None:
    return next((s for s in SAMPLES if s["id"] == sample_id), None)


# The demo product, matching the seed job's baseline: 300 mg/kg sodium benzoate
# is under the Indonesian limit and over the EU one, so the same product reads
# differently in two markets — which is the thing the app exists to show.
DEMO_PRODUCT_NAME = "Herbal Drink Powder"
DEMO_PRODUCT: dict[str, Any] = {
    "name": DEMO_PRODUCT_NAME,
    "product_type": "food_beverage_powder",
    "origin": "ID",
    "packaging": "250g plastic pouch",
    "ingredients": [
        {"name": "ginger"},
        {"name": "turmeric"},
        {"name": "honey powder"},
        {"name": "sodium benzoate", "amount": 300, "unit": "mg_per_kg"},
    ],
    "target_markets": ["market_de", "market_id"],
}
