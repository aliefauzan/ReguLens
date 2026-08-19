# Regulation Source Corpus

Retrieved **19 Aug 2026**. All files have a real text layer (verified with
`pdftotext`) — no OCR needed. Nothing here is synthetic.

## EU — `eu/`

| File | What it is | Source | Pages | SHA-256 (short) |
|---|---|---|---|---|
| `EU-reg-1333-2008-food-additives.pdf` | Regulation (EC) No 1333/2008 on food additives, **as originally published** (OJ L 354, 31.12.2008). Framework only; annex lists were empty at adoption. | CELEX `32008R1333` | 18 | `e5c612ae` |
| `EU-reg-1129-2011-annex-II-additives-list.pdf` | Commission Regulation (EU) No 1129/2011 — establishes the **Annex II Union list** of food additives with per-food-category maximum levels. This is where E 210–213 (benzoic acid — benzoates) limits live. | CELEX `32011R1129` | 177 | `abd470f7` |
| `EU-reg-1333-2008-consolidated-2026-02-18.pdf` | Consolidated 1333/2008 including all annexes, version in force 18 Feb 2026 – 17 Aug 2026. **Previous version.** | CELEX `02008R1333-20260218` | 366 | `e5fa1966` |
| `EU-reg-1333-2008-consolidated-2026-08-18.pdf` | Consolidated 1333/2008, version in force **from 18 Aug 2026** — the current text. | CELEX `02008R1333-20260818` | 366 | `f7dc3221` |

URL pattern used:
`https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:<celex-id>`

The two consolidated versions are one day apart in force and differ slightly —
useful as a genuine before/after pair for the "regulation changed" path, instead
of inventing a diff.

## BPOM (Indonesia) — `bpom/`

| File | What it is | Source | Pages | SHA-256 (short) |
|---|---|---|---|---|
| `BPOM-perka-11-2019-bahan-tambahan-pangan.pdf` | Peraturan Badan POM No. 11 Tahun 2019 tentang Bahan Tambahan Pangan. Annexes list every permitted additive with maximum levels per food category (Natrium benzoat / sodium benzoate, INS 211, ADI 0–5 mg/kg bw). | `https://jdih.pom.go.id/download/rule/848/11/2019/Bahan%20Tambahan%20Pangan` (JDIH BPOM, official) | 1156 | `1b9f67b5` |

## Divergence check — sodium benzoate in flavoured drinks

The demo premise holds. Both documents regulate the same substance and give
different numbers:

- **EU**, Annex II category **14.1.4 "Flavoured drinks"**:
  E 210-213 benzoic acid — benzoates = **150 mg/kg** (excluding dairy-based drinks).
- **BPOM**, categories **14.1.4.1 / 14.1.4.2 / 14.1.4.3** (flavoured water-based
  drinks, carbonated / non-carbonated / concentrates): limits in the range
  **400–900 mg/kg**, expressed as benzoic acid, computed on the ready-to-consume
  product. Neighbouring beverage categories (14.1.3.x nectar concentrates) go up
  to 1000 mg/kg.

**Caveat before this goes on a slide:** the BPOM figures above were read from a
`pdftotext` dump, where the category column and the limit column are extracted as
separate runs. Row alignment must be confirmed against the rendered table in the
PDF before any specific number is quoted in the UI or the demo. The *existence*
of a large divergence (hundreds of mg/kg) is not in doubt; the exact per-row
pairing is not yet verified.

Category taxonomies are close but not identical — EU 14.1.4 is one category, BPOM
splits it into 14.1.4.1–14.1.4.3. Whatever maps them will need to handle that.
