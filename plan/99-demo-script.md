# ReguLens — Demo Script

One product. One market. One regulatory change. Everything else is cut.

**Target runtime:** 3 minutes 10 seconds — the submission video is ~4 minutes and
must also prove the backend runs on Google Cloud (see the segment at the end).
Live in-person delivery can use the full 3m30s.

## Pre-demo state (from `POST /admin/seed`)

- Product: Herbal Drink Powder — ginger, turmeric, honey powder,
  sodium benzoate 0.08%, 250g pouch, origin Indonesia.
- Markets: Indonesia, Germany.
- Ingested: BPOM regulation, sodium benzoate ≤ 0.10%, active.
- Indonesia status: `compliant`.
- Germany status: `unknown` — no EU data ingested yet.
- The EU regulation PDF is on the desktop, **not yet uploaded**.

## Rehearsal tracker

- [ ] Beats walked through once on the deployed environment
- [ ] Run 1 clean, unassisted
- [ ] Run 2 clean, unassisted
- [ ] Run 3 clean, unassisted (phase 7 exit criterion)
- [ ] Timed under 3m10s for the video cut
- [ ] Google Cloud proof segment (beat 9) recorded
- [ ] Full fallback recording captured
- [ ] Each failure-path response practised at least once

## Beats

### 1 · The twin (25s)
Open the product page. Show the compliance twin: ingredients with real amounts,
packaging, origin, destination.

> "This isn't a document the system read. This is a structured model of an actual
> product — and the system keeps an opinion about it."

Indonesia: compliant. Germany: no data.

### 2 · The upload (20s)
Upload the EU food additives regulation. Select source type: **Official
Regulation** — point at the tier selector.

> "How authoritative a source is changes what the system is willing to do with it.
> An official regulation can rewrite state. A forwarded WhatsApp message cannot."

### 3 · The pipeline, live (35s)
The stepper advances through real states: Extracting → Extracted → Reconciling.
Show the extracted clause: substance, limit 0.05, unit, jurisdiction, effective
date, confidence 0.94 — hover to show the confidence breakdown.

> "That confidence isn't the model's self-assessment. It's parse quality,
> agreement across two extractions, and source authority."

### 4 · The reconciliation (30s)
Show the reconciliation panel. Two findings:

- vs. the BPOM clause → **cross-jurisdiction conflict** (both remain true; the
  stricter one binds the export).
- rejected comparisons, with the guardrail's reason.

> "The guardrail is ordinary code. It decides whether two clauses may even be
> compared. The model only gets called on pairs that pass — and the model never
> writes to the database."

### 5 · The flip (30s)
Return to the dashboard. **Without asking anything**, the alert is there:

```
⚠  Herbal Drink Powder — Germany
    compliant  →  NON-COMPLIANT
    sodium benzoate 0.08% exceeds EU limit 0.05%
```

> "Nobody queried it. A document arrived, the graph changed, and the system worked
> out on its own which product that broke."

Show the impact chain: regulation → clause → requirement → product → Germany →
high risk.

### 6 · The timeline (25s)
Open the timeline. Scroll the event log to the transition:

```
BEFORE  0.10%        AFTER  0.05%
        compliant  →  non-compliant
```

> "Every state change is an immutable event. This is the audit trail — you can
> show a regulator exactly when your compliance status changed and which document
> caused it."

### 7 · The question (35s)
Ask: **"Why is my product at risk?"**

Answer returns with the cause, and the evidence section shows both cited clauses
with their source documents and confidence.

> "Every claim traces to a stored clause. If it hasn't ingested the data, it says
> so — it will not answer a compliance question from a language model's memory."

Optionally ask about a market with no data to show the honest refusal.

### 8 · The close (20s)

> "ReguLens keeps a living compliance twin of a product. When regulations change,
> it reconciles them against what it already knew, traces the impact, and tells the
> exporter what broke, why, and with what evidence.
>
> Deterministic code owns every mutation. The model reasons; it never decides."

### 9 · Google Cloud proof — video only (40s)

Required by the rules: the video must prove the backend runs on Google Cloud.
Record this as a screen capture and cut it in after beat 5.

- Cloud Run console: the API service and the worker service, both healthy, with
  request counts moving during the demo run.
- Pub/Sub console: the `document.uploaded` subscription showing delivery, and the
  dead-letter topic sitting empty.
- Firestore console: the clause document appearing, and the requirement's
  `limit_value` changing `0.10 → 0.05`.
- Cloud Run Jobs: the `seed` job listed.

> "Nothing here is mocked. The pipeline is Pub/Sub-driven across two Cloud Run
> services, and every state change you saw in the UI is a Firestore document
> written by a worker."

## What to say if something fails

- **Extraction stalls:** cut to the pre-ingested state — "we've cached this run;
  here's the result" — and continue from beat 4. The cache is real, not a trick.
- **Query is slow:** keep talking through the evidence panel; it renders before
  the prose.
- **Anything hard-fails:** switch to the recorded run from phase 6 and narrate it.

## Questions to expect, and the honest answers

| Question | Answer |
|---|---|
| "Does it handle scanned documents?" | OCR fallback exists; quality drops and confidence reflects that. Screenshot ingestion is not in this build. |
| "What if extraction is wrong?" | Below 0.5 confidence it goes to `needs_review` and mutates nothing. Wrong-but-confident extraction is the real risk and is why we measure against a labelled fixture set. |
| "What's the 26% you're not showing?" | We only evaluate numeric limits automatically. Labeling, certification, and documentation clauses are surfaced and marked unverified. We don't claim checks we don't run. |
| "Is this a knowledge graph?" | It's an entity-and-event store in Firestore with explicit relations. The value is the state machine and audit log, not graph query expressiveness. |
| "Does it monitor continuously?" | Not in this build — propagation is triggered by ingestion. A crawler is the obvious next step and a separate set of problems. |
| "Why four agents? Do they all reason?" | No, and we say so. Query genuinely selects tools. Reconciliation is guardrail-gated with one judge call. Extraction is a fixed pipeline. Impact contains no model call at all — comparing 0.08 to 0.05 is arithmetic, and a model there would be strictly worse. |
| "Why Pub/Sub for one upload?" | Per-stage retry granularity. One malformed clause fails its own message and retries on its own backoff without re-running extraction for the whole document. Dead-letter surfaces it as a retryable failure in the UI. |
| "Why not just RAG over the PDFs?" | RAG answers questions about documents. This maintains state about a product and notices when that state breaks — without being asked. |
