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
| 2 | Strictest-wins across markets | `COMPLETE` | Conflicts are detected, never resolved into a number to ship against |
| 3 | Long-document map-reduce extraction | `COMPLETE` | The BPOM annex is a permanent refusal |
| 4 | Latency by chunk-level fan-out | `COMPLETE` (merged into 3 — same mechanism) | 174.3s vs a 90s target on a 55-clause annex |
| 5 | Alerts that leave the building | `COMPLETE` (webhook; email skipped, reason below) | No email/Slack/webhook anywhere in `api/app` |
| 6 | Measured accuracy, not a smoke test | `COMPLETE` | 5/5 on fixtures is not precision/recall |
| 7 | Auditor evidence pack | `COMPLETE` | Every input already exists in `graph_events` + `citations.py` |
| 8 | What-if simulation | `COMPLETE` | Read-only reuse of `impact.evaluate()` |

> **30 Aug 2026 — the whole backlog was commissioned in one go.** Items 2–8 are
> being worked in dependency order: 2 and 8 share the evaluator, 3 and 4 share
> the chunking, and 5, 6 and 7 are independent. One deploy at the end rather
> than one per item.

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


---

## Loops 2–8 — the rest of the backlog, 30 Aug 2026

Commissioned in one go and worked in dependency order. One deploy at the end.

### Loop 2 — strictest-wins across markets · `COMPLETE`

`core/strictest.py`. The graph could already say "the EU allows 150 and
Indonesia allows 400, and those disagree". A company with one recipe and two
markets cannot act on that sentence. Per substance, the lowest limit **still in
force** across the markets the product actually targets, which jurisdiction sets
it, and whether the product meets it.

- [x] Computed on read, never stored, so it cannot go stale — same rule as
      `relevance.py`
- [x] Only in-force rules count, so it agrees with loop 1 rather than contradicting it
- [x] The spread is shown beside the winner: a single number asks to be trusted
- [x] Markets with **no** rule for the substance are named — "strictest of the
      markets that regulate it" and "strictest of everywhere you sell" are
      different claims and only the first is true
- [x] Rules that cannot be compared as numbers are counted, not dropped
- [x] Ties break on market id, so two reads of unchanged data cannot disagree
- [x] 11 tests; on `/products/{id}/compliance`; on the product page

### Loop 3 + 4 — long documents, and the latency they cost · `COMPLETE`

These turned out to be one problem, and the measurement already in phase 4 said
why. Chunking and in-request concurrency **already existed**
(`pipeline._direct_pairs`), and phase 4 recorded that splitting did not move the
number because the annex was dense, not long. The real wall is elsewhere and it
is hard: **the worker answers a Pub/Sub push inside 300 seconds.**

So raising the size refusal on its own would have converted a *named refusal*
into an *unexplained timeout*, which is strictly worse. The fix is one message
per piece, each with its own request budget.

- [x] `core/extraction/fanout.py`: plan → publish one `document.chunk` per piece
      → each piece stores its own candidates → the last one reduces
- [x] Additive by construction: the decision reads `char_count` stored at
      upload, so a normal document never pays a text extraction to answer it and
      **takes exactly the path it took before**
- [x] A piece delivered twice overwrites itself (keyed by index)
- [x] Two pieces finishing at once: the reduce is claimed in a Firestore
      transaction, exactly one wins
- [x] A piece that never arrives leaves the document unfinished with a count,
      rather than producing clauses from the parts that happened to land
- [x] Self-consistency still scored *inside* a piece, never across — two samples
      of page one agreeing means something, page one agreeing with page four
      means nothing
- [x] `max_fetch_chars` raised 200,000 → 400,000, now that a document that long
      is read rather than refused. Still a refusal above it, never a truncation
- [x] `extraction_max_chunks` (60) refuses a document that would spend an hour
      of model calls, and says so in words
- [x] New topic wired into `scripts/setup.sh` and `scripts/pubsub_init.py`
- [x] 7 tests covering the three at-least-once hazards

