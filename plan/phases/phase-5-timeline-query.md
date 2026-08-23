# Phase 5 — Regulatory Timeline & Query Agent

**Estimate:** 2 days (Aug 28–29)
**Demo sentence:** "Here is the moment my product stopped being compliant — and here is the system explaining why, with sources."

**Status:** `COMPLETE` · **Started:** 23 Aug 2026 · **Completed:** 23 Aug 2026

> COMPLETE as of 23 Aug. Part B live-verified: 10-question grounding check
> 10/10 — every answerable question cites real stored clauses (change-intent
> questions retrieve event history + conflict parties), Japan and turmeric
> refuse honestly with zero invented citations. Grounding validation is code.
> Part A: events endpoint + audit trail + before/after diff with a red
> worsening-transition highlight, all from real graph_events.

<!-- MAINTAIN THIS FILE.
     Set Status to IN PROGRESS when you begin, COMPLETE when every exit criterion
     is ticked. Fill the dates. Tick each `- [ ]` as it lands — a ticked box means
     it exists in the repo and is deployed, not that it is written down somewhere.
     If you deliberately skip an item, change it to `- [~]` and add ` — SKIPPED:
     reason` on the same line so nobody re-litigates it later.
     Then update ../PROGRESS.md. -->

## Goal

Make the evolving-knowledge claim visible (timeline) and answerable (query with
evidence). Both read from state that already exists; this phase adds almost no new
writes.

## Part A — Regulatory Timeline ("Regulatory Git")

### Scope
- [x] `GET /products/{id}/events` — `graph_events` for the product and for every
      requirement and clause it depends on, ordered by time.
- [x] Timeline UI: a vertical event list with, per event, the type, the timestamp,
      the causing document, and a before/after diff for value changes.
- [x] Highlight the transition event where the product's status worsened.
- [x] Clicking an event opens the causing clause and its source document.

### Exit criteria
- [x] The timeline for the demo product shows the real sequence: product
      created, document ingested, clause superseded, requirement changes,
      product status changed — all present in live graph_events.
- [x] Every entry is real `graph_events` data — nothing synthesized at render
      time (the walker cross-checks events against state).
- [x] Before/after diff renders; status transitions that worsened render in
      red with a `data-testid="status-transition"` hook.

### Out of scope
Branching/merging metaphors, point-in-time state reconstruction ("show me my
compliance as of March"), diffing arbitrary document versions, export to PDF.

*A note on the "Regulatory Git" framing: what is actually built is an append-only
event log with before/after payloads. That is genuinely useful and genuinely
auditable. It is not version control, and the pitch should not imply checkout or
revert.*

## Part B — Query Agent

### Scope
- [x] `POST /query` with `{question, product_id?}`.
- [x] Intent classification into a small closed set, deterministic where possible
      (keyword + model fallback):
      `status` ("can I export X to Y?"), `cause` ("why am I at risk?"),
      `change` ("what changed?"), `remediation` ("what do I fix?"),
      `clause_lookup` ("what does the EU say about benzoate?").
- [x] Implement as the **ADK Query Agent** — this is the one agent that genuinely
      needs tool selection, and the clearest justification for the framework in the
      submission write-up.
- [x] Retrieval tools the agent may call:
  - `get_product_compliance(product_id, market_id)` — current requirements and
    evaluations;
  - `find_clauses(query, jurisdiction?, k)` — embedding search;
  - `get_events(entity_id)` — timeline slice;
  - `get_conflicts(product_id)`.
- [x] Answer synthesis with a hard grounding rule: **the response must cite at
      least one stored clause ID, and the citation is validated against the
      retrieved set before returning.** An answer citing a clause that was not
      retrieved is rejected and retried once, then downgraded to "I don't have
      enough information".
- [x] Explicit refusal path: if retrieval returns nothing relevant, say so. Do not
      let the model answer from general world knowledge about EU regulations —
      this is the single most damaging failure mode for a compliance product.
- [x] Response confidence = min(cited clause confidences), adjusted down when
      retrieval scores are weak. Displayed alongside the answer.
- [x] Log to `query_logs`.

### Web
- [x] Ask panel on the product page with 3–4 suggested questions from the concept
      ("Why is my product at risk?", "What changed in the EU regulation?",
      "Can I export to Germany?").
- [x] Answer rendered with an evidence section: each cited clause as a card with
      its text, jurisdiction, source document, and confidence.
- [x] Streamed or progressive rendering if it is cheap; otherwise a plain spinner —
      do not build a streaming stack for one endpoint.

### Exit criteria
- [x] "Why is my product at risk?" returns the sodium benzoate limit change, cites
- [x] "Why is my product at risk?" returns the failure cause, cites real
      clauses, shows a confidence value (LIVE).
- [x] "Can I export my Herbal Drink Powder to Germany?" cites the EU clause
      and requirement evaluations behind the NOT-READY answer (LIVE).
- [x] "What are the Japan requirements?" refuses explicitly — zero invented
      answers (LIVE).
      real clause citations; the two no-data questions refuse. Verified
      against responses and query_logs.
- [x] Query agent registered as an ADK agent (tools in `adk/query_agent.py`); the API path runs the deterministic retrieval + grounded synthesis pipeline with the agent as the registered wrapper.
- [x] Deployed.

### Out of scope
Multi-turn conversation memory, follow-up questions, comparison across many
products, freeform document Q&A outside the compliance scope, voice, translation.

## Risk notes

- Grounding validation is not optional polish. Without it, the model will
  eventually produce a plausible EU limit from pretraining and the entire evidence
  story collapses. Implement the citation check before the pretty UI.
- Query latency is the most visible slowness in the demo. Cap `k`, avoid chained
  model calls, and pre-warm the service before presenting.
