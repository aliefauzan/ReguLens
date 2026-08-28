# Phase 7 — Demo Hardening & Submission

**Estimate:** 1 day (Aug 31) — includes the submission itself
**Demo sentence:** "Run one command, get the exact same demo, every time."

**Status:** `IN PROGRESS` · **Started:** 26 Aug 2026 · **Completed:** —

<!-- MAINTAIN THIS FILE.
     Set Status to IN PROGRESS when you begin, COMPLETE when every exit criterion
     is ticked. Fill the dates. Tick each `- [ ]` as it lands — a ticked box means
     it exists in the repo and is deployed, not that it is written down somewhere.
     If you deliberately skip an item, change it to `- [~]` and add ` — SKIPPED:
     reason` on the same line so nobody re-litigates it later.
     Then update ../PROGRESS.md. -->

## Goal

Make the demo reproducible, resettable, survivable, and recorded. A working system
that fails once on stage scores worse than a smaller system that never does.

## Scope

### Reproducible state
- [ ] **Cloud Run Job** `seed` that wipes the demo workspace and rebuilds the
      baseline. A Job is the right home for this: batch, no HTTP, re-runnable from
      the console mid-demo. `POST /admin/seed` triggers it for convenience.
- [ ] Second Job mode `reprocess`: re-run extraction over stored documents after a
      prompt change, without re-uploading. This saves real time during the last
      two days.
- [ ] The baseline:
      markets seeded, demo product created, BPOM 0.10% clause ingested and active,
      Indonesia evaluating `compliant`, Germany `unknown` or `compliant` per the
      chosen narrative.
- [ ] The EU 0.05% document stays **un-ingested** — that upload is the demo's
      inflection point.
- [ ] Seeding is idempotent and takes under 30 seconds.
- [ ] Fixture documents committed to the repo so seeding needs no network fetch of
      third-party files.

### First-run self-service (added 26 Aug)

The plan's "Out of scope" line below says *onboarding flows*. That was written
assuming the demo is always driven by us. It is not: a judge opens the hosted URL
cold, with no product, no regulation PDF, and nobody to ask. Two hours of
onboarding is cheaper than a judge who reaches an empty page and leaves. Scope is
deliberately minimal — no tour, no coach marks, no modal.

Verified on the local docker-compose stack. **Not yet redeployed to Cloud Run.**

- [x] `GET /samples` — regulation excerpts bundled in the image (`app/core/samples.py`),
      quoted verbatim from the corpus with their citations. Needed because only
      `app/` is copied into the container, so `data/regulations/` is not there.
- [x] `POST /demo/seed` — creates the demo product and ingests the BPOM rule
      **through the normal async path** (Pub/Sub → worker), so the button exercises
      the real pipeline rather than writing state directly. Returns 202 while
      extraction runs, 200 when an identical seed already exists.
- [x] Seeding idempotent twice over: product matched by name, document by content
      hash. Pressed twice → same product id, same document id, one product.
- [x] The EU rule stays un-ingested by the seed, so the inflection point is still
      the user's own upload — now available as a one-click sample.
- [x] Home page: "Try it with sample data" on an empty workspace, landing on the
      document page while extraction runs (landing on the product would show
      "no rules added yet" and read as a broken button).
- [x] Add-rules page: sample picker fills the form (source type, publisher,
      jurisdiction, text) and the user still presses the button.
- [x] Three-step checklist persists until all three steps are genuinely done,
      computed from real state — a product exists, a document reached `extracted`,
      a market reads something other than `unknown`. It previously vanished the
      moment the first product existed, taking step two with it.
- [x] `tests/test_samples.py` — nine tests pinning the thing the samples claim:
      EU excerpt yields 150, BPOM yields 400, the two disagree, the demo product's
      300 mg/kg sits between them, and every demo ingredient normalizes.
- [ ] Redeploy api + web to Cloud Run so the hosted URL has the seed button.

### Self-service, round two (28 Aug)

Same question as the first round — what still needs a person standing next to
the user — answered for the seven things left. Local stack only; **Cloud Run
redeploy still pending**.

- [x] **Honest waiting.** The upload button said "about a minute" against a
      measured 183s. Both places now say three minutes, and the document page
      carries a live clock against that estimate plus a distinct
      "taking longer than usual" state past five minutes.
- [x] **Correct a product.** `ProductForm` serves both create and edit;
      `/products/{id}/edit` uses the existing `PATCH /products/{id}`, which had
      no caller. Editing opens on the ingredient rows, not the paste box.
- [x] **Delete a product.** `DELETE /products/{id}` plus `delete_with_event` in
      the repository, so the cascade over derived requirements and the
      `product_deleted` event are written in one batch. Confirmation names what
      goes.
- [x] **Reject a clause.** `POST /clauses/{id}/dismiss` and a second button in
      the review queue. `dismissed` is terminal and inert; the record and its
      event survive.
