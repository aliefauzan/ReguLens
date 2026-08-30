# Improvement Loop — tracking file

Not a phase. A running list of post-phase-8 improvements, worked one loop at a
time: **analyze → plan → verify plan → execute → review → loop**.

Same checkbox semantics as the rest of `plan/`: `[x]` means real, verified, and
deployed. `[~]` means deliberately skipped with a reason on the line.

Last updated: **30 Aug 2026**

## Backlog, ranked

| # | Item | Status | Why it is on the list |
|---|---|---|---|
| 1 | Time-aware compliance | `COMPLETE` | `effective_date` is captured and never used by the impact engine |
| 2 | Strictest-wins across markets | `NOT STARTED` | Conflicts are detected, never resolved into a number to ship against |
| 3 | Long-document map-reduce extraction | `NOT STARTED` | The BPOM annex is a permanent refusal |
| 4 | Latency by chunk-level fan-out | `NOT STARTED` | 174.3s vs a 90s target on a 55-clause annex |
| 5 | Alerts that leave the building | `NOT STARTED` | No email/Slack/webhook anywhere in `api/app` |
| 6 | Measured accuracy, not a smoke test | `NOT STARTED` | 5/5 on fixtures is not precision/recall |
| 7 | Auditor evidence pack | `NOT STARTED` | Every input already exists in `graph_events` + `citations.py` |
| 8 | What-if simulation | `NOT STARTED` | Read-only reuse of `impact.evaluate()` |

---

## Loop 1 — Time-aware compliance

**Status:** `COMPLETE` · **Started:** 30 Aug 2026 · **Completed:** 30 Aug 2026

### The defect, stated so it can be tested

`Clause.effective_date` is extracted (`core/extraction/llm.py:46`), detected
(`core/detection.py:302`) and used by reconciliation to order supersessions
(`core/reconciliation.py:528`). `core/impact.py` never reads it.

Two consequences, both wrong:

1. A rule that enters into force in 2027 marks a product `non_compliant`
   **today**.
2. A rule that binds in 60 days is invisible until the day it binds, so the one
   window in which a company could reformulate is the one window the product
   does not show.

### Assumptions — say so now if any is wrong

- `effective_date` absent (`None`) means **in force**. That is today's behaviour
  and most stored clauses have no date; it must not change.
- `effective_date` present but unparseable also means **in force**. Failing open
  keeps a real limit visible; failing closed would hide a rule because a string
  was malformed.
- "Compliant" with no date asked for means **as of today**. The stored
  `products.compliance_status` keeps that meaning, so nothing downstream of it
  changes shape.
- Binding is a **filter**, not an evaluation concern: `evaluate()` is not
  touched. A requirement is still evaluated and still written; it is only
  counted into a different rollup.

### Success criteria

- [x] Test: product over the limit + clause `effective_date` = today + 365 →
      status today is `compliant`, and the response names an upcoming change on
      that date
- [x] Test: same clause with `effective_date` = yesterday → `non_compliant`
- [x] Test: same clause with `effective_date` = `None` → `non_compliant`
      (regression guard on existing behaviour)
- [x] Test: `effective_date` = `"not-a-date"` → `non_compliant` (fails open)
- [x] `make test-all` green from a clean checkout

### Steps

Scope confirmed 30 Aug: engine + API + UI + the upcoming-rule alert, in one
loop, verified all the way to Cloud Run.

- [x] **1. Store the date on the requirement.** `effective_date` into the
      `materialize_for_product` payload and into `REPORTED_FIELDS`, so a
      corrected date is a visible change rather than a silent one
      → verify: `test_requirement_change.py` extended, green
- [x] **2. Parse safely, in one place.** `_in_force(effective_date, as_of)` in
      `core/impact.py`. `None` → True. Unparseable → True, logged once
      → verify: unit test covers None / past / today / future / junk
- [x] **3. Split the rollup.** `rollup_status(product_id, as_of=None)` counts
      only in-force requirements. New `upcoming_changes(product_id, as_of=None)`
      returns, per market, the earliest future date and the status it brings
      → verify: the success-criteria tests above
