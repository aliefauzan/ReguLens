# Phase 2 — Ingestion & Extraction Agent

**Estimate:** 2 days (Aug 22–23)
**Demo sentence:** "I uploaded a regulation PDF and it became six structured, sourced, confidence-scored clauses."

**Status:** `NOT STARTED` · **Started:** — · **Completed:** —

<!-- MAINTAIN THIS FILE.
     Set Status to IN PROGRESS when you begin, COMPLETE when every exit criterion
     is ticked. Fill the dates. Tick each `- [ ]` as it lands — a ticked box means
     it exists in the repo and is deployed, not that it is written down somewhere.
     If you deliberately skip an item, change it to `- [~]` and add ` — SKIPPED:
     reason` on the same line so nobody re-litigates it later.
     Then update ../PROGRESS.md. -->

## Goal

Turn a document into `clauses` that downstream deterministic code can actually
compare. Extraction quality is the ceiling on everything after it.

## Build the evaluation before the extractor

Do this first, on day one of the phase:

- [x] Collect 3–5 **real** regulatory source documents (EU additives regulation
      pages, a BPOM regulation) covering the demo substances. Five PDFs are in
      `data/regulations/`, catalogued with sources, CELEX ids and checksums in
      `data/regulations/SOURCES.md`. All have text layers. The two consolidated
      EU versions (2026-02-18 / 2026-08-18) are a genuine before/after pair.
      Still missing from the ideal fixture spread: a short, differently-laid-out
      document — the current five are all long official gazette-style texts.
- [ ] Hand-label a fixture set of ~10 expected clauses:
      `(substance, limit_value, unit, product_type, jurisdiction, effective_date)`.
- [ ] Write `tests/test_extraction_quality.py` that runs the extractor over the
      fixtures and reports per-field accuracy.

Target from the PRD: ≥ 8 of 10 clauses correct on substance + limit + unit +
jurisdiction. Do not proceed to phase 3 below that number — a reconciliation engine
fed by bad extraction produces confident nonsense.

## Scope

### Upload
- [ ] `POST /documents`: multipart file + `source_type`, `source_name`,
      `jurisdiction`, `declared_effective_date`.
- [ ] Reject > 100 pages and > 20 MB with a clear message.
- [ ] Compute `content_sha256`; if a reconciled document with the same hash exists,
      return it instead of re-processing (the rehearsal cache).
- [ ] Write to GCS, create the `documents` record, **publish `document.uploaded`**,
      return `202 {document_id}`. The API service does no extraction work.
- [ ] Also accept pasted text (`POST /documents` with a `text` field) — this is the
      path for the "messy source" use case and costs almost nothing to support.

### Text extraction
- [ ] `pdfplumber` for the text layer.
- [ ] If the text layer is empty or near-empty, fall back to OCR
      (Cloud Vision, or `pytesseract` locally). Record which path was used —
      it feeds `parse_quality`.
- [ ] Compute `parse_quality` deterministically: characters per page, OCR-fallback
      penalty, proportion of non-decodable characters.

### Gemma pre-filter (long documents) — OPTIONAL BONUS
The rules list Gemma as a bonus, not a requirement. Build it if phase 2 is on
schedule; **cut it first if not**. Nothing downstream depends on it.

- [ ] Only for documents above a section threshold (~15 pages).
- [ ] Chunk by page or heading; ask Gemma per chunk: does this chunk state a
      substance limit, a labeling rule, a documentation rule, or a certification
      rule? Return a yes/no plus the matched category.
- [ ] Pass only the selected chunks to Gemini.
- [ ] Log tokens saved — this is a real justification for Gemma's presence, and a
      good slide.

### Gemini extraction — ADK Extraction Agent
- [ ] Implement as an ADK agent with tools `extract_text`, `prefilter_sections`,
      `emit_clause_candidates`. Every tool body is a plain function in
      `core/extraction/`, importable and testable without ADK.
- [ ] Use the pinned Gemini 3.5+ model from phase 0.
- [ ] Prompt returns a JSON array of clause candidates matching a Pydantic schema.
      Use structured/JSON output mode; do not parse prose.
- [ ] **Two samples** at low temperature for `self_consistency`.
- [ ] Validate every candidate against `ClauseCandidate`; drop invalid ones and log
      them. A malformed model response must never reach Firestore.
