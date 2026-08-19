# ReguLens — Implementation Plan

End-to-end MVP plan derived from `../regulens-session-summary.md`, scoped to the
All Things Agentic Hackathon (Collaborative Partner track).

**Hard deadline: 31 Aug 2026, 5:00pm PDT** — 1 Sep, ~07:00 WITA.
**Plan start: 19 Aug 2026.** 13 calendar days available, **13 days of planned
work — zero float.** Adding Cloud Build, Secret Manager, Docker Compose,
observability, and a dedicated E2E testing phase consumed the day of slack the
earlier draft had. Read the cut-line below **today**, not when you are behind.

**Confirmed constraints:** Google ADK is required. Gemini 3.5 or newer is required.
Pub/Sub and Cloud Run Jobs are approved and used. Gemma is an optional bonus and is
the first thing to cut.

## The core loop this MVP must prove

```
Regulation document arrives
  → extracted into a structured clause
  → deterministic guardrail decides comparability
  → reconciliation decides conflict / supersede / new / needs-review
  → knowledge graph mutates, audit event written
  → impact propagates to the affected product + market
  → user is told what broke, why, and with what evidence
```

If a task does not move that loop forward, it does not belong in the MVP.

## Documents

| File | Purpose |
|---|---|
| **[PROGRESS.md](PROGRESS.md)** | **Start here every session — what is done, what is next, what is blocked** |
| [00-prd.md](00-prd.md) | Problem, users, hypothesis, MVP boundary, success criteria |
| [01-architecture.md](01-architecture.md) | Architecture + what complexity was deliberately cut |
| [02-data-model.md](02-data-model.md) | Firestore collections, state machines, API surface |
| [03-hackathon-compliance.md](03-hackathon-compliance.md) | Rules traceability, submission deliverables, eligibility checks |
| [04-observability.md](04-observability.md) | Correlation IDs, structured logging, tracing, metrics, alerts, the debug view |
| [phases/](phases/) | Phase-by-phase build plan with exit criteria |
| [99-demo-script.md](99-demo-script.md) | The demo this whole thing exists to deliver |

## Schedule

| # | Phase | Dates | Outcome | Days |
|---|---|---|---|---|
| 0 | [Foundation](phases/phase-0-foundation.md) | Aug 19–20 | Deployed skeleton + Cloud Build + Secret Manager + Compose + observability + ADK proven on Cloud Run | 2 |
| 1 | [Compliance Twin](phases/phase-1-compliance-twin.md) | Aug 21 | Product + ingredients + destination market | 1 |
| 2 | [Ingestion & Extraction](phases/phase-2-ingestion-extraction.md) | Aug 22–23 | Upload → structured clauses with computed confidence + debug view | 2 |
| 3 | [Guardrail & Reconciliation](phases/phase-3-guardrail-reconciliation.md) | Aug 24–25 | Clause compared, judged, graph mutates, event written | 2 |
| 4 | [Impact Engine](phases/phase-4-impact-engine.md) | Aug 26–27 | Unprompted status flip + alert — the autonomy requirement | 2 |
| 5 | [Timeline & Query](phases/phase-5-timeline-query.md) | Aug 28–29 | Before/after timeline + grounded, cited answers | 2 |
| 6 | [E2E Testing](phases/phase-6-e2e-testing.md) | Aug 30 | Every use case green against the deployed stack; video footage captured | 1 |
| 7 | [Hardening & Submission](phases/phase-7-demo-hardening.md) | Aug 31 | Seed Job, alert drills, video edit, diagram, README, submit | 1 |

**Submit by Aug 31, 18:00 WITA** (03:00 PDT) — a 14-hour buffer before the cut-off.
Do not plan to use the final night.

### The schedule is exactly full — do this to create float

Phase 0 grew from 1.5 to 2 days, and phase 6 is new. Recommendation: **take the
first two cut-line items now, on day one**, rather than deciding under pressure:

- **Drop Gemma.** It is an optional bonus. Nothing depends on it. Saves ~0.5 day
  in phase 2 and removes a whole model integration from the risk surface.
- **Drop OCR fallback.** Choose demo PDFs with a real text layer. Saves ~0.25 day
  and removes the least reliable code path in the build.

That converts zero float into roughly three quarters of a day. Phase 5 is the
elastic one after that — the timeline UI and the extra query intents can shrink
without touching the thesis.

## Cut-line

When you fall behind, cut in this order. Decide by the *end of phase 3*, not on
Aug 30.

1. **Gemma pre-filter** — optional bonus, nothing depends on it. *Recommended: cut now.*
2. **OCR fallback** — support PDFs with a text layer plus pasted text only.
   *Recommended: cut now.*
3. **Timeline UI polish** — a plain reverse-chronological event list still proves
   the audit trail.
4. **Query intents** — keep only "why is my product at risk?" and "can I export to
   Germany?".
5. **Impact chain visual** — a text list of the propagation path still reads.
6. **Second market's depth** — one authoritative clause per jurisdiction is enough.

**Never cut:** the phase-3 guardrail (the architectural thesis), the phase-4
unprompted flip (the hackathon's autonomy requirement), the phase-6 UC-B and
idempotency specs (they catch the bugs that kill live demos), or any of phase 7
(an unsubmitted project scores zero).

Also never cut, despite the temptation when behind: `trace_id` propagation and the
debug view. They are what make phase 6 finishable in one day.

## Tracking progress

Every phase file carries a **Status** block and checkboxes; `PROGRESS.md` carries
the roll-up. The rule, also written into `../CLAUDE.md` so future sessions pick it
up automatically:

> Update the plan in the same commit as the code. Tick what landed, set the phase
> status, append a line to the session log in `PROGRESS.md`.

Checkbox meaning: `[ ]` not done · `[x]` done, in the repo, **and deployed** ·
`[~]` deliberately skipped, with ` — SKIPPED: reason` on the line.

Tick a box only when the thing is real. A checkbox that lags the repo is worse than
no checkbox, because the next session trusts it.

## Rules for executing this plan

1. **Each phase ends deployed.** A phase without a live URL is not done.
2. **Each phase has a demo sentence.** If you cannot show it in 20 seconds, it is
   not finished.
3. **Deterministic code owns mutations.** ADK agents propose; typed code decides.
   Enforced per phase, not bolted on at the end.
4. **Every Pub/Sub handler is idempotent.** Delivery is at-least-once and *will*
   redeliver. Test redelivery explicitly in phases 2, 3, and 4.
5. **ADK tools wrap plain functions.** Every tool body must be importable and
   testable without ADK, so a framework problem can never block the demo.
6. **Seed data is code, not clicks.** The demo baseline is a Cloud Run Job.
7. **Log structured, always.** `trace_id` on every line, every message, every
   event. No `print`. See `04-observability.md`.
8. **Add `data-testid` as you build the UI**, from phase 1. Phase 6 writes specs
   against those selectors and has no time to retrofit them.
9. **Claim only what is verified.** No fabricated readiness percentages, no invented
   regulation text, no "monitoring" language for behaviour that only runs on upload.

## Do this today, before writing code

<!-- Tick these off in place. -->

- [ ] Confirm eligibility — country exclusions, age, entry category
      (`03-hackathon-compliance.md`). Blocking if it fails.
- [ ] Register on Devpost; check whether registration closes before submission.
- [ ] Create the GCP project and set a budget alert.
- [ ] Confirm the exact Gemini 3.5+ model identifier available in your region.
- [ ] Work through [`../todo.md`](../todo.md) — the inputs only you can provide.
      Several of them block phase 0 or phase 2.
