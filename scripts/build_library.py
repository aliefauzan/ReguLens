#!/usr/bin/env python3
"""Build the bundled rule library from the real corpus.

Why this exists: a new workspace used to know nothing, so the first thing the app
asked a user to do was go and find a regulation PDF. The library answers that for
them — a set of verbatim excerpts from the two regulations already in the repo,
ingested through the ordinary pipeline like any other upload.

Nothing here paraphrases, summarises or re-numbers a limit. Each entry is a
literal slice of a source document carried with the citation that lets a reader
check it.

  EU     data/regulations/eu/EU-reg-1333-2008-consolidated-20260818.eurlex.md
         The Annex II Union list as published in HTML by EUR-Lex (CELEX
         02008R1333-20260818), converted to markdown. HTML rather than the PDF
         because the PDF's columns come out of a text dump unaligned, and an
         unaligned row pairs a category with the wrong number. Re-fetch with:
           firecrawl scrape "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02008R1333-20260818"

  BPOM   data/regulations/bpom/BPOM-perka-11-2019-bahan-tambahan-pangan.pdf
         Read with pdfplumber, which keeps each table row on one line — category
         number, category name and maximum level together.

Run:  docker compose run --rm -v "$PWD:/repo" --no-deps api python /repo/scripts/build_library.py
Out:  api/app/core/library_data.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EU_MD = ROOT / "data/regulations/eu/EU-reg-1333-2008-consolidated-20260818.eurlex.md"
BPOM_PDF = ROOT / "data/regulations/bpom/BPOM-perka-11-2019-bahan-tambahan-pangan.pdf"
OUT = ROOT / "api/app/core/library_data.json"

# An excerpt has to be small enough to read in one extraction pass and large
# enough to be worth reading. Rows past the cap are dropped and the entry says
# so, rather than implying the excerpt is the whole category.
MAX_CHARS = 7000

EU_CITATION = (
    "Consolidated Regulation (EC) No 1333/2008, Annex II Part E, "
    "version in force from 18 August 2026 (CELEX 02008R1333-20260818)"
)
BPOM_CITATION = (
    "Peraturan Badan POM No. 11 Tahun 2019 tentang Bahan Tambahan Pangan, Lampiran"
)

# EU: the Annex II food categories worth carrying, with words a non-specialist
# would use and the product kinds they bear on.
EU_CATEGORIES: list[tuple[str, str, str, list[str]]] = [
    (
        "14.1.4",
        "Flavoured drinks",
        "Fizzy and still flavoured drinks, sports and energy drinks.",
        ["food_beverage_liquid", "food_beverage_powder"],
    ),
    (
        "14.1.2",
        "Fruit and vegetable juices",
        "Juices as defined by Directive 2001/112/EC.",
        ["food_beverage_liquid"],
    ),
    ("14.1.3", "Fruit and vegetable nectars", "Nectars, including concentrates.", ["food_beverage_liquid"]),
    (
        "14.1.5.2",
        "Tea, herbal infusions and cereal drinks",
        "Everything in 14.1.5 that is not coffee.",
        ["food_beverage_liquid", "food_beverage_powder"],
    ),
    ("01.4", "Flavoured fermented milk products", "Drinking yoghurt and similar.", ["food_beverage_liquid"]),
    ("04.2.5.2", "Jam, jellies and marmalades", "Standard jams and fruit spreads.", ["food_solid"]),
    ("06.3", "Breakfast cereals", "Cereals and rolled oats.", ["food_solid"]),
    ("07.2", "Fine bakery wares", "Cakes, biscuits and pastries.", ["food_solid"]),
    ("12.6", "Sauces", "Table and cooking sauces.", ["food_solid"]),
    ("15.1", "Savoury snacks", "Potato, cereal, flour or starch based snacks.", ["food_solid"]),
    ("17.1", "Food supplements in solid form", "Tablets, capsules and powders.", ["supplement"]),
    ("17.2", "Food supplements in liquid form", "Drops and liquid supplements.", ["supplement"]),
]

# BPOM: the additive sections worth carrying, keyed by the page each section
# starts on (0-based, as pdfplumber counts them).
BPOM_SUBSTANCES: list[tuple[int, str, str, str, list[str]]] = [
    (
        766,
        "Natrium benzoat (Sodium benzoate)",
        "INS 211",
        "Preservative. The Indonesian counterpart to the EU's E 211.",
        ["food_beverage_liquid", "food_beverage_powder", "food_solid"],
    ),
    (94, "Asam benzoat (Benzoic acid)", "INS 210", "Preservative.", ["food_beverage_liquid", "food_solid"]),
    (124, "Asam sorbat (Sorbic acid)", "INS 200", "Preservative.", ["food_beverage_liquid", "food_solid"]),
    (
        499,
        "Kalium sorbat (Potassium sorbate)",
        "INS 202",
        "Preservative.",
        ["food_beverage_liquid", "food_solid"],
    ),
    (
        140,
        "Belerang dioksida (Sulphur dioxide)",
        "INS 220",
        "Preservative and antioxidant.",
        ["food_beverage_liquid", "food_solid"],
    ),
    (
        137,
        "Aspartam (Aspartame)",
        "INS 951",
        "Sweetener.",
        ["food_beverage_liquid", "food_beverage_powder", "food_solid"],
    ),
    (
        130,
        "Asesulfam-K (Acesulfame potassium)",
        "INS 950",
        "Sweetener.",
        ["food_beverage_liquid", "food_beverage_powder"],
    ),
    (
        845,
        "Natrium sakarin (Sodium saccharin)",
        "INS 954(iv)",
        "Sweetener.",
        ["food_beverage_liquid", "food_solid"],
    ),
    (
        846,
        "Natrium siklamat (Sodium cyclamate)",
        "INS 952(iv)",
        "Sweetener. Permitted in Indonesia; not permitted in the EU.",
        ["food_beverage_liquid", "food_solid"],
    ),
    (
        296,
        "Glikosida steviol (Steviol glycosides)",
        "INS 960",
        "Sweetener.",
        ["food_beverage_liquid", "food_beverage_powder"],
    ),
    (996, "Sukralosa (Sucralose)", "INS 955", "Sweetener.", ["food_beverage_liquid", "food_solid"]),
    (1001, "Tartrazin (Tartrazine)", "INS 102", "Yellow colour.", ["food_beverage_liquid", "food_solid"]),
    (
        661,
        "Kuning FCF (Sunset yellow FCF)",
        "INS 110",
        "Orange-yellow colour.",
        ["food_beverage_liquid", "food_solid"],
    ),
    (937, "Ponceau 4R (Cochineal red A)", "INS 124", "Red colour.", ["food_beverage_liquid", "food_solid"]),
    (646, "Karmin (Carmines)", "INS 120", "Red colour.", ["food_beverage_liquid", "food_solid"]),
    (158, "Butil hidroksianisol / BHA", "INS 320", "Antioxidant.", ["food_solid"]),
]


def eu_blocks() -> dict[str, list[str]]:
    """Every Annex II category block, keyed by category number.

    The Union list is one long table: a row holding only a category number and
    its name opens a block, and every row after it belongs to that category
    until the next such row.
    """
    lines = EU_MD.read_text().split("\n")
    header = re.compile(r"^\|\s*(\d{1,2}(?:\.\d+)*)\s*\|\s*([^|]{3,200}?)\s*\|\s*$")
    starts = [(i, m.group(1)) for i, line in enumerate(lines) if (m := header.match(line))]
    blocks: dict[str, list[str]] = {}
    for position, (start, number) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        body = [
            line
            for line in lines[start:end]
            # EUR-Lex marks each amendment with a ▼M link row. It is apparatus,
            # not regulation text, and it makes the excerpt unreadable.
            if line.strip() and not line.strip().startswith("| [▼") and "————" not in line
        ]
        # The same numbers appear twice: Part D is a bare index with nothing
        # under it, Part E carries the limits. Keep whichever block actually has
        # additive rows, which is always Part E.
        if len(body) > len(blocks.get(number, [])):
            blocks[number] = body
    return blocks


def bpom_sections() -> dict[int, list[str]]:
    """Each additive section of the annex, keyed by its starting page."""
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(BPOM_PDF) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")

    # One flat stream of lines, remembering which page each came from, because a
    # section can start halfway down a page and run over several more.
    stream: list[tuple[int, str]] = []
    for index, text in enumerate(pages):
        for line in text.split("\n"):
            line = line.strip()
            # Page numbers ("-767-") are the printer's, not the rule's.
            if not line or re.fullmatch(r"-\s*\d+\s*-", line):
                continue
            stream.append((index, line))

    # A section opens with the substance name, then "INS : <number>".
    starts = [
        position
        for position, (_, line) in enumerate(stream)
        if position > 0 and re.match(r"^INS\s*:\s*", line)
    ]
    sections: dict[int, list[str]] = {}
    for order, position in enumerate(starts):
        begin = position - 1  # the substance's own name
        end = starts[order + 1] - 1 if order + 1 < len(starts) else len(stream)
        page = stream[begin][0]
        sections[page] = [line for _, line in stream[begin:end]]
    return sections


def clip(body: list[str], header: str) -> tuple[str, bool]:
    """Join rows up to the cap. Returns the text and whether it was cut short."""
    kept: list[str] = []
    total = len(header)
    for line in body:
        if total + len(line) + 1 > MAX_CHARS:
            return header + "\n" + "\n".join(kept), True
        kept.append(line)
        total += len(line) + 1
    return header + "\n" + "\n".join(kept), False


def main() -> int:
    if not EU_MD.exists():
        print(f"missing {EU_MD}", file=sys.stderr)
        return 1

    entries: list[dict] = []

    blocks = eu_blocks()
    for number, name, summary, product_types in EU_CATEGORIES:
        body = blocks.get(number)
        if not body:
            print(f"EU category {number} not found — skipped", file=sys.stderr)
            continue
        header = (
            f"Regulation (EC) No 1333/2008, Annex II Part E — Food category {number}: {name}.\n"
            "Maximum level (mg/l or mg/kg as appropriate). "
            "Columns: E number | name | maximum level | footnotes | restrictions."
        )
        text, truncated = clip(body, header)
        entries.append(
            {
                "id": f"eu_annex_ii_{number.replace('.', '_')}",
                "jurisdiction": "EU",
                "source_type": "official_regulation",
                "source_name": f"EU Annex II — {number} {name}",
                "title": f"{name} (EU)",
                "summary": summary,
                "citation": f"{EU_CITATION}, food category {number}",
                "product_types": product_types,
                "truncated": truncated,
                "text": text,
            }
        )

    sections = bpom_sections()
    for page, name, ins, summary, product_types in BPOM_SUBSTANCES:
        body = sections.get(page)
        if not body:
            print(f"BPOM section on page {page} not found — skipped", file=sys.stderr)
            continue
        header = (
            "Peraturan Badan POM Nomor 11 Tahun 2019 tentang Bahan Tambahan Pangan — "
            f"{name}, {ins}.\n"
            "Tabel: Nomor Kategori Pangan | Nama Kategori Pangan | Batas Maksimal (mg/kg). "
            "CPPB = Cara Produksi Pangan yang Baik (no numeric maximum; good manufacturing practice)."
        )
        text, truncated = clip(body, header)
        entries.append(
            {
                "id": f"bpom_11_2019_p{page}",
                "jurisdiction": "ID_BPOM",
                "source_type": "official_regulation",
                "source_name": f"BPOM 11/2019 — {name}",
                "title": f"{name} ({ins}) — Indonesia",
                "summary": summary,
                "citation": f"{BPOM_CITATION}, page {page + 1}",
                "product_types": product_types,
                "truncated": truncated,
                "text": text,
            }
        )

    OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(entries)} entries -> {OUT}")
    for entry in entries:
        print(f"  {entry['id']:24} {len(entry['text']):6} chars  truncated={entry['truncated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
