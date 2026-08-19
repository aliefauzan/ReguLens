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
| 0 | [Foundation](phases/phase-0-foundation.md) | Aug 19–20 | `NOT STARTED` | — | — |
| 1 | [Compliance Twin](phases/phase-1-compliance-twin.md) | Aug 21 | `NOT STARTED` | — | — |
| 2 | [Ingestion & Extraction](phases/phase-2-ingestion-extraction.md) | Aug 22–23 | `NOT STARTED` | — | — |
| 3 | [Guardrail & Reconciliation](phases/phase-3-guardrail-reconciliation.md) | Aug 24–25 | `NOT STARTED` | — | — |
| 4 | [Impact Engine](phases/phase-4-impact-engine.md) | Aug 26–27 | `NOT STARTED` | — | — |
| 5 | [Timeline & Query](phases/phase-5-timeline-query.md) | Aug 28–29 | `NOT STARTED` | — | — |
| 6 | [E2E Testing](phases/phase-6-e2e-testing.md) | Aug 30 | `NOT STARTED` | — | — |
| 7 | [Hardening & Submission](phases/phase-7-demo-hardening.md) | Aug 31 | `NOT STARTED` | — | — |

## Cross-cutting work

Tracked here because it spans phases and is easy to lose.

- [ ] `trace_id` propagated end to end (phase 0) — *the thing that makes debugging possible*
- [ ] Structured JSON logging everywhere, no `print` (phase 0, maintained throughout)
- [ ] Cloud Build pipeline green, rollback practised (phase 0)
- [ ] Secret Manager wired, no secrets in image or repo (phase 0)
- [ ] `docker compose up` brings up the full local stack (phase 0)
- [ ] Five alerts configured **and each one deliberately triggered once** (phase 0 → 7)
- [ ] Debug view `/debug/documents/{id}` (phase 2, extended in 3 and 4)
- [ ] `data-testid` attributes added as UI is built (phases 1–5)
- [ ] Every repository mutation writes a `graph_event` (phase 1 onward)
- [ ] Every Pub/Sub handler idempotent, redelivery tested (phases 2, 3, 4)
- [ ] Extraction fixture set + accuracy test checked in (phase 2)
- [ ] `FAKE_LLM=1` fixtures covering the E2E suite (phase 0 switch, phase 6 fixtures)

## Decisions taken

Recorded so they are not reopened. Change one only with a reason written here.

- [x] **Google ADK required** — all four agents are ADK agents; tool bodies stay plain functions
- [x] **Pub/Sub + Cloud Run Jobs approved** — three topics, one per pipeline stage
- [x] **Cloud Build** for CI/CD, not GitHub Actions
- [x] **Secret Manager** for secrets; plain env vars for non-secret config
- [x] **Docker Compose** for local, with push subscriptions matching production
- [ ] **Cut Gemma?** — recommended yes. *Decision pending, see `../todo.md` §7*
- [ ] **Cut OCR fallback?** — recommended yes. *Decision pending, see `../todo.md` §7*
- [ ] **Readiness as counts, not percentage?** — recommended counts. *Pending*
- [ ] **Two GCP projects or one?** *Pending*
- [ ] **Repo public or private?** *Pending*

## Blocked on the user

Mirrors `../todo.md`. Nothing below can be unblocked by writing code.

- [ ] Eligibility confirmed (country exclusions) — **blocks everything**
- [ ] Devpost registration — **blocks submission**
- [ ] GCP project ID + region + billing — **blocks phase 0**
- [ ] Gemini 3.5+ model identifier confirmed in that region — **blocks phase 0**
- [x] Real EU + BPOM regulation PDFs with text layers — downloaded to `data/regulations/`, see `data/regulations/SOURCES.md`
- [x] Confirmation that the two jurisdictions' limits actually differ — sodium benzoate in flavoured drinks: EU 150 mg/kg vs BPOM 400–900 mg/kg. Exact BPOM row alignment still to be confirmed against the rendered table

## Session log

Append one line per working session. Keep it short — this is for orientation, not
a diary.

| Date | Who | What changed |
|---|---|---|
| 19 Aug 2026 | planning | Plan folder created; ADK + Pub/Sub + Cloud Build + observability + E2E phase incorporated |
| 19 Aug 2026 | corpus | Downloaded 5 real regulation PDFs (EU 1333/2008 original + two consolidated versions, EU 1129/2011 Annex II, BPOM 11/2019) into `data/regulations/`; text layers verified; divergence confirmed |
