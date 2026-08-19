# Phase 6 — End-to-End Testing

**Estimate:** 1 day (Aug 30)
**Demo sentence:** "One command runs every use case against the deployed system and tells you it works."

**Status:** `NOT STARTED` · **Started:** — · **Completed:** —

<!-- MAINTAIN THIS FILE.
     Set Status to IN PROGRESS when you begin, COMPLETE when every exit criterion
     is ticked. Fill the dates. Tick each `- [ ]` as it lands — a ticked box means
     it exists in the repo and is deployed, not that it is written down somewhere.
     If you deliberately skip an item, change it to `- [~]` and add ` — SKIPPED:
     reason` on the same line so nobody re-litigates it later.
     Then update ../PROGRESS.md. -->

## Goal

Prove every use case from the concept works against the **deployed** stack, not
against local mocks — and leave behind a suite that catches a regression on Aug 31
before a judge does.

## Why a phase and not "we tested as we went"

Per-phase exit criteria verify one phase. They do not catch the failures that only
appear when the whole pipeline runs: a Pub/Sub redelivery producing a second alert,
a reconciliation race under real concurrency, an impact pass reading a clause
mid-transaction. Those are precisely the bugs that surface during a live demo.

## Test layers

| Layer | Runs against | Runs when | Owns |
|---|---|---|---|
| Unit | Pure functions | Every commit, Cloud Build step 1 | Guardrail, normalization, unit conversion, confidence math, evaluation logic |
| Integration | Docker Compose (emulators + `FAKE_LLM=1`) | Every commit | Pub/Sub handlers, idempotency, transactions, repository event-writing |
| Evaluation | Real Vertex, fixture documents | On demand | Extraction accuracy, query grounding |
| E2E | **Deployed dev environment** | Cloud Build after deploy, and manually before submission | Full user journeys through the browser |

`FAKE_LLM=1` is what makes integration tests deterministic and free. Without it,
this suite is too slow and too expensive to run on every commit, and a suite you
don't run is not a suite.

## Use-case coverage

Every use case from the concept document. Each is an E2E spec. Tick when the spec
is written **and green against the deployed environment**.

- [ ] UC-A — Entering a new market
- [ ] UC-B — Regulation changed *(the core scenario — if this is red, nothing else matters)*
- [ ] UC-C — Cross-jurisdiction conflict
- [ ] UC-D — Messy / low-authority source
- [ ] UC-E — Pre-export compliance check
- [ ] UC-F — Multi-product assertion only (out of MVP scope as a journey)
- [ ] Same-jurisdiction supersede
- [ ] Non-comparable pair — zero false conflicts
- [ ] Pub/Sub redelivery — no duplicates
- [ ] Concurrent reconcile — consistent final state
- [ ] DLQ path + retry recovery
- [ ] Grounding refusal — zero invented citations
- [ ] Audit integrity walker
- [ ] Unknown amount never reads `pass`
- [ ] Idempotent seed
- [ ] Latency under 90s from the metric

### UC-A — Entering a new market
Create the product, add Germany, no EU data ingested.
**Expect:** status `unknown` with an honest "no regulatory data for this market" —
not 0%, not "compliant".

### UC-B — Regulation changed *(the core scenario)*
Baseline: BPOM 0.10% active, product at 0.08%, Indonesia `compliant`.
Upload the EU 0.05% regulation. Do nothing else.
**Expect:** within 90s and with **no user query**, Germany flips to
`non_compliant`, an alert appears naming sodium benzoate, `graph_events` contains
`requirement_changed` (0.10 → 0.05) and `product_status_changed`.
This spec is the hackathon's autonomy requirement. If it goes red, nothing else matters.

### UC-C — Cross-jurisdiction conflict
With both BPOM 0.10% and EU 0.05% active.
**Expect:** a `cross_jurisdiction_limit_mismatch` conflict, **both clauses remain
`active`** (neither supersedes the other), Indonesia still `compliant`, Germany
`non_compliant`.

