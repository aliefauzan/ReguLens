# Phase 5 — Regulatory Timeline & Query Agent

**Estimate:** 2 days (Aug 28–29)
**Demo sentence:** "Here is the moment my product stopped being compliant — and here is the system explaining why, with sources."

**Status:** `NOT STARTED` · **Started:** — · **Completed:** —

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
- [ ] `GET /products/{id}/events` — `graph_events` for the product and for every
      requirement and clause it depends on, ordered by time.
- [ ] Timeline UI: a vertical event list with, per event, the type, the timestamp,
      the causing document, and a before/after diff for value changes.
- [ ] Highlight the transition event where the product's status worsened.
- [ ] Clicking an event opens the causing clause and its source document.

### Exit criteria
- [ ] The timeline for the demo product shows, in order: product created, baseline
      requirement created, document ingested, clause superseded, requirement changed
      `0.10 → 0.05`, product status changed `compliant → non_compliant`.
- [ ] Every entry is real `graph_events` data — nothing synthesized at render time.
- [ ] The before/after diff for the limit change renders correctly.

### Out of scope
Branching/merging metaphors, point-in-time state reconstruction ("show me my
compliance as of March"), diffing arbitrary document versions, export to PDF.

*A note on the "Regulatory Git" framing: what is actually built is an append-only
event log with before/after payloads. That is genuinely useful and genuinely
auditable. It is not version control, and the pitch should not imply checkout or
revert.*

## Part B — Query Agent

### Scope
- [ ] `POST /query` with `{question, product_id?}`.
- [ ] Intent classification into a small closed set, deterministic where possible
      (keyword + model fallback):
      `status` ("can I export X to Y?"), `cause` ("why am I at risk?"),
      `change` ("what changed?"), `remediation` ("what do I fix?"),
      `clause_lookup` ("what does the EU say about benzoate?").
- [ ] Implement as the **ADK Query Agent** — this is the one agent that genuinely
      needs tool selection, and the clearest justification for the framework in the
      submission write-up.
- [ ] Retrieval tools the agent may call:
  - `get_product_compliance(product_id, market_id)` — current requirements and
    evaluations;
  - `find_clauses(query, jurisdiction?, k)` — embedding search;
  - `get_events(entity_id)` — timeline slice;
  - `get_conflicts(product_id)`.
- [ ] Answer synthesis with a hard grounding rule: **the response must cite at
      least one stored clause ID, and the citation is validated against the
      retrieved set before returning.** An answer citing a clause that was not
      retrieved is rejected and retried once, then downgraded to "I don't have
      enough information".
- [ ] Explicit refusal path: if retrieval returns nothing relevant, say so. Do not
      let the model answer from general world knowledge about EU regulations —
      this is the single most damaging failure mode for a compliance product.
- [ ] Response confidence = min(cited clause confidences), adjusted down when
      retrieval scores are weak. Displayed alongside the answer.
- [ ] Log to `query_logs`.

### Web
- [ ] Ask panel on the product page with 3–4 suggested questions from the concept
      ("Why is my product at risk?", "What changed in the EU regulation?",
      "Can I export to Germany?").
- [ ] Answer rendered with an evidence section: each cited clause as a card with
      its text, jurisdiction, source document, and confidence.
- [ ] Streamed or progressive rendering if it is cheap; otherwise a plain spinner —
      do not build a streaming stack for one endpoint.

### Exit criteria
- [ ] "Why is my product at risk?" returns the sodium benzoate limit change, cites
      the EU clause and the product requirement, and shows a confidence value.
- [ ] "Can I export my Herbal Drink Powder to Germany?" returns `NOT READY` with the
      issue list from real requirement evaluations.
- [ ] A question with no supporting data ("what are the Japan requirements?") returns
      an explicit "no data ingested for this market" — not an invented answer.
- [ ] Ten manual questions: 100% cite a real stored clause; verified against
      `query_logs`.
- [ ] Runs as an ADK agent on the deployed API service.
- [ ] Deployed.

### Out of scope
Multi-turn conversation memory, follow-up questions, comparison across many
products, freeform document Q&A outside the compliance scope, voice, translation.

## Risk notes

- Grounding validation is not optional polish. Without it, the model will
  eventually produce a plausible EU limit from pretraining and the entire evidence
  story collapses. Implement the citation check before the pretty UI.
- Query latency is the most visible slowness in the demo. Cap `k`, avoid chained
  model calls, and pre-warm the service before presenting.
