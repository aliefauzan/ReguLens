# ReguLens — Progress Tracker

**Single source of truth for what is done.** Check here before starting any work.

Last updated: **28 Aug 2026** · Updated by: **self-service round two**

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
| 0 | [Foundation](phases/phase-0-foundation.md) | Aug 19–20 | `IN PROGRESS` (web hosting moved to Cloud Run; Vercel dependency gone) | 19 Aug | — |
| 1 | [Compliance Twin](phases/phase-1-compliance-twin.md) | Aug 21 | `IN PROGRESS` (frontend now deployed on Cloud Run web service) | 19 Aug | — |
| 2 | [Ingestion & Extraction](phases/phase-2-ingestion-extraction.md) | Aug 22–23 | `COMPLETE` | 22 Aug | 23 Aug |
| 3 | [Guardrail & Reconciliation](phases/phase-3-guardrail-reconciliation.md) | Aug 24–25 | `COMPLETE` | 23 Aug | 23 Aug |
| 4 | [Impact Engine](phases/phase-4-impact-engine.md) | Aug 26–27 | `COMPLETE` (183s latency honestly recorded vs 90s target) | 23 Aug | 23 Aug |
| 5 | [Timeline & Query](phases/phase-5-timeline-query.md) | Aug 28–29 | `COMPLETE` (10/10 grounding check live) | 23 Aug | 23 Aug |
| 6 | [E2E Testing](phases/phase-6-e2e-testing.md) | Aug 30 | `IN PROGRESS` (UC-A..F + redelivery/concurrency/DLQ/walker/grounding all live-green; formal Playwright shell left) | 23 Aug | — |
| 7 | [Hardening & Submission](phases/phase-7-demo-hardening.md) | Aug 31 | `IN PROGRESS` (self-service done; local only, Cloud Run redeploy pending) | 26 Aug | — |

## Cross-cutting work

Tracked here because it spans phases and is easy to lose.

- [x] `trace_id` propagated end to end (phase 0) — API mints/adopts, publisher stamps, worker re-adopts; verified by a Cloud Logging query
- [x] Structured JSON logging everywhere, no `print` (phase 0, maintained throughout)
- [x] Cloud Build pipeline green, rollback practised (phase 0) — *manual trigger only; push trigger still to wire*
- [ ] Secret Manager wired, no secrets in image or repo (phase 0)
- [x] Budget cap + billing alert live (Rp 540,000 ≈ $30/month, 50/90/100%) — *email channel still needs the user to click Google's verification mail*
- [x] `docker compose up` brings up the full local stack (phase 0) — verified 25 Aug;
      `scripts/verify_local.sh` runs the whole drill offline, free, in ~2 minutes
- [ ] Five alerts configured **and each one deliberately triggered once** (phase 0 → 7)
- [x] Debug view `/debug/documents/{id}` (phase 2, extended in 3) — behind
      `DEBUG_VIEW`, live: stage_log, rejected candidates, reconciliation
      decisions, confidence components
- [x] Frontend hosting on Cloud Run (`regulens-web`) — Vercel unblocked; CORS
      pinned to the web origin in cloudbuild.yaml
- [x] `data-testid` attributes added as UI is built (phases 1–5) — started in phase 0's home page
- [x] Every repository mutation writes a `graph_event` (phase 1 onward) — same-batch write, no raw update exposed
- [x] Every Pub/Sub handler idempotent, redelivery tested — extract, reconcile
      and impact all verified against the deployed stack; the concurrent
      probe additionally caught and fixed a double-race hole
- [x] Extraction fixture set + accuracy test checked in — verbatim corpus
      excerpts, live-Vertex run gated behind `REGULENS_EVAL=1`, result 5/5
- [~] `FAKE_LLM=1` fixtures covering the E2E suite — SKIPPED as a separate fixture set: `llm.fake_candidates` is now keyed on the document's own text (Indonesian source → 400 mg/kg, EU source → 150 mg/kg), which is enough to drive the entire local E2E drill including the conflict and the flip. A second fixture layer would duplicate it

