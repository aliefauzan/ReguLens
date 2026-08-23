"""Cloud Run Job entrypoint — seed and reset the demo baseline.

Runs to completion and exits. The baseline per the demo script, using REAL
corpus numbers (EU Annex II 14.1.4 = 150 mg/kg; BPOM 14.1.4.x = 400 mg/kg):

- markets seeded
- demo product: 300 mg/kg sodium benzoate (0.03%) → compliant in Indonesia,
  no EU data yet so Germany reads `unknown`
- BPOM excerpt ingested through the real pipeline (paste-text path)
- the EU regulation stays un-ingested — that upload is the demo's inflection point

Idempotent by content hash: re-seeding after a wipe rebuilds identically;
re-running without a wipe hits the upload cache.
"""

from __future__ import annotations

import logging
import sys

from app.core import markets
from app.core.documents import create_document
from app.core.extraction.pipeline import run_extraction
from app.core.impact import run_impact_for_product
from app.core.products import create_product
from app.core.reconciliation import reconcile_clause
from app.models import DocumentIn, ProductIn, SourceType
from app.observability import configure_logging, log, set_trace_id
from app.settings import get_settings

settings = get_settings()
configure_logging(settings.log_level, "regulens-job")
logger = logging.getLogger(__name__)

# Verbatim excerpt from BPOM Perka 11/2019 annex (see data/regulations/SOURCES.md).
BPOM_EXCERPT = """Peraturan Badan POM Nomor 11 Tahun 2019 tentang Bahan Tambahan Pangan.

Natrium benzoat (Sodium benzoate), INS: 211. Golongan: Pengawet.

Nomor Kategori Pangan 14.1.4.1 - Minuman Berbasis Air Berperisa yang Berkarbonat:
Batas Maksimal (mg/kg) dihitung sebagai asam benzoat: 400.
"""


def seed() -> int:
    set_trace_id(None)
    markets.seed_markets()

    from app.core.products import list_products

    existing = list_products()
    demo = next((p for p in existing if p.name == "Herbal Drink Powder"), None)
    if demo is None:
        product = create_product(
            ProductIn(
                name="Herbal Drink Powder",
                product_type="food_beverage_powder",
                origin="ID",
                packaging="250g plastic pouch",
                ingredients=[
                    {"name": "ginger"},
                    {"name": "turmeric"},
                    {"name": "honey powder"},
                    {"name": "sodium benzoate", "amount": 300, "unit": "mg_per_kg"},
                ],
                target_markets=["market_de", "market_id"],
            )
        )
    else:
        product = demo

    document, cached = create_document(
        meta=DocumentIn(
            source_type=SourceType.OFFICIAL_REGULATION,
            source_name="BPOM Perka 11/2019",
            jurisdiction="ID_BPOM",
        ),
        text=BPOM_EXCERPT,
    )
    if not cached:
        result = run_extraction(document.id)
        for clause_id in [c.id for c in result.clauses]:
            reconcile_clause(clause_id)

    statuses = run_impact_for_product(product.id)["statuses"]
    log(logger, logging.INFO, "seed complete", product_id=product.id, statuses=statuses)
    print(f"seeded: product={product.id} statuses={statuses}")
    return 0


def main(argv: list[str]) -> int:
    set_trace_id(None)
    task = argv[1] if len(argv) > 1 else "seed"
    if task == "seed":
        return seed()
    log(logger, logging.ERROR, "unknown task", task=task)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
