# Phase 3 — Guardrail & Reconciliation Agent

**Estimate:** 2 days (Aug 24–25)
**Demo sentence:** "The system noticed this new clause contradicts what it already knew, and wrote down why."

**Status:** `NOT STARTED` · **Started:** — · **Completed:** —

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
- [ ] Vertex AI embeddings over the clause text; store the vector on the clause.
- [ ] `find_similar(clause, k=10)`: load active clauses filtered by
      `substance_normalized` **or** the same jurisdiction, cosine-rank in process.
- [ ] Keep the function signature stable so a vector index can replace the body.

### Guardrail (`guardrail/`, pure functions, heavily tested)
- [ ] `comparability(a, b) -> Comparable | Incomparable(reason)`:
  - substances must match after normalization;
  - product types must match or one must be a documented superset;
  - units must be equal or convertible through an explicit conversion table
    (`percent_w_w ↔ mg_per_kg ↔ ppm`) — no inferred conversions;
  - measurement basis must match (per weight vs per volume vs per serving);
  - both clauses must be `clause_type: numeric_limit` for limit comparison.
- [ ] `relationship_class(a, b)` — deterministic, before any LLM call:
  - same jurisdiction → **supersede question** (which is current? decided by
    `effective_date`, then document date);
  - different jurisdiction → **cross-jurisdiction conflict** (both hold; the
    stricter one binds the export);
  - and if the limits are numerically equal, there is **no** finding at all —
    do not invoke the model to confirm that 0.05 equals 0.05.
- [ ] Unit tests including adversarial pairs: different substance, different
      product type, incompatible units, one numeric and one labeling clause.
      Target from the PRD: zero false conflicts across this set.

### Gemini judge
- [ ] Invoked **only** for pairs the guardrail passed and where the deterministic
      classification is genuinely ambiguous — overlapping scope, unclear
      applicability, conflicting effective dates, or exemption language.
- [ ] Input: both clause texts and their structured fields. Output: a constrained
      enum verdict (`supersedes`, `conflicts`, `distinct_scope`, `ambiguous`) plus a
      one-sentence rationale, as structured JSON.
- [ ] Judge output is validated; anything unparsable becomes `ambiguous`.
- [ ] `ambiguous` → `needs_review`. Never `conflict`.

### Consumption & concurrency
- [ ] `/internal/reconcile` consumes `clause.extracted`. Clauses from one document
      reconcile **in parallel**, which is the point of per-clause fan-out.
- [ ] **This creates a real race:** two clauses reconciling against the same existing
      clause. Every clause state mutation runs inside a Firestore transaction that
      re-reads the target clause and aborts if its status changed. Untransacted
      mutation here produces a lost update and an inconsistent graph — this is the
      cost of the fan-out and it is paid here, not deferred.
- [ ] Idempotency: if the clause is already past `pending_reconciliation`, ack and
      return.
- [ ] After a successful mutation, **publish `graph.changed`** for phase 4.

### Verdict application (`store/`, transactional)
- [ ] `supersedes`: old clause → `superseded`, new clause → `active`, set
      `supersedes` / `superseded_by`, write `clause_superseded`.
- [ ] `conflicts`: create a `conflicts` record, mark both clauses `conflicted`,
      write `conflict_opened`.
- [ ] no match: new clause → `active`, write `clause_created`.
- [ ] confidence < 0.5 at any point → `needs_review`, write `clause_flagged_review`,
      and stop. Low-confidence input never mutates existing state.
- [ ] All writes for one clause happen in a single Firestore batch alongside their
      events. A partial mutation with no event is a bug, not an edge case.

### Observability
- [ ] Extend the debug view with every guardrail decision and its reason enum,
      whether the judge was invoked, and its raw verdict.
- [ ] Log `guardrail_rejected`, `judge_invoked`, `judge_verdict`, `state_mutation`.
- [ ] Log-based metric on judge invocation rate — a spike means the guardrail
      regressed, and you want to know that the day it happens.

### Web
- [ ] `data-testid` on reconciliation results, conflict rows, and the review queue.
- [ ] Reconciliation results panel on the document page: per clause, what the system
      decided and why — including the guardrail's reason when a pair was rejected.
      Showing rejected comparisons is more persuasive than only showing hits.
- [ ] Conflicts list page with severity and both clause texts side by side.
- [ ] `needs_review` queue with a single "confirm" action promoting a clause to
      `active` (no workflow, no assignment, no comments).

## Exit criteria

- [ ] Ingesting an EU clause at 0.05% when an EU clause at 0.10% is active produces a
      **supersede**, not a conflict, and the old clause reads `superseded`.
- [ ] An active BPOM clause at 0.10% and an active EU clause at 0.05% produce a
      **cross-jurisdiction conflict**, and both clauses stay active.
- [ ] A clause about a different substance produces **no finding**, and the guardrail
      logs the rejection reason.
- [ ] A low-authority pasted announcement produces `needs_review` and mutates nothing.
- [ ] Every mutation in the above has a matching `graph_events` record; an integrity
      test asserts this.
- [ ] Two clauses from one document reconciling concurrently against the same existing
      clause produce a consistent result — tested by forcing simultaneous delivery.
- [ ] Reconciliation runs as an ADK agent on the deployed worker, and the guardrail
      functions are unit-tested without ADK in the loop.
- [ ] Deployed.

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
