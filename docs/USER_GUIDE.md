# Using the ReguLens Web App

Live environment:

| Service | URL |
|---|---|
| Web app | https://regulens-web-babuvy7w3a-as.a.run.app |
| API | https://regulens-api-babuvy7w3a-as.a.run.app |

Everything below runs against the deployed Cloud Run stack. No login exists by
design — the MVP has a single hardcoded workspace.

## The 5-minute walkthrough

### 1. Create the product (the compliance twin)

Open the web app. Click **New product**. Fill in:

- Name: `Herbal Drink Powder`
- Product type: `food beverage powder`
- Origin: `ID`
- Destination markets: tick **Germany (EU)** and **Indonesia (BPOM)**
- Ingredients: add `ginger`, `turmeric`, `honey powder`, and
  `sodium benzoate` with amount `300` unit `mg_per_kg`

Click **Create product**. The detail page shows the twin. Note that Indonesia
has **no readiness figure yet** — nothing has been evaluated, and the app says
so instead of showing a fake percentage.

### 2. Ingest the Indonesian baseline (paste text)

Click **Ingest** in the top nav. Fill the form:

- **How authoritative is this source?** → `Official regulation` (tier 1.0)
- Source name: `BPOM Perka 11/2019`
- Jurisdiction: `Indonesia (BPOM)`
- Leave the file input empty; paste this into the text box:

```
Peraturan Badan POM Nomor 11 Tahun 2019 tentang Bahan Tambahan Pangan.
Natrium benzoat (Sodium benzoate), INS: 211. Golongan: Pengawet.
Nomor Kategori Pangan 14.1.4.1 Minuman Berbasis Air Berperisa yang Berkarbonat:
Batas Maksimal (mg/kg) dihitung sebagai asam benzoat: 400.
```

Submit. The stepper advances `Uploaded → Extracting → Extracted`.

### 3. Watch Indonesia turn compliant

Return to the product page. Within a minute the readiness panel shows:

- Indonesia: **Compliant** — `✓ sodium_benzoate limit 400 mg/kg, product 300`
- Germany: **No regulatory data**

The audit trail at the bottom lists every event with its trace id.

### 4. The inflection: upload the EU regulation (PDF)

Click **Ingest** again. This time:

- Authority: `Official regulation`, source name `European Commission`,
  jurisdiction `EU`
- Choose the file:
  `data/regulations/excerpts/EU-annex-II-14.1.4-flavoured-drinks-excerpt.pdf`
  (a real 4-page excerpt of Annex II of Commission Regulation (EU) 1129/2011,
  committed in this repo)

Submit and watch the stepper. When it reaches Extracted, do nothing else.

### 5. The unprompted flip (the point of the whole system)

Stay on the product page. Within ~1-3 minutes, **without asking anything**:

- An alert banner appears: `Non-compliant — market_de ← clause_… ← ingested
  document (unknown → non_compliant)`
- Germany flips to a red **Non-compliant** badge with the failing requirement:
  product 300 mg/kg vs EU limit 150 mg/kg

Nobody queried the system. A document arrived, the knowledge graph changed,
and the impact engine worked out on its own which product broke.

### 6. Inspect the conflict

Open **Conflicts** in the nav. You will see
`cross jurisdiction limit mismatch` with both clauses side by side:
EU 150 mg/kg vs BPOM 400 mg/kg. Both clauses stay active — neither supersedes
the other; the stricter one binds an export.

### 7. Ask questions with evidence

On the product page, use the **Ask** panel. Suggested buttons are provided:

- "Why is my product at risk?" — cites the EU and BPOM clauses
- "What changed in the EU regulation?" — cites the conflict + clause history
- "Can I export to Germany?" — NOT READY with cited requirements
- Ask about Japan — the system **refuses**: no data ingested, no invented answer

Every answer shows a confidence value (the minimum confidence of its citations)
and an evidence list of the exact clause cards used.

### 8. Review queue (authority gating in action)

Open **Review queue**. Clauses from low-authority sources land here with
`needs_review` instead of mutating state. Try it: ingest a pasted announcement
with authority `Social / chat` (tier 0.2) — its clause appears in the queue at
low confidence and **nothing else changes**. Confirming a row promotes it to
active.

## Resetting to the demo baseline

```bash
gcloud run jobs execute regulens-job --region asia-southeast1 --project regulens-506014 --wait
```

Idempotent: markets seeded, demo product at 300 mg/kg, BPOM 400 mg/kg clause
ingested and reconciled. Germany stays `unknown` — the EU upload is the demo's
inflection point. Re-uploading the same EU PDF never re-bills Gemini (the
sha256 rehearsal cache returns the stored result).

## What to do next (owner checklist)

- [ ] **Register on Devpost** and join the hackathon — blocks submission
- [ ] Click Google's budget-alert verification email (afindo.mi01@gmail.com)
- [ ] Record the ~4-minute video (include Cloud Run / Pub/Sub / Firestore proof segment)
- [ ] Architecture diagram image for Devpost
- [ ] Wire Cloud Build push/PR triggers (needs GitHub-app OAuth in console)
- [ ] Rehearse the walkthrough above 3x unassisted on the live URL
- [ ] Optional: start Docker Desktop and try `docker compose up` locally

## Where the debug detail lives

`GET /debug/documents/{id}` (enabled in this deployment) shows stage timings,
rejected candidates with reasons, per-pair guardrail decisions, judge verdicts,
and confidence components. Use it when a document extracts strangely.