- [x] **4. Record the schedule as an event.** New
      `EventType.PRODUCT_STATUS_SCHEDULED`, written when a market gains a future
      status worse than its current one. Same `write_with_event` path as every
      other mutation → verify: test asserts one event on first sight, none on
      re-run
- [x] **5. Alert on it.** `list_alerts` reads both `product_status_changed` and
      `product_status_scheduled`; `explain()` carries the date through
      → verify: `test_alerts.py` covers a scheduled alert and its wording inputs
- [x] **6. Surface it on the API.** `/products/{id}/compliance` returns
      `upcoming` alongside `statuses` → verify: local drill shows the field
- [x] **7. Put it on the screen.** Product page reads "meets the rules today,
      breaks a rule from 12 Jan 2027"; the alerts banner says a rule is coming
      and when. Status vocabulary stays in `web/app/_ui/status.tsx`
      → verify: `data-testid` present, `make test-all` builds the web app
- [x] **8. `make test-all` green** from a clean checkout → verify: pass/fail table
- [x] **9. Deploy and re-verify.** `gcloud builds submit` with a fresh
      `SHORT_SHA`, then the drill against the deployed stack
      → verify: a future-dated clause on the live stack does not flip today's
      status and does raise a scheduled alert
- [x] **10. Update the plan files** — phase 4 gets a line, `PROGRESS.md` gets a
      session-log entry → verify: files reflect what actually landed

### Added during the loop, not in the original plan

Both were needed to verify the feature rather than assert it.

- [x] `FAKE_LLM` reads an explicit `shall apply from YYYY-MM-DD` out of the
      document text. Without it the local stack cannot produce a future-dated
      clause at all, so the whole feature would only be testable against a paid
      model — which is the opposite of what `FAKE_LLM` is for
- [x] `upcoming_changes` names the rule that sets the deadline
      (`clause_id` / `document_id`, worst-evaluating rule starting that day).
      Found in review on the deployed stack: the scheduled alert had no cause,
      so the banner rendered “the rule behind this has since been removed” about
      a rule that exists. An alert that cannot name its cause is
      indistinguishable from one whose cause was deleted

### Out of scope for loop 1 — deliberately

- Inheriting `documents.declared_effective_date` onto a clause that has none
- Sunset dates (`effective_until`). Nothing extracts one today, so there is
  nothing to read

## Session log

- 30 Aug 2026 — file created; loop 1 analysed and planned, awaiting sign-off
- 30 Aug 2026 — scope widened on request to engine + API + UI + alert, verified
  to Cloud Run. Steps 1–8 written and green locally: 430 unit tests, ruff, tsc,
  next build, and the emulator drill with a new step for a rule that has not
  entered into force. Boxes stay unticked until the deploy in step 9, because
  `[x]` in this repo means deployed
- 30 Aug 2026 — first deploy (`a05be18-174121`) verified against the real model:
  it read `2027-01-12` out of prose, today's verdict held at
  `attention_required`, and `upcoming` reported `non_compliant` from that date.
  Review of that same run found the missing-cause defect above; fixed, retested,
  redeploying
- 30 Aug 2026 — loop 1 COMPLETE. Redeployed as `a05be18-175751` and verified
  live: the real model read `2027-01-12` out of prose, today's verdict held at
  `attention_required`, `upcoming` reported `non_compliant` from that date and
  named the clause and document that set it, and the scheduled alert came back
  with `cause_available: True` and the source's name. The test product and test
  document created for the check were both deleted (`200`), and `/alerts`
  returned to 5 with 0 scheduled
- 30 Aug 2026 — first drill run failed on my own step, not on the feature: it
  waited for a document status of `reconciled`, and nothing writes that —
  `extracted` is terminal. The verdict itself was right on the first run
  (Indonesia compliant today, `non_compliant` from 2027-01-12, one scheduled
  alert)