### Loop 5 — alerts that leave the building · `COMPLETE`

`core/notifications.py`, delivered from the worker after impact runs.

- [x] One channel kind: an HTTP POST of JSON, which is what a Slack or Discord
      incoming webhook is
- [x] Off unless `ALERT_WEBHOOK_URL` is set — a webhook URL is a credential and
      nothing should be posted anywhere by accident
- [x] Delivery marked on the causing event, so at-least-once redelivery does not
      send twice
- [x] A failed send is logged and left unmarked for retry: a channel that
      quietly stops working is worse than one never configured
- [x] Capped per run, so a first ingestion cannot flood a channel into being muted
- [x] A channel being down never fails the pipeline run that produced the verdict
- [x] 7 tests
- [~] Email — **SKIPPED: it needs an SMTP provider and a verified sender, neither
      of which exists here. Shipping an untested mail path would be a claim, not
      a feature. The webhook covers Slack, Discord and anything that accepts a
      JSON POST.**

### Loop 6 — measured accuracy, not a smoke test · `COMPLETE`

"5/5 on fixtures" was never accuracy: it stopped at the first candidate that
matched and never counted the wrong ones beside it. A stage emitting the right
answer plus four inventions scored 5/5.

- [x] `core/evaluation.py` — precision, recall, F1 over sets; per-label scoring;
      a table that prints `n` on every row, because a precision without its
      sample size is a number pretending to be evidence
- [x] Predicting nothing scores 0, not 1 — dividing by zero and calling silence
      flawless is the exact failure being fixed
- [x] The scorer has its own tests (7), because a quietly wrong scoring function
      makes every number downstream wrong and confident
- [x] Hand-labelled sets in `tests/fixtures/labels/` for the guardrail, unit
      conversion and the evaluator — the stages that actually decide a verdict,
      all deterministic and free
- [x] `make eval`, and a row in `make test-all` that prints the table
- [x] The live extraction test now counts false positives and asserts precision,
      not just recall
- [x] **The harness found something on its first run** — a `g_per_kg` label. It
      was the *label* that was wrong: the system accepts three units and
      refusing an unknown one is correct. Relabelled as the refusal case it is
- [ ] Live extraction precision has **not** been re-measured this session — it
      needs `REGULENS_EVAL=1` and real model calls

### Loop 7 — auditor evidence pack · `COMPLETE`

`core/evidence.py`, `GET /products/{id}/evidence`, a button on the product page.

- [x] Per verdict: the rule as the regulator wrote it, its confidence and its
      breakdown, the source document, when it was read, and the stored
      `content_sha256` proving the file behind the quote is the file that was read
- [x] The comparison in both forms — 0.03% *and* 300 mg/kg — so a reader checks
      arithmetic instead of trusting a badge
- [x] The stored audit trail, not a narrative assembled for the document
- [x] A verdict whose clause or document was deleted is **marked, not dropped**,
      and counted in `coverage`
- [x] The pack states what it is not: not signed, only what ReguLens read, and
      `needs_review` is not an assertion of compliance
- [x] Hashes itself, and is checked to survive being written to a file
- [x] 7 tests

### Loop 8 — what-if simulation · `COMPLETE`

`core/simulation.py`, `POST /simulate`, `WhatIfPanel` on the product page.

- [x] Writes nothing: no document, no event, no requirement row — pinned by a
      test that makes `write_with_event` raise
- [x] Shares `clause_binds` and `evaluate` with the impact engine. A preview
      that picked its own rules would eventually disagree with the page it
      previews, and a disagreeing preview is worse than none
- [x] Returns the strictest-wins ceiling too, so the answer is "cut it to 120 and
      you may ship in both" rather than a pair of badges
- [x] `clause_binds` extracted from `materialize_for_product` so the two cannot
      drift — the only refactor in this batch, and it exists for that reason
- [x] 8 tests
