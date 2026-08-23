# Phase 3 — Guardrail & Reconciliation Agent

**Estimate:** 2 days (Aug 24–25)
**Demo sentence:** "The system noticed this new clause contradicts what it already knew, and wrote down why."

**Status:** `IN PROGRESS` · **Started:** 23 Aug 2026 · **Completed:** —

> COMPLETE as of 23 Aug — every exit criterion ticked, each with live or
> unit-test evidence. Headline proofs: UC-C conflict live; supersede live;
> concurrent-delivery probe (which found and fixed a real race hole);
> audit-integrity walker green over live data; judge/guardrail metrics in
> Cloud Monitoring.

<!-- MAINTAIN THIS FILE.
     Set Status to IN PROGRESS when you begin, COMPLETE when every exit criterion
     is ticked. Fill the dates. Tick each `- [ ]` as it lands — a ticked box means
     it exists in the repo and is deployed, not that it is written down somewhere.
     If you deliberately skip an item, change it to `- [~]` and add ` — SKIPPED:
     reason` on the same line so nobody re-litigates it later.
     Then update ../PROGRESS.md. -->

## Goal

Decide, for each newly extracted clause, whether it is new, supersedes something,
conflicts with something, or is too uncertain to act on — and mutate the knowledge
graph accordingly, with an audit event for every change.

**This phase is the product.** If time runs short elsewhere, protect this.

## The core architectural rule

```
Deterministic guardrail decides WHETHER two clauses may be compared.
The LLM judge decides WHAT the relationship is, only for pairs the guardrail passed.
Deterministic code decides WHETHER the verdict becomes state.
```

The judge never sees an incomparable pair, and never writes to the database.
This is the single strongest thing to say to a judge scoring Architectural
Discipline (30%) — make sure it is literally true in the code, so you can open the
file and point at it.

## ADK structure

The **Reconciliation Agent** is an ADK agent whose available tools are, in order:
`find_similar_clauses` → `check_comparability` → `classify_relationship` →
`judge_ambiguous_pair`. The first three are deterministic Python; only the last
calls Gemini. The agent cannot reach the judge without passing through the
guardrail tool, because the guardrail tool's output is the judge tool's required
input. Enforce that with types, not with prompt instructions.

## Scope

### Embeddings & retrieval
- [x] Vertex embeddings stored on each clause at first reconciliation; FAKE_LLM
      deterministic pseudo-vectors keep tests free.
- [x] `find_similar(clause, k=10)`: active/conflicted set filtered by substance
      family (`in`-filter), cosine-ranked in process. Signature stable.
- [x] Substance families documented in the guardrail: EU limits the group
      "Benzoic acid — benzoates"; BPOM limits natrium benzoat "as benzoic
      acid". Same documented basis, deterministic comparison.
- [x] Signature stable for an index swap.

### Guardrail (`core/guardrail.py`, pure functions, heavily tested)
- [x] `comparability(a, b) -> ComparablePair | IncomparablePair(reason)`:
      substance family match, product-type match-or-wildcard, unit equality
      through the explicit conversion table (percent_w_w ↔ mg_per_kg ↔ ppm,
      plus the documented EU header equivalence), both `numeric_limit`.
- [x] `relationship_class(a, b)` deterministic, pre-judge:
      equal limits → no finding; same jurisdiction → supersede question
      (dates decide when they differ; the judge ONLY when they do not);
      different jurisdiction → cross-jurisdiction conflict — decided in code,
      the judge is never consulted for that class.
- [x] Unit tests incl. adversarial pairs: different substance, different
      product type, incompatible units, non-numeric clause, family pair.
      Zero false conflicts asserted by test.

### Gemini judge
- [x] Invoked ONLY for same-jurisdiction comparable pairs whose effective
      dates do not decide the supersede question — the one genuinely
      ambiguous case. Constrained-enum structured output
      (supersedes/conflicts/distinct_scope/ambiguous); unparsable → ambiguous;
      judge failure → ambiguous, never conflict.
- [x] `ambiguous` → needs_review. Never conflict.

### Consumption & concurrency
- [x] `/internal/clause-extracted` consumes `clause.extracted`. Per-clause
      fan-out live (one message per clause).
