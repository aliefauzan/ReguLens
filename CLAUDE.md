# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# ReguLens — Working Agreement

Hackathon project. Deadline **31 Aug 2026, 5:00pm PDT**. Plan lives in `plan/`.

## Before doing anything

1. Read **`plan/PROGRESS.md`** first. It is the single source of truth for what is
   already built.
2. Do not rebuild a phase marked `COMPLETE`. Read its phase file to learn what
   exists.
3. If a phase is `IN PROGRESS`, the unticked boxes in that phase file are the
   remaining work. Start there.
4. Check `todo.md` for inputs still blocked on the user before assuming something is
   missing because of a bug.

## Commands

Everything runs through the Makefile. `make help` lists the targets.

```bash
make install          # venv + api deps + npm install
make run              # whole stack on Docker (emulators, FAKE_LLM, no GCP, no cost)
make test-all         # lint + tests + tsc + web build + local drill, as a pass/fail table
make lint             # ruff over api/, tsc over web/
make test             # unit tests only, offline
make test-local       # the pipeline drill against emulators (needs Docker)
make verify-deployed  # the same drill against the deployed stack — spends money
make diagram          # regenerate docs/architecture.png (needs Graphviz)
```

The Python venv is `api/.venv` and every command must run from `api/`:

```bash
cd api && .venv/bin/python -m pytest tests/test_sources.py          # one file
cd api && .venv/bin/python -m pytest -k "relevance and not market"  # by name
cd api && .venv/bin/python -m pytest -q -p no:cacheprovider         # quiet, no cache
cd api && .venv/bin/python -m ruff check . --fix
```

> `make test-local` is **not idempotent** — it asserts a fresh baseline but leaves a
> product and two documents behind, so a second run fails on `Germany must read
> unknown`. Reset first: `docker compose down -v && docker compose up -d`.

Deploying is `gcloud builds submit --config cloudbuild.yaml` with a unique
`SHORT_SHA` (a repeated tag silently redeploys nothing — see `scripts/quickstart.sh`
for the exact invocation). `scripts/setup.sh` provisions GCP and is idempotent; run
it a second time after the first deploy so the Pub/Sub push subscriptions and the
Cloud Scheduler job can learn the worker's URL.

## Architecture

One container image, four Cloud Run services. **Everything slow is behind Pub/Sub**;
the API hashes, stores, publishes and returns 202.

```
two ways in ─┬─ POST /documents (upload or pasted text)
             └─ Cloud Scheduler 06:00 → worker /internal/check-sources → re-reads
                watched addresses → create_document, the SAME call an upload makes
                          │
                          ▼  both publish document.uploaded
  /internal/document-uploaded → extract  → clause.extracted
  /internal/clause-extracted  → reconcile → graph.changed
  /internal/graph-changed     → impact (no model call) → verdict + audit event
  /internal/dead-letter       ← any topic after max delivery attempts
```

There is no third way into the graph. Anything that would add one is a design error.

**Layering is load-bearing, not stylistic.** `api/app/core/` imports neither FastAPI
nor ADK — verify with a grep before you break it. `api/app/adk/` holds four agents
that only *register* tools; every tool body is a plain function in `core/` that
imports and tests without an agent framework or a web server. Route handlers in
`main.py` / `worker.py` stay thin and import from `core/` lazily.

Where the reasoning lives, by module:

| Module | Owns |
|---|---|
| `core/documents.py` | ingestion, the content-hash cache, cascade delete |
| `core/extraction/` | text extraction, chunking, the LLM call, candidate building |
| `core/guardrail.py` | may two clauses even be compared — deterministic, no model |
| `core/reconciliation.py` | supersede / conflict / review verdicts + embeddings |
| `core/impact.py` | requirements, evaluation, status rollup — arithmetic, no model |
| `core/sources.py` + `fetching.py` | watched addresses; four kinds, four change signals |
| `core/relevance.py` | which rules bear on this workspace — computed on read, never stored |
| `core/alerts.py` + `autonomy.py` | why a verdict moved; what ran unprompted |
| `core/repository.py` | the only write path — mutation and its audit event in one batch |

