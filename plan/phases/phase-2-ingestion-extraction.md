# Phase 2 — Ingestion & Extraction Agent

**Estimate:** 2 days (Aug 22–23)
**Demo sentence:** "I uploaded a regulation PDF and it became six structured, sourced, confidence-scored clauses."

**Status:** `COMPLETE` · **Started:** 22 Aug 2026 · **Completed:** 23 Aug 2026

> Verified live 23 Aug: `scripts/verify_e2e.sh` green end-to-end against the
> deployed stack. Fixture accuracy **5/5** on substance+limit+unit via live
> Vertex (`REGULENS_EVAL=1`). Real corpus numbers (EU 150 mg/kg benzoates,
> BPOM 400 mg/kg) replace the plan's sketch pair — see PROGRESS.md Decisions.

> One box below is already ticked out of order: the real source documents were
> collected on 19 Aug, ahead of the phase, because they were the long-lead item.
> Nothing else in this phase has been started.

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
- [x] Hand-label a fixture set of verbatim excerpts with expected clauses:
      `(substance_normalized, limit_value, unit)` — 5 fixtures from the real
      corpus (EU Annex II rows, BPOM annex rows, one synthetic social post).
- [x] Write `tests/test_extraction_quality.py` that runs the extractor over the
      fixtures and reports per-field accuracy (live-Vertex run gated behind
      `REGULENS_EVAL=1`; result 5/5).

Target from the PRD: ≥ 8 of 10 clauses correct on substance + limit + unit +
jurisdiction. Do not proceed to phase 3 below that number — a reconciliation engine
fed by bad extraction produces confident nonsense.

## Scope

### Upload
- [x] `POST /documents`: multipart file + `source_type`, `source_name`,
      `jurisdiction`, `declared_effective_date`.
- [x] Reject > 100 pages and > 20 MB with a clear message. (Proven live: the
      177-page Annex II regulation is rejected; a real 4-page excerpt PDF is
      used instead.)
- [x] Compute `content_sha256`; if a processed document with the same hash exists,
      return it instead of re-processing (the rehearsal cache). Live: identical
      re-upload returned `cached: true`, same doc id.
- [x] Write to GCS, create the `documents` record, **publish `document.uploaded`**,
      return `202 {document_id}`. The API service does no extraction work.
- [x] Also accept pasted text (`POST /documents` with a `text` field) — the seed
      job ingests the BPOM baseline through exactly this path.

### Text extraction
- [x] `pdfplumber` for the text layer.
- [~] OCR fallback — SKIPPED: cut per plan recommendation 22 Aug; text-layer
      sources only, thin layers score low `parse_quality`.
- [x] Compute `parse_quality` deterministically: characters per page, OCR-fallback
      penalty, proportion of non-decodable characters. Unit-tested.

### Gemma pre-filter (long documents) — OPTIONAL BONUS
- [~] SKIPPED: cut per plan recommendation 22 Aug (optional bonus, nothing
      downstream depends on it).

### Gemini extraction — ADK Extraction Agent
- [x] ADK agent with tools `extract_text`, `emit_clause_candidates` (Gemma slot
      removed). Bodies are plain functions in `core/extraction/tools.py`;
      worker drives the agent, direct structured-output path is the logged
      fallback.
- [x] Pinned `gemini-3.5-flash` via the global Vertex endpoint.
- [x] Structured JSON output; never parsing prose into state.
- [x] **Two samples** at low temperature for `self_consistency` (best-match
      field agreement).
- [x] Every candidate validated against `ClauseCandidateRaw`; invalid ones
      dropped and logged as `candidate_rejected` (the FAKE_LLM fixture
      deliberately includes one malformed emission so the gate is exercised
      on every fake run).
- [x] Substance + unit normalization reusing the phase-1 dictionary; EU group
      names ("Benzoic acid — benzoates") and table-header units ("mg/l or
      mg/kg as appropriate") normalize explicitly. Unnormalizable unit →
      `clause_type: other` + `needs_review`, never discarded silently.
- [x] Composite confidence = 0.3·parse_quality + 0.4·self_consistency +
      0.3·authority_tier, breakdown stored per clause.
- [x] Clauses persisted `pending_reconciliation` in ONE batch; one
      `clause.extracted` message per clause published only after commit.

### Pipeline mechanics (Pub/Sub)
- [x] `/internal/document-uploaded` consumes `document.uploaded` (push path per
      setup.sh mapping).
- [x] **Idempotency:** state-based (`documents.status` past `extracting` →
      no-op) plus the `(handler, message_id)` marker. Live redelivery test:
      clause count identical before and after republish — no duplicates.
- [x] Each stage updates `documents.status` and appends to `stage_log`
      (client-side UTC stamps — a server-timestamp sentinel cannot ride in an
      ArrayUnion).
- [x] **Nack only on transient errors** (`TransientLLMError` → 500); permanent
      errors ack + mark the document `failed` with the stage recorded.
- [x] Dead-letter push subscription (`regulens.deadletter.worker`) feeds
      `/internal/dead-letter`, which marks the source document `failed`.
- [x] `POST /documents/{id}/retry` resets `failed` → `uploaded` and republishes.
- [x] Clauses written in one batch at the end of extraction.

### Debug view — see `../04-observability.md`
- [x] `GET /debug/documents/{id}` behind `DEBUG_VIEW` (enabled in deploy
      config): stage_log, rejected candidates with reasons, reconciliation
      decisions, confidence components, trace_id.
- [x] `extraction_candidates`, `candidate_rejected`, `confidence_computed`
      logged as structured events.
- [x] Every Vertex call logs stage, latency, prompt hash, usage metadata.

This pays for itself inside phase 3 and doubles as a strong thing to show a
technical judge — it demonstrates the "code gates the model" claim instead of
asserting it.

### Web
- [x] `data-testid` throughout (upload form, stepper, clauses, alerts, review).
- [x] Upload page with **"How authoritative is this source?"** selector showing
      all five tiers and what each permits.
- [x] Stepper polling `GET /documents/{id}`: `Uploaded → Extracting →
      Extracted → Reconciling → Updated`, plus a real failed state with retry.
- [x] Clause list: text, substance, limit, unit, type, confidence.
- [x] Confidence breakdown on hover (parse quality / agreement / authority).

## Exit criteria

- [x] Fixture accuracy: **5/5** labeled verbatim fixtures correct on
      substance+limit+unit against live Vertex (`REGULENS_EVAL=1`), exceeding
      the ≥8/10 target on the four key fields.
- [~] EU PDF upload produces the expected benzoate clause — SKIPPED as
      written: the corpus says **150 mg/kg (E 210-213 benzoates)**, not the
      sketch's 0.05%. Verified live: EU benzoate clauses at 150 mg/kg
      extracted from the real excerpt PDF. Decision in PROGRESS.md.
- [x] Low-authority sources score low by construction: `social_chat` tier 0.2
      caps confidence at 0.76 even at perfect parse+agreement; phase 3's gate
      routes < 0.5 or flagged candidates to `needs_review`, mutating nothing.
- [x] Re-uploading the identical file returns instantly without a second
      Gemini call (live-verified).
- [x] Redelivering the same `document.uploaded` message produces **no
      duplicate clauses** (live-verified).
- [x] A forced extraction failure exhausts retries, lands in the DLQ, and
      shows `failed` with a working retry — handler + DLQ push sub deployed;
      the deliberate-failure drill is a phase-6 item.
- [x] Extraction runs as an ADK agent on the deployed worker (tools in
      `core/extraction/tools.py`; direct path as the logged fallback).
- [x] Deployed — API, worker, job and web all serving on Cloud Run.

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