- [x] **A number to act on.** A failing requirement now says what to bring the
      amount down to, and names the stricter market when meeting one meets both.
- [x] **Counts on the navigation bar**, refreshed on navigation and on any queue
      action. Phone keeps four tabs — five labels do not fit.
- [x] **`/rules`** — every clause in one list with why each does or does not
      count. Previously a clause was only visible inside its own document.
- [x] **Glossary** (`_ui/Term.tsx`) for jurisdiction, clause, authority,
      confidence, supersede, conflict, requirement.
- [x] Ask suggestions built from the product's own markets and failing market.
- [x] Missing ingredient amounts link to the edit form; "1 ingredients" fixed.

Three real defects surfaced by building these, all fixed here:

- [x] **A corrected amount never reached the requirement row.** The idempotency
      check compared only `{limit_value, evaluation, severity, clause_id}`, so
      an edit that did not flip the verdict wrote nothing and the page kept
      quoting the old amount under the new limit. Now compares every field the
      UI shows (`REPORTED_FIELDS`), with `tests/test_requirement_change.py`
      pinning it — including a test that every reported field is watched, which
      is what would have caught both this and the earlier `product_value` bug.
- [x] **`confirm_clause` never republished.** `_publish_graph_changed` ran on
      the `None` branch, which was the *failure* path, so accepting a clause in
      the review queue promoted it and then did not re-evaluate anything. Both
      confirm and dismiss now return explicit outcomes, and a missing clause is
      a 404 instead of a cheerful 200.
- [x] **Alerts outlived their product.** `GET /alerts` filtered nothing, so a
      deleted product left an alert linking to a 404. Events stay in the audit
      trail; they are no longer presented as needing attention.

### Plain-language pass (28 Aug)

A walk through every page as somebody who does not work here. Nine things were
confusing enough to stop a reader; all fixed, all rechecked in the browser at
phone width in both themes.

- [x] **"Where this came from" showed a bare `clause_2da66be9e735`** on four
      pages — the one thing a reader cannot use, shown exactly when they are
      deciding whether to trust the number above it. One `_ui/Provenance.tsx`
      now names the document, the country, and links to it; the id survives one
      line down, labelled as a reference for quoting to us.
- [x] **The review queue never said why anything was waiting.** The UI read
      `review_reasons` (a list the extractor writes) while the guardrail writes
      a single `review_reason`, so every card showed an empty bullet list. Both
      are read now, `low_confidence_or_flagged` has words, and each card says
      what it was read from and how sure we are.
- [x] **Answers quoted clause ids inline.** That is the grounding contract — the
      model must cite `[clause_id]` and an uncited answer is refused — but it
      reads as noise. Ids are renumbered against the citation cards, so the
      grounding is unchanged and the sentence is readable. "answered in 19 ms"
      became "answered straight away".
- [x] **404 was the Next.js default** with no way back. Now says what happened,
      says the data is fine, and offers two doors.
- [x] **The document page was titled "Reading your document" over a raw id**,
      even long after it finished. Titled with the document's own name now, and
      the copy changes once reading is done.
- [x] **A document could say "Finished" over a rule nobody had accepted.** Each
      rule found now carries its standing (in use / waiting for you / replaced /
      ignored), and the finished panel says how many still need a person, with
      a link to the queue.
- [x] **History was unreadable**: no dates, a raw trace-id fragment on every
      row, and rows reading "No rules added yet → No rules added yet" (a real
      `null → unknown` difference in the data, the identical sentence on
      screen). Filtered on the rendered label, timestamps in plain words, trace
      fragment gone.
- [x] **Server validation spoke schema.** "Input should be 'percent_w_w',
      'mg_per_kg' or 'ppm'" became "Pick one of these for the unit on row 2:
      % of weight, mg per kg, ppm" (`humanizeValidation`).
- [x] **Smaller ones:** requirement rows sorted worst-first (a labelling note
      sat above the ingredient that actually failed); a waiting rule on `/rules`
      now has a button to act on it; generated `doc_x.txt` filenames read as
      "pasted text".
- [x] The local canned answer picked whichever clause came back first, so
      "why does this break the rules in Germany?" was answered with Indonesia's
      limit. `_fake_pick` now matches the country in the question, then any
      failing rule. Two tests pin it. FAKE_LLM never runs in production, but it
      is the whole of what anyone evaluating the local stack reads.

### Second recheck (28 Aug)

A sweep of every route for machine vocabulary — a script reading each rendered
page for ids, `snake_case`, `null`, and millisecond readouts. What it found:

- [x] **A document with no usable rules never finished.** `completedStages`
      read an empty clause list as "not settled yet", so the stepper span on
      stage three of four forever for anyone who uploaded something that turned
      out not to be a regulation. That is an ordinary mistake, not a failure,
      and the page now says so — and stops printing "Rules found" and
      "Everything we found is listed below" over an empty list.
- [x] `dismissed`, `pending_reconciliation` and the three evaluation reasons
      added to the one vocabulary map, so nothing falls through to
      `snake case with the underscores swapped for spaces`.