Firestore collections: `documents`, `clauses`, `requirements`, `conflicts`,
`products`, `markets`, `watched_sources`, `graph_events`, `processed_messages`,
`extraction_debug`, `query_logs`.

Config is `api/app/settings.py` (pydantic-settings). Nothing is hardcoded at a call
site; a real env var always beats `regulens.env`. `FAKE_LLM=1` runs the whole
pipeline with no model calls — the local stack and most tests rely on it.

`web/` carries its own `AGENTS.md` written by `next dev`: this Next.js is newer than
your training data, so read `node_modules/next/dist/docs/` before writing app code.

## While working

- Work the current phase only. If you find something belonging to a later phase,
  note it in that phase's file rather than building it now.
- Every phase file has a **Status** block and checkboxes. They are the record.

## After every meaningful change — not optional

Update the plan in the same commit as the code. A checkbox that lags the repo is
worse than no checkbox, because the next session trusts it.

- [ ] Tick the boxes in the relevant `plan/phases/phase-N-*.md` for what actually
      landed.
- [ ] Update that file's **Status** block (`NOT STARTED` → `IN PROGRESS` →
      `COMPLETE`) and its dates.
- [ ] Update the phase row and any cross-cutting boxes in `plan/PROGRESS.md`.
- [ ] Append one line to the **Session log** in `plan/PROGRESS.md`.
- [ ] If a decision got made, record it under **Decisions taken** so it is not
      reopened.

## Checkbox semantics

| Marker | Meaning |
|---|---|
| `- [ ]` | Not done |
| `- [x]` | Done, in the repo, **and deployed** |
| `- [~]` | Deliberately skipped. Append ` — SKIPPED: <reason>` on the same line |

Tick a box only when the thing is real and verified. Not "written down", not
"works locally". If you skip something on purpose, mark it `[~]` with a reason so
nobody re-litigates it at 2am on the 30th.

## Standing rules from the plan

- **Deterministic code owns every mutation.** ADK agents propose; typed code
  decides. Never write a model response into `clauses`, `requirements`, or
  `conflicts` without a Pydantic validator and the guardrail.
- **Every Pub/Sub handler is idempotent.** Delivery is at-least-once and will
  redeliver.
- **ADK tools wrap plain functions** that are importable and testable without ADK.
- **Structured JSON logs with `trace_id` on every line.** No `print`.
- **Add `data-testid` as you build UI.** Phase 6 depends on it.
- **Claim only what is verified.** No fabricated readiness percentages, no invented
  regulation text, no "monitoring" language for behaviour that only runs on upload.

## Rules learned the hard way

Each of these cost a real debugging session. Undoing one silently reintroduces the
bug.

- **Hash the extracted text, not the bytes.** EUR-Lex stamps a fresh session id into
  every response, so a byte hash reports a change — and bills a model run — nightly.
- **Verify a fetched URL from Cloud Run, not just from a laptop.** EUR-Lex answers a
  datacentre address with `202` and a challenge page. The EU source points at CELLAR
  for exactly this reason, and an empty 2xx body is its own named failure.
- **Send `Accept` explicitly.** CELLAR content-negotiates; without it you get RDF
  *about* the regulation, which reaches extraction and fails there.
- **Hand `google-genai` an httpx client you own** (`http_options=`). The SDK closes a
  transport it created when the owning object is collected, which killed the direct
  extraction path three times in production.
- **Refuse, never truncate.** A confident answer drawn from the half of a regulation
  that happened to fit is worse than no answer.
- **A filter that hides something must say how much and why.** The review queue
  states its held-back count; a source that cannot be read renders its error. Silence
  is what makes a monitoring claim a lie.
