# Phase 4 — Impact Engine & Compliance Readiness

**Estimate:** 2 days (Aug 26–27)
**Demo sentence:** "Nobody asked it anything — the product just went from compliant to high-risk for Germany, on its own."

**Status:** `IN PROGRESS` · **Started:** 23 Aug 2026 · **Completed:** —

> Built and live-verified 23 Aug. The headline is real: with BPOM 400 mg/kg
> active and the product at 300 mg/kg, Indonesia reads `compliant` and Germany
> `unknown`; uploading the EU excerpt flipped Germany to **non_compliant with
> zero user interaction**, inside the demo window, and an alert naming the
> market fired. Requirements materialize family-aware; evaluations are pure
> arithmetic. Remaining: latency metric emission, impact-chain visual,
> explicit redelivery-alert idempotency drill (phase 6).

<!-- MAINTAIN THIS FILE.
     Set Status to IN PROGRESS when you begin, COMPLETE when every exit criterion
     is ticked. Fill the dates. Tick each `- [ ]` as it lands — a ticked box means
     it exists in the repo and is deployed, not that it is written down somewhere.
     If you deliberately skip an item, change it to `- [~]` and add ` — SKIPPED:
     reason` on the same line so nobody re-litigates it later.
     Then update ../PROGRESS.md. -->

## Goal

Trace a knowledge-graph change through to a business consequence, and surface it
without the user asking. This is the difference between a document tool and an
agentic system.

## The propagation path

```
clause changed
  → requirements referencing that clause (indexed lookup)
  → products those requirements belong to
  → markets those products target
  → re-evaluate → status change → alert
```

No LLM anywhere in this phase. Comparing 0.08 to 0.05 is arithmetic, and making a
model do it introduces a failure mode for no gain. The Impact Agent is still
registered as an ADK agent so the hierarchy is complete and legible — but its tools
contain no model call, and the submission says so plainly. A judge scoring
architectural discipline will credit that more than a fourth reasoning agent.

**This phase carries the hackathon's autonomy requirement** ("operate beyond
standard chat loops"). The unprompted status flip *is* the qualifying behaviour.
If the schedule slips, protect this phase over phase 5.

## Scope

### Consumption
- [ ] `/internal/impact` consumes `graph.changed`.
- [ ] Idempotent: re-running impact over an unchanged graph produces no new events
      and no duplicate alerts.

### Requirement materialization
- [ ] `materialize_requirements(product)`: for each target market, for each
      jurisdiction of that market, find `active` clauses where
      `substance_normalized` matches a product ingredient **or** the clause is a
      non-numeric requirement for the product type; create/update `requirements`.
- [ ] Run on product create/update (phase 1 hook) and on clause state change.
- [ ] Requirements are updated in place, never duplicated — key on
      `(product_id, market_id, clause_id)`.

### Evaluation (deterministic)
- [ ] `numeric_limit` with a known product amount → `pass` / `fail`.
- [ ] Unit conversion via the phase-3 table; unconvertible → `needs_review`.
- [ ] Product ingredient present but amount unknown → `needs_review`.
      **Never `pass`.**
- [ ] Non-numeric clause types → `needs_review` with the clause text shown, so the
      user can check it themselves. The UI must say "we surfaced this, we did not
      verify it".
- [ ] Clause confidence < 0.5 → `needs_review` regardless of the arithmetic.
- [ ] Severity derived deterministically; no model-assigned risk levels.

### Product status rollup
- [ ] `compliance_status(product, market)`:
      any `fail` → `non_compliant`; else any `needs_review` → `attention_required`;
      else all `pass` and at least one requirement → `compliant`;
      no requirements → `unknown` ("no regulatory data for this market").
- [ ] Status changes write `product_status_changed` with before/after and the
      causing clause and document.

### Observability
- [ ] Emit the **end-to-end propagation latency** metric here: upload timestamp to
      `product_status_changed`. This is the PRD's 90-second headline number and
      phase 6 asserts against the metric, not a stopwatch.
- [ ] Log `requirement_evaluated` and `status_changed` as structured events.

### Alerts
- [ ] `GET /alerts` reads recent `product_status_changed` events where the status
      worsened.
- [ ] Acknowledge action (writes an ack field; keep it that simple).

### Web
- [ ] Readiness panel on the product page, per market:
      overall status badge, then a checklist of requirements with `✓ / ⚠ / ✕`,
      the limit, the product's value, and the source clause link.
- [ ] **Prefer issue counts over a percentage.** "3 issues — 1 critical" is honest;
      "74% ready" implies a denominator we cannot defend. If a percentage is wanted
      for the visual, show it as "checks passed: 4 of 7" with the counts visible.
- [ ] Impact chain visual on an alert: regulation → clause → requirement →
      product → market → risk. This is the concept's Impact View and it is the
      single most legible artifact in the demo.
- [ ] Alert banner appearing on the dashboard without a page action, driven by the
      poll that is already running.

## Exit criteria

- [ ] With the BPOM 0.10% clause active and the product at 0.08%, Indonesia reads
      `compliant`.
- [ ] Ingesting the EU 0.05% clause flips Germany to `non_compliant` **with no user
      interaction beyond the upload**, within the 90-second target.
- [ ] The alert names the causing requirement and links to both clauses.
- [ ] A product with an unmeasured ingredient shows `attention_required`, never
      `compliant`.
- [ ] The impact chain visual renders from real event data, not a hardcoded diagram.
- [ ] `graph_events` contains `requirement_changed` and `product_status_changed` for
      the flip.
- [ ] Redelivering `graph.changed` produces no second alert.
- [ ] Deployed.

## Out of scope

Remediation suggestions ("reformulate to 0.04%") — that is advice we cannot
responsibly generate; multi-product portfolio rollup; cost/risk quantification;
scheduled re-evaluation (evaluation is event-driven only); historical
what-if simulation.

## Risk notes

- The tempting failure is to compute a satisfying readiness percentage by counting
  categories the system does not actually evaluate. That is fabricated
  precision — and a judge asking "what are the other 26%?" will expose it. Show
  what is verified and mark the rest as unverified.
- Re-evaluation must be idempotent: uploading the same document twice must not
  produce two alerts.