- [ ] Normalize substance (reuse the phase-1 dictionary) and unit. A clause whose
      unit cannot be normalized is stored with `clause_type: other` and
      `needs_review`, not discarded.
- [ ] Compute composite confidence per `01-architecture.md`.
- [ ] Persist clauses with `status: pending_reconciliation`, then **publish one
      `clause.extracted` message per clause**. Phase 3 consumes these; until then
      the reconcile handler is a no-op that acks.

### Pipeline mechanics (Pub/Sub)
- [ ] `/internal/extract` consumes `document.uploaded` from the push subscription.
- [ ] **Idempotency:** the handler checks `documents.status` first. If the document
      is already past `extracted`, ack and return. Pub/Sub is at-least-once and
      *will* redeliver — a duplicate must not produce duplicate clauses.
- [ ] Each stage updates `documents.status` and appends to `stage_log`.
- [ ] **Nack only on transient errors** (quota, timeout, 5xx from Vertex). Malformed
      input acks and records `failed` — nacking a permanent error burns five retries
      and hides the failure for minutes.
- [ ] Dead-letter delivery sets the document to `failed` with the stage recorded.
- [ ] `POST /documents/{id}/retry` republishes `document.uploaded`.
- [ ] Clauses are written in one batch at the end of extraction — never a
      half-written clause set.

### Debug view — see `../04-observability.md`
- [ ] `GET /debug/documents/{id}` and a page behind an env flag: `trace_id` with a
      Cloud Logging deep link, full `stage_log` with timings, every extracted
      candidate **including rejected ones and why**, confidence breakdown, raw model
      responses truncated.
- [ ] Log `extraction_candidates`, `candidate_rejected`, and `confidence_computed`
      as structured events.
- [ ] Log every Vertex call: model, stage, token counts, latency, prompt hash.

This pays for itself inside phase 3 and doubles as a strong thing to show a
technical judge — it demonstrates the "code gates the model" claim instead of
asserting it.

### Web
- [ ] Add `data-testid` attributes as you build. Phase 6 writes E2E specs against
      them, and retrofitting selectors wastes that day.
- [ ] Upload page with the source metadata form — **the source type selector is a
      product feature, not a form field**: it drives authority tier, so label it as
      "How authoritative is this source?" with the tiers visible.
- [ ] Processing stepper polling `GET /documents/{id}`, rendering real states:
      `Uploaded → Extracting → Extracted → Reconciling → Updated`.
- [ ] Clause list view: text snippet, substance, limit, jurisdiction, effective
      date, confidence, source document link.
- [ ] Confidence rendered with its breakdown on hover — showing *why* the score is
      what it is is more convincing than the number.

## Exit criteria

- [ ] Fixture accuracy ≥ 8/10 on the four key fields, measured by a checked-in test.
- [ ] Uploading the EU regulation PDF produces the expected sodium benzoate clause
      with `limit_value: 0.05`, `unit: percent_w_w`, `jurisdiction: EU`.
- [ ] Uploading a low-authority pasted announcement produces a clause with low
      confidence and `needs_review` — **not** a confident clause.
- [ ] Re-uploading the identical file returns instantly without a second Gemini call.
- [ ] Redelivering the same `document.uploaded` message produces **no duplicate
      clauses** — tested explicitly, not assumed.
- [ ] A forced extraction failure exhausts retries, lands in the DLQ, and shows the
      document as `failed` with a retry button that works.
- [ ] Extraction runs as an ADK agent on the deployed worker.
- [ ] Deployed.

## Out of scope

Screenshot ingestion (stretch only if OCR is already working), chat-export
parsing, URL fetching, multi-language extraction beyond Indonesian and English,
table-structure extraction (if the demo clause lives in a table, pick a different
demo clause).

## Risk notes

- **Real regulatory PDFs are hostile**: multi-column layouts, limits inside large
  tables, and cross-references ("as amended by Annex II"). Choose demo documents
  where the clause is in prose or a simple table. This is a legitimate MVP
  narrowing, but say so honestly rather than implying general capability.
- Two-sample extraction doubles LLM cost. At demo volume this is trivial; note it
  as a known scaling cost rather than optimizing now.
- Gemma is bonus-only. If it is fighting you at hour three, delete it and move on —
  it is worth a mention in the submission, not a day of the schedule.
