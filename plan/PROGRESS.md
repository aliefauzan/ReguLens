# ReguLens — Progress Tracker

**Single source of truth for what is done.** Check here before starting any work.

Last updated: **19 Aug 2026** · Updated by: **planning session**

> **Read this first, every session.** If a phase below is `COMPLETE`, do not rebuild
> it — read its phase file to see what exists. If it is `IN PROGRESS`, the unticked
> boxes in that phase file are the remaining work.

## Legend

| Marker | Meaning |
|---|---|
| `[ ]` | Not done |
| `[x]` | Done, exists in the repo, and deployed |
| `[~]` | Deliberately skipped — the line says why. **Do not re-litigate.** |
| `NOT STARTED` / `IN PROGRESS` / `COMPLETE` / `SKIPPED` | Phase-level status |

A box is ticked only when the thing is real. Not "written in a doc", not "mostly
working locally". If it is not deployed and not verified, it stays unticked.

## Phases

| # | Phase | Planned | Status | Started | Completed |
|---|---|---|---|---|---|
| 0 | [Foundation](phases/phase-0-foundation.md) | Aug 19–20 | `IN PROGRESS` | 19 Aug | — |
| 1 | [Compliance Twin](phases/phase-1-compliance-twin.md) | Aug 21 | `IN PROGRESS` | 19 Aug | — |
| 2 | [Ingestion & Extraction](phases/phase-2-ingestion-extraction.md) | Aug 22–23 | `NOT STARTED` | — | — |
| 3 | [Guardrail & Reconciliation](phases/phase-3-guardrail-reconciliation.md) | Aug 24–25 | `NOT STARTED` | — | — |
| 4 | [Impact Engine](phases/phase-4-impact-engine.md) | Aug 26–27 | `NOT STARTED` | — | — |
| 5 | [Timeline & Query](phases/phase-5-timeline-query.md) | Aug 28–29 | `NOT STARTED` | — | — |
| 6 | [E2E Testing](phases/phase-6-e2e-testing.md) | Aug 30 | `NOT STARTED` | — | — |
| 7 | [Hardening & Submission](phases/phase-7-demo-hardening.md) | Aug 31 | `NOT STARTED` | — | — |

## Cross-cutting work

Tracked here because it spans phases and is easy to lose.

- [x] `trace_id` propagated end to end (phase 0) — API mints/adopts, publisher stamps, worker re-adopts; verified by a Cloud Logging query
- [x] Structured JSON logging everywhere, no `print` (phase 0, maintained throughout)
- [x] Cloud Build pipeline green, rollback practised (phase 0) — *manual trigger only; push trigger still to wire*
- [ ] Secret Manager wired, no secrets in image or repo (phase 0)
- [x] Budget cap + billing alert live (Rp 540,000 ≈ $30/month, 50/90/100%) — *email channel still needs the user to click Google's verification mail*
- [ ] `docker compose up` brings up the full local stack (phase 0)
- [ ] Five alerts configured **and each one deliberately triggered once** (phase 0 → 7)
- [ ] Debug view `/debug/documents/{id}` (phase 2, extended in 3 and 4)
- [x] `data-testid` attributes added as UI is built (phases 1–5) — started in phase 0's home page
- [x] Every repository mutation writes a `graph_event` (phase 1 onward) — same-batch write, no raw update exposed
- [ ] Every Pub/Sub handler idempotent, redelivery tested (phases 2, 3, 4)
- [ ] Extraction fixture set + accuracy test checked in (phase 2)
- [ ] `FAKE_LLM=1` fixtures covering the E2E suite — switch landed in phase 0; fixtures still to come in phase 6

## Decisions taken

Recorded so they are not reopened. Change one only with a reason written here.

- [x] **Google ADK required** — all four agents are ADK agents; tool bodies stay plain functions
- [x] **Pub/Sub + Cloud Run Jobs approved** — three topics, one per pipeline stage
- [x] **Cloud Build** for CI/CD, not GitHub Actions
- [x] **Secret Manager** for secrets; plain env vars for non-secret config
- [x] **Docker Compose** for local, with push subscriptions matching production
- [x] **Vertex topology** — infra in `asia-southeast1`, Gemini `gemini-3.5-flash` via the `global` endpoint, embeddings `text-multilingual-embedding-002` in `asia-southeast1`. Forced: `asia-southeast1` only offers `gemini-2.5-flash`, which fails the hackathon's 3.5+ rule
- [ ] **Cut Gemma?** — recommended yes. *Decision pending, see `../todo.md` §7*
- [ ] **Cut OCR fallback?** — recommended yes. *Decision pending, see `../todo.md` §7*
- [ ] **Readiness as counts, not percentage?** — recommended counts. *Pending*
- [ ] **Two GCP projects or one?** *Pending*
- [ ] **Repo public or private?** *Pending*