### UC-D — Messy / low-authority source
Paste the Indonesian announcement text ("batasnya sekarang lebih rendah… katanya
mulai berlaku tahun ini") with source type *social/chat*.
**Expect:** a clause with low confidence and `needs_review`, **zero mutations** to
existing clauses, no conflict opened, no product status change. Assert the mutation
count is zero — this is the test that proves authority tiering is real.

### UC-E — Pre-export compliance check
Ask "Can I export my Herbal Drink Powder with 0.08% sodium benzoate to Germany?"
**Expect:** `NOT READY`, an issue list derived from real requirement evaluations,
at least one cited clause id present in the retrieved set, and a confidence value.

### UC-F — Multi-product monitoring — **out of MVP scope**
Not tested as a UI journey. One assertion only: creating a second product and
ingesting a clause affecting both produces two `product_status_changed` events.
This proves the data model does not preclude the portfolio view, which is the honest
claim to make in the submission.

### Supporting specs (the ones that actually break)

| Spec | Assertion |
|---|---|
| Same-jurisdiction supersede | EU 0.10% then EU 0.05% → **supersede**, not conflict; old clause `superseded` |
| Non-comparable pair | Different substance / product type / unit → **no finding**, guardrail reason logged. Zero false conflicts |
| Pub/Sub redelivery | Republish `document.uploaded` for a processed document → no duplicate clauses, no second alert |
| Concurrent reconcile | Publish N `clause.extracted` simultaneously against one shared existing clause → consistent final state |
| DLQ path | Force five failures → document `failed`, DLQ alert fires, retry button recovers |
| Grounding refusal | "What are Japan's requirements?" → explicit no-data answer, **zero** citations invented |
| Audit integrity | Every mutation in the full run has a matching `graph_events` record. Walk both collections and diff |
| Unknown amount | Ingredient with no measured amount → `needs_review`, **never** `pass` |
| Idempotent seed | Seed → run → seed → byte-identical baseline |
| Latency | Full UC-B run completes under 90s, measured from the metric, not a stopwatch |

## Tasks

- [ ] `e2e/` with Playwright, running against a configurable base URL.
- [ ] Fixtures: the demo documents and the hand-labelled clause set from phase 2,
      committed.
- [ ] `FAKE_LLM=1` response fixtures covering every extraction used by the suite.
- [ ] Integration tests for each Pub/Sub handler against the Compose emulators.
- [ ] The audit-integrity walker as a reusable assertion, not a one-off script.
- [ ] Cloud Build step: run integration tests on every commit; run E2E against the
      deployed dev service after deploy.
- [ ] `make test-all` — one command, runs everything, prints a pass/fail table.
- [ ] Fix what this phase finds. **Budget half the day for fixes, not for writing
      tests.** If the suite finds nothing, you wrote the suite wrong.

## Exit criteria

- [ ] Every use-case spec above passes against the **deployed** environment.
- [ ] `make test-all` is green from a clean checkout.
- [ ] UC-B completes in under 90s, verified from the latency metric.
- [ ] Zero false conflicts across the non-comparable fixture set.
- [ ] Audit integrity walker reports no orphaned mutations.
- [ ] The suite runs in Cloud Build and blocks a red deploy.

## Out of scope

Load testing, performance benchmarking beyond the 90s target, cross-browser
testing (Chrome only), visual regression, accessibility audit, fuzzing, security
testing beyond confirming `/internal/*` rejects unauthenticated calls.

## Risk notes

- Writing E2E specs against a UI that is still moving wastes the day. Freeze the
  selectors used by tests: add `data-testid` attributes during phases 1–5 as you
  build, not now.
- If the suite finds a phase-3 concurrency bug on Aug 30, you have one day. That is
  the honest reason this phase exists rather than being folded into hardening — and
  the reason the concurrency work is not deferred out of phase 3.
- Record the demo video **during this phase** while you are running every use case
  anyway. It saves an hour on Aug 31 and the runs are already green.
