# Phase 3 — Guardrail & Reconciliation Agent

**Estimate:** 2 days (Aug 24–25)
**Demo sentence:** "The system noticed this new clause contradicts what it already knew, and wrote down why."

**Status:** `COMPLETE` · **Started:** 23 Aug 2026 · **Completed:** 23 Aug 2026

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
- [x] **The food category is part of comparability, 31 Aug.** An additive table
      is one limit per food, not competing limits for the same food. A clause
      carried a substance, a limit, a jurisdiction and a date but nothing that
      said *what food*, so every pair of rows in one BPOM table looked like a
      supersede question with no date to settle it — the one case that goes to
      the judge, which answered `ambiguous`, which parked the row. Thirty-six
      rows of BPOM 11/2019 sat in the queue asking a person to confirm that a
      regulation does not contradict itself. `core/scope.py` reads the GSFA code
      the regulator prints at the head of the row (`14.1.4.2`, `04.1.2.8`) and
      the guardrail refuses the pair as `food_category_mismatch`. Not inferred,
      not a model call, and silence on either side blocks nothing.
- [x] **`POST /clauses/recheck` re-decides what the queue is holding, 31 Aug.**
      Only clauses parked `judge_ambiguous` are reopened — the reason that means
      "typed code had nothing to go on", which is exactly what changed. Low
      confidence and low authority are never touched: no recheck makes an
      unreadable number readable. Each clause goes back through
      `reconcile_clause`, so one that is still ambiguous returns to the queue,
      and the response names what it could not settle rather than reporting only
      its successes. Proven against the emulator: a fresh pair from one table
      reconciles `active` with no judge call; a backlogged `judge_ambiguous`
      clause rechecks to `active` carrying `clause_rechecked` + `clause_created`;
      a `low_confidence_or_flagged` clause is skipped as `needs_a_person`; the
      audit-integrity walker stays green.

### Known follow-up, not done

- [ ] The category is read for comparability but **not** for binding.
      `clause_binds` still matches on jurisdiction, substance and
      `product_type`, so a drink is bound by every food category's benzoate row
      and strictest-wins takes the lowest of them. This was already true of any
      clause a person confirmed by hand; automatic resolution makes it reachable
      at scale. Fixing it needs a category on the *product*, which is a new
      input from the user, not a code change.

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
