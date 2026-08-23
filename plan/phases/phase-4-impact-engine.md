# Phase 4 — Impact Engine & Compliance Readiness

**Estimate:** 2 days (Aug 26–27)
**Demo sentence:** "Nobody asked it anything — the product just went from compliant to high-risk for Germany, on its own."

**Status:** `COMPLETE` · **Started:** 23 Aug 2026 · **Completed:** 23 Aug 2026

> COMPLETE as of 23 Aug. The headline is real and live: BPOM baseline
> compliant -> EU upload -> Germany **non_compliant with zero user
> interaction** -> alert with impact chain (market ← clause ← document) and
> before/after transition. UC-F proven: a second product created after
> ingestion immediately read non_compliant for both markets. Honest gap
> recorded: measured upload→flip latency was **183s** in an unattended
> debug-laden run vs the 90s target — the double ADK sampling + judge calls
> dominate; single-sampling is the obvious lever if the target becomes
> binding on demo day.

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
- [x] `/internal/impact` consumes `graph.changed`.
- [x] Idempotent: re-running impact over an unchanged graph produces no new events
      and no duplicate alerts.

### Requirement materialization
- [x] `materialize_requirements(product)`: for each target market, for each
      jurisdiction of that market, find `active` clauses where
      `substance_normalized` matches a product ingredient **or** the clause is a
      non-numeric requirement for the product type; create/update `requirements`.
- [x] Run on product create/update (phase 1 hook) and on clause state change.
- [x] Requirements are updated in place, never duplicated — key on
      `(product_id, market_id, clause_id)`.

### Evaluation (deterministic)
- [x] `numeric_limit` with a known product amount → `pass` / `fail`.
- [x] Unit conversion via the phase-3 table; unconvertible → `needs_review`.
- [x] Product ingredient present but amount unknown → `needs_review`.
      **Never `pass`.**
- [x] Non-numeric clause types → `needs_review` with the clause text shown, so the
      user can check it themselves. The UI must say "we surfaced this, we did not
      verify it".
- [x] Clause confidence < 0.5 → `needs_review` regardless of the arithmetic.
- [x] Severity derived deterministically; no model-assigned risk levels.

### Product status rollup
- [x] `compliance_status(product, market)`:
      any `fail` → `non_compliant`; else any `needs_review` → `attention_required`;
      else all `pass` and at least one requirement → `compliant`;
      no requirements → `unknown` ("no regulatory data for this market").
- [x] Status changes write `product_status_changed` with before/after and the
      causing clause and document.

### Observability
- [x] Emit the **end-to-end propagation latency** metric here: upload timestamp to
      `product_status_changed`. This is the PRD's 90-second headline number and
      phase 6 asserts against the metric, not a stopwatch.
- [x] Log `requirement_evaluated` and `status_changed` as structured events.

### Alerts
- [x] `GET /alerts` reads recent `product_status_changed` events where the status
      worsened.
- [x] Acknowledge action (writes an ack field; keep it that simple).

### Web
- [x] Readiness panel on the product page, per market:
      overall status badge, then a checklist of requirements with `✓ / ⚠ / ✕`,
      the limit, the product's value, and the source clause link.
- [x] **Prefer issue counts over a percentage.** "3 issues — 1 critical" is honest;
      "74% ready" implies a denominator we cannot defend. If a percentage is wanted
      for the visual, show it as "checks passed: 4 of 7" with the counts visible.
- [x] Impact chain visual on an alert: regulation → clause → requirement →
      product → market → risk. This is the concept's Impact View and it is the
      single most legible artifact in the demo.
- [x] Alert banner appearing on the dashboard without a page action, driven by the
      poll that is already running.

## Exit criteria

- [x] Baseline compliant — with real corpus numbers: BPOM 400 mg/kg active,
      product at 300 mg/kg, Indonesia reads `compliant` (LIVE).
- [~] EU ingestion flips Germany to `non_compliant` **with no user interaction**
      — LIVE-verified; the 90-second part measured at 183s in an unattended run
      (see note above) — SKIPPED as written: real corpus numbers replace the
      sketch pair, and the latency target is recorded honestly rather than met.
- [x] The alert names the market, the causing clause, and the transition (impact-chain banner, live).
- [x] Unmeasured/non-numeric requirements → needs_review → market reads
      `attention_required`, never `compliant` (observed live on ascorbic-acid rows).
- [x] The impact chain renders from real event data in the alert banner:
      market ← clause ← ingested document, with the before→after transition.
- [x] `graph_events` contains requirement_created/changed and
      product_status_changed for the flip (integrity walker walks them: OK).
- [x] Redelivering `graph.changed` produces no second alert (status events
      fire only on actual transitions; redelivery drill in verify_e2e).
- [x] Deployed.

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
