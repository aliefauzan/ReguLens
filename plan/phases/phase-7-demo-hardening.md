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