## Blocked on the user

Mirrors `../todo.md`. Nothing below can be unblocked by writing code.

- [x] Eligibility confirmed (country exclusions) — confirmed by user 19 Aug
- [ ] Devpost registration — **blocks submission**
- [x] GCP project ID + region + billing — `regulens-506014`, Owner confirmed, billing linked to `01B951-232B54-4E1D9A`. Infra region `asia-southeast1`; Vertex Gemini on the `global` endpoint
- [x] Gemini 3.5+ model identifier confirmed — `gemini-3.5-flash` on `global`, verified with a live `generateContent` call; embeddings `text-multilingual-embedding-002` in `asia-southeast1`, verified with a live call
- [x] Real EU + BPOM regulation PDFs with text layers — downloaded to `data/regulations/`, see `data/regulations/SOURCES.md`
- [x] Confirmation that the two jurisdictions' limits actually differ — sodium benzoate in flavoured drinks: EU 150 mg/kg vs BPOM 400–900 mg/kg. Exact BPOM row alignment still to be confirmed against the rendered table

## Session log

Append one line per working session. Keep it short — this is for orientation, not
a diary.

| Date | Who | What changed |
|---|---|---|
| 19 Aug 2026 | planning | Plan folder created; ADK + Pub/Sub + Cloud Build + observability + E2E phase incorporated |
| 19 Aug 2026 | corpus | Downloaded 5 real regulation PDFs (EU 1333/2008 original + two consolidated versions, EU 1129/2011 Annex II, BPOM 11/2019) into `data/regulations/`; text layers verified; divergence confirmed |
| 19 Aug 2026 | env audit | Verified user's todo answers: GCP project + Owner OK, GitHub repo public, gcloud/ADC OK; found billing disabled, Docker daemon down, Python 3.14 vs required 3.12; enabled `aiplatform.googleapis.com` |
| 20 Aug 2026 | repo hygiene | Rewrote the unpushed local history: `node_modules` and `.next/cache` (~150 MB, incl. an 88 MB binary) had been committed by an over-broad `git add -A`. Proper `.gitignore` written, nine commits collapsed into one clean commit, pushed |
| 19 Aug 2026 | phase 1 twin | Products collection, 20-substance normalization dictionary with EN/ID synonyms and E-numbers, unit parsing, event-writing repository, full product API, and the create/detail UI. Demo product created through the browser; `natrium benzoat` normalized to `sodium_benzoate`. Fixed a real CORS failure found by driving the form |
| 19 Aug 2026 | phase 0 web | Next.js 16 + Tailwind 4 home page rendering both markets from deployed Cloud Run; README written; uptime check on the public API; FAKE_LLM switch wired |
| 19 Aug 2026 | phase 0 build | API + worker + Job deployed to Cloud Run from one image via Cloud Build; markets seeded; Pub/Sub push round-trip proven with matching trace_id; ADK agent with a tool running on Cloud Run against gemini-3.5-flash; rollback practised |
| 19 Aug 2026 | phase 0 infra | `scripts/setup.sh` written and run: APIs, Artifact Registry, Firestore Native, GCS bucket, 4 Pub/Sub topics, 3 service accounts with narrow + bucket-scoped IAM. Push subscriptions deferred until the worker has a URL |
| 19 Aug 2026 | billing guard | $30 cap created as Rp 540,000/month (billing account is IDR-denominated) scoped to `regulens-506014`, thresholds 50/90/100%; email notification channel `7686068825666649291` for afindo.mi01@gmail.com, wired to the budget and reserved for the Phase 0 alerts |
| 19 Aug 2026 | vertex config | Billing linked by user. Found `asia-southeast1` carries only `gemini-2.5-flash` — fails the 3.5+ rule. Settled on infra in `asia-southeast1` + Gemini `gemini-3.5-flash` on the `global` endpoint + embeddings `text-multilingual-embedding-002` in `asia-southeast1`; all smoke-tested |