## Decisions taken

Recorded so they are not reopened. Change one only with a reason written here.

- [x] **Google ADK required** — all four agents are ADK agents; tool bodies stay plain functions
- [x] **Pub/Sub + Cloud Run Jobs approved** — three topics, one per pipeline stage
- [x] **Cloud Build** for CI/CD, not GitHub Actions
- [x] **Secret Manager** for secrets; plain env vars for non-secret config
- [x] **Docker Compose** for local, with push subscriptions matching production
- [x] **Vertex topology** — infra in `asia-southeast1`, Gemini `gemini-3.5-flash` via the `global` endpoint, embeddings `text-multilingual-embedding-002` in `asia-southeast1`. Forced: `asia-southeast1` only offers `gemini-2.5-flash`, which fails the hackathon's 3.5+ rule
- [x] **Cut Gemma?** — **Cut, 22 Aug.** Optional bonus; nothing depends on it. `prefilter_sections` tool slot stays empty rather than half-built.
- [x] **Cut OCR fallback. Cut, 22 Aug.** Text-layer PDFs + pasted text only; a near-empty text layer scores low `parse_quality` and the clause lands in review instead of inventing content
- [x] **Minimal onboarding is in scope, 26 Aug** — phase 7 listed "onboarding flows" as out of scope, written on the assumption that we always drive the demo. A judge opens the hosted URL cold with no product and no regulation PDF. So: bundled sample regulations, a one-click demo seed, and a three-step checklist that persists until done. No tour, no coach marks, no modal — those stay out
- [x] **Readiness as counts, not percentage?** — Counts (phase 4 will render issue counts). *User confirmation still welcome; nothing built contradicts it*
- [x] **Two GCP projects or one?** — **One** (`regulens-506014`), as already provisioned 19 Aug
- [x] **Repo public or private?** — **Public**, verified public on GitHub 19 Aug
- [x] **Composite confidence weights** (22 Aug) — `0.3·parse_quality + 0.4·self_consistency + 0.3·authority_tier`, from the concept doc's model. Self-consistency = best-match field agreement between the two Gemini samples over substance/limit/unit/product_type
- [x] **Decision events belong to reconciliation** (22 Aug) — phase 2 persists clauses as `pending_reconciliation` with no `clause_created` event; phase 3's verdict application writes exactly one of {created, superseded, conflict_opened, flagged_review} per clause. Keeps one-decision-one-event true and UC-D's zero-mutation assertion meaningful
- [x] **Upload cache key** (22 Aug) — identical bytes short-circuit when the prior document reached a terminal state (`extracted`/`reconciled`), not only `reconciled`; otherwise the cache could never hit before phase 3 exists
- [x] **Real corpus numbers override the sketch numbers** (23 Aug) — EU Annex II 14.1.4 is 150 mg/kg for E210-213; BPOM 14.1.4.x reads 400–900 mg/kg. Extraction follows the documents; the "0.05% vs 0.10%" pair stays a demo-narrative baseline seeded in phase 7, never presented as extracted fact
- [x] **Substance-family equivalence** (23 Aug) — EU limits the group "Benzoic acid — benzoates (E210-213)"; BPOM limits natrium benzoat computed "as benzoic acid". The guardrail compares across that documented shared basis (`_SUBSTANCE_FAMILIES` in `core/guardrail.py`); retrieval and requirement materialization use the same families. Not a guessed mapping — both documents state it
- [x] **Cross-jurisdiction conflict decided in code, not by the judge** (23 Aug) — different jurisdictions with different limits is deterministically a conflict; the judge is consulted ONLY for same-jurisdiction pairs whose effective dates do not settle the supersede question
- [x] **Unique image tags per deploy** (23 Aug) — Cloud Run skips revision creation on an unchanged tag, so builds pass `SHORT_SHA=<sha>-<HHMMSS>`; a plain git short-SHA silently redeploys nothing
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
| 23 Aug 2026 | phases 2–5 + deploy | Phases 2–5 built AND live-verified in one push. Phase 2 `COMPLETE` (5/5 fixture accuracy on live Vertex). Live E2E green: baseline compliant→upload EU excerpt PDF→conflict opens (UC-C)→**Germany flips non_compliant unprompted** (UC-B)→alert fires→grounded query cites 2 real clauses→Japan refusal honest→cache hit→redelivery no dupes. Fixed en route: SERVER_TIMESTAMP-in-ArrayUnion, transaction.get generator API, empty clause ids published, missing clause jurisdiction/unit fields, substance-family equivalence (benzoates), judge scope narrowed to genuinely ambiguous same-jurisdiction pairs, throwaway genai clients closed (shared cached client), unique image tags per deploy. Web deployed to Cloud Run (`regulens-web`); Vercel dependency dropped; taste-skill design pass (tokens, Geist, single accent, dark/light). 62 tests green, lint clean |
| 23 Aug 2026 | drills | Two more live drills banked. **UC-D**: social-chat source produced a needs_review clause at confidence 0.47 (<0.5) with ZERO mutations to conflicts or statuses — authority tiering is demonstrably real. **Same-jurisdiction supersede**: BPOM amendment (350 mg/kg eff. 2026-12-01) superseded the active 400 mg/kg clause live (`superseded` + `superseded_by`). Two latent bugs found and fixed by these drills: cross-jurisdiction conflicts now only open against ACTIVE partners (a needs_review counterpart must not gain state), and a dominant conflict verdict no longer silently drops valid supersede findings — both findings apply |
| 23 Aug 2026 | drills + close-out | Phase 3/4/5 → COMPLETE. Drills: DLQ→failed→retry recovered live; audit-integrity walker green over live data; concurrent-delivery probe found+fixed a double-race hole; UC-F second-product propagation proven; 10/10 grounding check. Log metrics `regulens_judge_invoked` + `regulens_guardrail_rejected` created. Web: impact-chain banner + red worsening-transition highlight. Honest gap recorded: upload→flip measured 183s vs 90s target (double ADK sampling dominates). Remaining open: Cloud Build push/PR triggers (needs GitHub-app OAuth by user), docker compose (daemon down, user-deferred), formal Playwright shell, phase-7 user items |
| 25 Aug 2026 | local stack + UI | Full local stack now real and verified: `LOCAL_STORAGE_DIR` filesystem backend in `app/storage.py` (no Cloud Storage emulator exists) with the two direct-GCS readers routed through it, `FIRESTORE_DATABASE=local` for the emulator, `API_INTERNAL_URL` for server components, tracing disabled locally, jurisdiction-aware `fake_candidates`. `scripts/verify_local.sh` runs the whole drill offline: baseline → EU upload → conflict → unprompted Germany flip → alert → cache hit → redelivery-no-duplicates, all green with zero GCP calls. Web redesigned against Apple HIG for a non-technical first-time user: system type scale and colour set, translucent nav plus mobile tab bar, 44px targets, one `_ui/status.tsx` that translates every machine word once, "Start here" first-run guide, per-market verdicts on the home cards, conflicts page joined to clause text and country, plain-language failure copy. Google-font fetch dropped (system stack) so the web builds offline. 62 tests green, ruff clean, tsc clean |
| 25 Aug 2026 | UI readability pass | Audited every page at real size, light and dark. Same three defects everywhere: 13px at 60% opacity for content that had to be read, tiny grey uppercase labels doing the job of headings, clause ids in the reader's face. Fixed at the token level — solid secondary/tertiary colours chosen for contrast, 15px floor for readable text, 13px reserved for ids and coloured tertiary by definition, 20px section headings, 62ch prose measure. Requirement rows and conflict sides now show the deciding comparison as two large figures (your amount vs the limit) instead of a faint aside; ids moved behind a "Where this came from" disclosure. Home became full-width product rows with per-market tiles and a consistent alert action row. Also fixed a stepper that sat on "working…" forever: a document's status stops at `extracted` because reconciliation is per-clause, so the last stage is now derived from clause statuses and the two trailing stages collapsed into one. tsc clean, production build green |
| 25 Aug 2026 | UI round 3 | Three user-reported problems fixed. (1) Controls were different heights in the same row — an `<input>` takes its height from body line-height while a `<select>` uses the browser's, so `min-height: 44px` produced 47px and 44px side by side; every single-line control is now a fixed 48px with the native appearance removed and one themed chevron. (2) Nobody knew what to do on opening the app: home now leads with a "What to do next" card computed from real state in the order the work has to happen (broken rule → market with no rules → things to check → disagreements → all clear), and the alert list collapsed to one line each so it stops competing with it. (3) Ingredient entry was a chore: a paste-the-label mode parses a pasted list into editable rows (conservative — a number only fills in when the text is unambiguous, an unconvertible unit says so on the row), plus autocomplete from a new `GET /substances` endpoint over the normalization dictionary so users pick names that can actually match a clause. Found and fixed a real reporting bug on the way: `product_value` was rendered against the *clause's* unit, showing "0.02 mg per kg" for an ingredient given as 0.02% — impact now persists `product_unit` and the converted `comparable_value`/`comparable_limit`, and the UI shows both sides in one unit. 62 tests green, ruff clean, tsc clean, build green |
| 26 Aug 2026 | first-run self-service | Answered "what stops a user without a tutor" by building the two blockers. (1) A cold workspace demanded a regulation PDF the user does not have: `app/core/samples.py` now carries verbatim EU 1129/2011 and BPOM 11/2019 excerpts with citations, served by `GET /samples` and offered as a one-click filler on the Add-rules page; `POST /demo/seed` creates the demo product and ingests the Indonesian rule through the real Pub/Sub path (202 while extracting, 200 on repeat), idempotent by product name and content hash. The EU rule stays for the user to add, so the verdict flip is still theirs to watch. (2) The three-step guide only rendered on a completely empty workspace, so it vanished the moment the first product existed and took step two with it: it is now a checklist computed from real state (product exists / a document reached `extracted` / a market reads something other than `unknown`) that stays until all three are done, and the "What to do next" card holds back until then rather than competing with it. Seed lands on the document page, not the product, because a product page during extraction says "no rules added yet" and reads as a broken button. `job.py` de-duplicated against the new samples module. Verified from a wiped stack in the browser: empty → seed → BPOM extracted → EU sample → Germany flips `non_compliant`, one conflict open. 71 tests green (9 new), ruff clean, tsc clean, next build green. Cloud Run redeploy still pending |
| 28 Aug 2026 | self-service round two | Closed the remaining seven things a user could not do without asking someone. Editing and deleting a product (`ProductForm` now serves both, `/products/[id]/edit` finally calls the `PATCH` that had no caller, `DELETE /products/{id}` cascades derived requirements through a new `delete_with_event` so the audit event and the deletes land in one batch). Rejecting a clause (`POST /clauses/{id}/dismiss`; `dismissed` is terminal and inert, the record survives). Honest waiting: the upload button claimed "about a minute" against a measured 183s — both places now say three minutes and the document page runs a clock against it with a separate "longer than usual" state. A failing requirement says what number to get under, and names the stricter market when meeting one meets both. Nav badges for the two queues, refreshed on navigation and on queue actions; phone stays at four tabs because five labels do not fit. New `/rules` page listing every clause and why it does or does not count. `_ui/Term.tsx` glossary. Ask suggestions built from the product's own markets. Three defects found by building this and fixed: (1) a corrected ingredient amount never reached the requirement row because the idempotency check watched only limit/evaluation/severity/clause — the page kept quoting the old amount; now every displayed field is watched, with a test asserting exactly that; (2) `confirm_clause` republished on its failure branch, so accepting a clause in the review queue re-evaluated nothing, and a missing clause returned 200; (3) alerts outlived deleted products and linked to a 404. 78 tests green (7 new), ruff clean, tsc clean, build green. Verified in the browser end to end: seed, edit an amount and watch both markets re-read, dismiss from the queue, delete with the cascade, watch the stepper clock on a stalled worker |