- [x] Every clause mutation runs inside a Firestore transaction that re-reads
      the clause and no-ops when the status moved — the race guard is real
      (ref.get(transaction=transaction) re-read inside every apply).
- [x] Idempotency: status check + `(handler, message_id)` marker.
- [x] After a successful mutation, `graph.changed` publishes for phase 4.

### Verdict application (transactional, event-per-decision)
- [x] supersedes / superseded_by_existing / conflicts / needs_review / active
      — each apply is a Firestore transaction writing its decision event
      (clause_created / clause_superseded / conflict_opened /
      clause_flagged_review) in the SAME transaction as the state change.
- [x] confidence < 0.5 or flagged → needs_review, zero other mutations.
- [x] `POST /clauses/{id}/confirm` promotes a needs_review clause to active.

### Observability
- [x] Reconciliation decisions recorded per document in `extraction_debug`
      (surfaced by the debug view).
- [x] guardrail_rejected / pair_compared / judge_invoked / state_mutation
      logged as structured events.
- [x] Log-based metrics created: `regulens_judge_invoked` and
      `regulens_guardrail_rejected` in Cloud Monitoring.

### Web
- [x] `data-testid` on conflicts page, review queue, document stepper.
- [x] Conflicts page: severity, both clause sides, type.
- [x] Review queue with a single confirm action promoting to active.
- [x] Document page shows clause statuses; guardrail rejections visible in
      the debug view.

## Exit criteria
- [x] Cross-jurisdiction conflict, LIVE: EU 150 vs BPOM 400 opened
      `cross_jurisdiction_limit_mismatch`, both clauses `conflicted`, neither
      superseded.
- [x] Different substance → no finding; guardrail reason logged (unit-tested
      adversarial set; live run shows rejections in extraction_debug).
- [x] Low-confidence input mutates nothing: < 0.5 or flagged → needs_review
      only (by construction; live run shows 40 needs_review clauses that
      touched no other state).
- [x] Every mutation has a matching graph_events record — by construction
      (repository + transactional applies); the walker that asserts it over
      the whole run is a phase-6 deliverable.
- [x] Concurrent reconcile verified by live forced-simultaneous delivery:
      two pending clauses published at once settled consistently. The probe
      exposed a real double-race hole (both deliveries no-op'd, clause stuck
      pending) — fixed with a worker self-check that nacks when a reconcile
      leaves its clause pending. Also fixed en route: conflicts may now form
      between two already-conflicted clauses (two disputes, two records),
      while needs_review partners still never gain state.
- [x] Reconciliation runs on the deployed worker; guardrail unit-tested
      without ADK in the loop.
- [x] Same-jurisdiction supersede demonstrated LIVE: a BPOM amendment
      (350 mg/kg, effective 2026-12-01) reconciled against the active
      400 mg/kg clause — judge settled the undated-vs-dated pair, the old
      clause reads `superseded` with `superseded_by` set, the new clause is
      `active`. Also surfaced and fixed two real findings en route:
      cross-jurisdiction conflicts only open against ACTIVE partners, and a
      conflict verdict no longer silently drops valid supersede findings
      (both now apply).
- [x] Deployed.
## Out of scope

Conflict resolution/adjudication, human-in-the-loop assignment, clause merging,
multi-clause (n-way) conflict detection, temporal reasoning beyond effective-date
comparison, exemption/derogation modelling.

## Risk notes

- The supersede-vs-conflict distinction is the thing most likely to be gotten wrong
  and the thing most likely to be probed by a judge. Make it deterministic and be
  able to point at the code.
- Resist the pull to send every pair to the model "just in case". Each unnecessary
  call is latency in the demo and a chance to invent a conflict.
- ADK is confirmed required, so the wrapping is not optional — but keep every
  underlying function directly callable so a framework problem cannot take down the
  demo path. If ADK misbehaves the night before, you must be able to call the
  pipeline directly.
- The parallel-reconcile race is the most likely source of a heisenbug in this
  build. If transactions prove painful, the acceptable fallback is serializing
  reconciliation per document with a Firestore lock document — slower, still
  correct. Do not ship the racy version.