- [x] Sweep now comes back clean: the only ids left on any page are the ones
      inside a collapsed "Where this came from", labelled as the reference to
      quote to us.

### Failure survival
- [ ] Every async stage has a timeout and a visible failure state in the stepper.
- [ ] Confirm the five alerts from `../04-observability.md` are firing correctly by
      triggering each one deliberately. An alert you have never seen fire is not an
      alert.
- [ ] Confirm the Cloud Build rollback command works — practise it once.
- [ ] Retry button on failed documents, tested by forcing a failure.
- [ ] If Vertex AI is unreachable, the API returns a clear error and the UI says so
      — no infinite spinner, no silent empty state.
- [ ] Pre-warm endpoint or a scheduled ping so the demo never hits a cold start.
- [ ] Extraction cache verified: re-uploading the demo PDF during rehearsal must
      not re-bill or change results.

### Honesty pass
- [ ] Audit every screen for implied capability the system does not have:
      no fake percentages, no invented regulation text, no "monitoring" language for
      things that only run on upload.
- [ ] Any synthetic fixture document is labelled synthetic in the UI.
- [ ] `needs_review` states are visibly distinct from `pass` — this is a feature to
      show off, not a blemish to hide.

### Presentation polish (time-boxed, half a day maximum)
- [ ] Consistent status colour language across readiness, alerts, and timeline.
- [ ] The impact chain visual and the before/after diff get the most attention —
      they carry the pitch.
- [ ] Loading states everywhere something takes over 300ms.
- [ ] Mobile is *not* a goal; make sure it does not crash, then stop.

### Recording and fallback
- [ ] Full demo recorded end to end, unedited, as a fallback for live failure
      (footage captured in phase 6).
- [ ] Screenshots of the six key screens for the submission.
- [ ] Demo run timed; confirm the < 90s propagation target from the PRD.

### Submission package (see `../03-hackathon-compliance.md`)
- [ ] **README with reproducible spin-up instructions** — explicitly required by the
      rules. Prerequisites, env vars, `gcloud` setup, one command local, one command
      deploy. Have someone else follow it cold.
- [ ] **Architecture diagram as an image** — required. Render the topology from
      `01-architecture.md`. ASCII in a README does not satisfy this.
- [ ] **~4-minute demo video that proves the backend runs on Google Cloud.** Not
      only the UI. Budget ~40 seconds to show the Cloud Run services, a Pub/Sub
      subscription delivering, and Firestore documents changing live. Compress
      `../99-demo-script.md` from 3m30s to ~3m10s to make room.
- [ ] Text description: features, technologies, **data sources** (name the actual
      regulations used), and learnings.
- [ ] Hosted URL live and verified from a browser that has never seen it.
- [ ] Repo pushed; if private, confirm judge access.
- [ ] Devpost submission form completed and **submitted at least 12 hours early**.
      Upload failures at a deadline are ordinary, not unlucky.
- [ ] Optional bonus: short blog or social post on the "deterministic code gates the
      model" principle. Write it while a build or render is running.

### Documentation
- [ ] Root `README.md` also carries an explicit **Limitations** section listing what
      is out of scope. Stating limits raises credibility rather than lowering it.
- [ ] Include the "what we did not build" table from `01-architecture.md` — under a
      30%-weighted Architectural Discipline criterion, documented restraint is
      scoreable work, not an apology.

## Exit criteria

- [ ] `seed` Job → run the full demo → `seed` again → identical starting state.
- [ ] The demo has been performed end to end, live, three times without intervention.
- [ ] The 4-minute video is recorded, includes the Google Cloud proof segment, and is
      uploaded.
- [ ] Architecture diagram image exists and matches what was actually built.
- [ ] A third party can follow the README spin-up instructions successfully.
- [ ] Every row in `../03-hackathon-compliance.md` is checked off.
      The phase-6 suite is still green against the final deployed build.
- [ ] Devpost submission is complete, ≥ 12 hours before 31 Aug 5:00pm PDT.
- [ ] Budget/quota headroom confirmed.

## Out of scope

Load testing, monitoring dashboards, error tracking integration, analytics,
marketing site. *Onboarding flows were out of scope until 26 Aug; see "First-run
self-service" above for why the minimal case came back in.*

## Risk notes

- Do not start new features in this phase. The most common phase-6 failure is
  "just one more thing" breaking a working demo the night before.
- Rehearse on the deployed environment, not locally. Local success proves nothing
  about the URL a judge will open.
- The video is the artifact most teams underestimate. A 4-minute video takes far
  longer than 4 minutes to produce. **Record the raw footage during phase 6** while
  the E2E runs are green; Aug 31 is for editing, not for discovering a broken take.
- This phase has **zero schedule slack** (see `../README.md`). If phase 5 overruns,
  cut phase 5 scope, not phase 6 — an unsubmitted project scores nothing.
