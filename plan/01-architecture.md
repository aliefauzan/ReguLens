# ReguLens — MVP Architecture

Target: All Things Agentic Hackathon, Collaborative Partner track.
Constraints confirmed from the rules page and from the team: **Google ADK is
required**, **Gemini 3.5 or newer is required**, and Pub/Sub + Cloud Run Jobs are
approved for use.

This document states the architecture we build, then the complexity we
deliberately refuse. The second list is the one that earns points under
*Architectural Discipline* (30% of scoring).

## Governing principle

> Deterministic code owns every mutation. ADK agents produce proposals; typed code
> decides whether a proposal becomes state; every accepted proposal writes an
> immutable audit event.

No code path writes a model response directly into `clauses`, `requirements`, or
`conflicts` without passing a Pydantic validator and a deterministic guardrail.

## Topology

```
┌────────────────────────────────┐
│ Next.js — Vercel               │
│ twin · upload · readiness      │
│ timeline · ask                 │
└───────────────┬────────────────┘
                │ HTTPS
                ▼
┌──────────────────────────────────────────┐
│ API service — Cloud Run                  │   fast, synchronous only
│ FastAPI                                  │
│ /products /documents /compliance         │
│ /events /query /alerts                   │
│ writes GCS + Firestore, then publishes   │
└──────┬─────────────────────┬─────────────┘
       │                     │
       ▼                     ▼
┌─────────────┐   ┌──────────────────────────────────┐
│ Cloud       │   │ Pub/Sub                          │
│ Storage     │   │  document.uploaded               │
│ raw files   │   │  clause.extracted                │
└─────────────┘   │  graph.changed                   │
                  │  + dead-letter topic per subs.   │
                  └──────────────┬───────────────────┘
                                 │ push subscriptions
                                 ▼
┌──────────────────────────────────────────────────────┐
│ Worker service — Cloud Run (same image, own entry)   │
│                                                      │
│  /internal/extract    ← document.uploaded            │
│      ADK Extraction Agent                            │
│  /internal/reconcile  ← clause.extracted             │
│      guardrail (code) → ADK Reconciliation Agent     │
│  /internal/impact     ← graph.changed                │
│      Impact Engine (pure code, no model)             │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐    ┌────────────────────────────┐
│ Firestore                            │    │ Vertex AI                  │
│ documents · clauses · products       │    │ Gemini 3.5+ (required)     │
│ markets · requirements · conflicts   │    │ text-embedding             │
│ graph_events · query_logs            │    │ Gemma (optional bonus)     │
└──────────────────────────────────────┘    └────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ Cloud Run Job — batch, no HTTP                       │
│  seed / reset demo workspace                         │
│  reprocess: re-run extraction over stored documents  │
└──────────────────────────────────────────────────────┘
```

Three deployables: API service, worker service, batch Job — all from **one
container image**, selected by entrypoint. One image keeps CI trivial while the
runtime separation stays real.

## Why this shape

**API service does no expensive work.** Upload returns `202` in under a second.
Everything that can be slow or can fail is behind Pub/Sub.

**One topic per pipeline stage, not one per document.** Each stage acks
independently, so a single malformed clause fails its own message and retries on
its own backoff without re-running extraction for the whole document. This is the
real reason for Pub/Sub here, and it is worth stating in the pitch — it is not
message-bus decoration.

**Per-clause fan-out.** Extraction publishes one `clause.extracted` message per
extracted clause. Six clauses reconcile in parallel. The cost of this is a genuine
race: two clauses reconciling against the same existing clause. Mitigation is a
Firestore transaction around every clause state mutation, keyed on the clause being
mutated. This is implemented in phase 3, not deferred.

**Cloud Run Jobs for batch, not for the request path.** The Job runs `seed` (demo
reset) and `reprocess` (re-extract stored documents after a prompt change). Both
are genuinely batch, both are things you want during a hackathon, and neither
belongs behind an HTTP request. Escalating a very large document from the worker to
a Job is possible via the Jobs API but is **not** in MVP scope — the worker's Cloud
Run timeout is far above what a ≤100-page document needs.

## Pub/Sub contract

| Topic | Published by | Consumed by | Payload |
|---|---|---|---|
| `document.uploaded` | API `/documents` | worker `/internal/extract` | `{document_id, workspace_id}` |
| `clause.extracted` | extract handler | worker `/internal/reconcile` | `{clause_id, document_id, workspace_id}` |
| `graph.changed` | reconcile handler | worker `/internal/impact` | `{entity_type, entity_id, clause_id, workspace_id}` |

Rules for every handler:

- **Idempotent by key.** Handler checks current state before acting; re-delivery of
  an already-processed message is a no-op that acks. Pub/Sub is at-least-once and
  will redeliver — design for it rather than hoping.
- **Ack deadline 600s**, push subscription, OIDC-authenticated so only Pub/Sub can
  invoke `/internal/*`.
- **Max delivery attempts 5, then dead-letter topic.** A message landing in the DLQ
  sets the document to `failed` with the stage recorded, surfaced in the UI with a
  retry button.
- **Never nack on a permanent error.** Malformed input acks and records `failed`;
  only transient errors (quota, timeout) nack for retry. Nacking a permanent error
  burns five retries and delays the visible failure.

## ADK agent design

ADK is required, so all four agents are ADK agents. But the honest split matters —
two of these genuinely need agentic tool selection and two do not:

| ADK agent | Tools | Nature | Why |
|---|---|---|---|
| **Extraction** | `extract_text`, `prefilter_sections` (Gemma), `emit_clause_candidates` | Fixed pipeline, structured output | Nondeterminism is least welcome at the point where documents become state |
| **Reconciliation** | `find_similar_clauses`, `check_comparability` (deterministic), `classify_relationship` (deterministic), `judge_ambiguous_pair` | Guardrail-gated; the agent may only reach the judge through the guardrail tool | The guardrail is code by design — see governing principle |
| **Impact** | `materialize_requirements`, `evaluate_requirement`, `rollup_status` | Pure deterministic traversal, **no model call** | Comparing 0.08 to 0.05 is arithmetic; a model here is strictly worse |
| **Query** | `get_product_compliance`, `find_clauses`, `get_events`, `get_conflicts` | Genuinely agentic — open-ended question shape, real tool selection | This is the one that justifies the framework |

A **root agent** routes to these, matching the concept's hierarchy.

Two implementation rules:

1. **Every tool body is a plain Python function importable and testable without
   ADK.** ADK wraps them; it does not own them. Guardrail tests call
   `comparability(a, b)` directly.
2. **The Impact agent's ADK wrapper contains no model call.** Registering
   deterministic logic as an ADK agent is fine and keeps the hierarchy legible;
   pretending it reasons is not. Say this out loud in the submission — a judge
   scoring architectural discipline will respect it more than four LLM agents.

## Model selection

- **Gemini 3.5 or newer is a hard rules requirement.** Confirm the exact available
  model identifier in the Vertex AI console during phase 0 and pin it in config —
  do not hardcode a guessed model string.
- Structured/JSON output mode for extraction and for judge verdicts. Never parse
  prose into state.
- **Gemma is an optional bonus, not a dependency.** It earns its place as the
  long-document section pre-filter (a real token reduction we can measure), but if
  phase 2 runs late, cut Gemma before cutting anything else. Nothing downstream
  depends on it.

## Similarity without a vector database

Clause embeddings are stored as a float array on the clause. `find_similar(clause, k)`
loads active clauses filtered by `substance_normalized` or jurisdiction and ranks by
cosine in process. At hundreds of clauses this is milliseconds and zero
infrastructure. The function signature is stable, so a managed index is a body swap.

**Trip-wire:** > 10k clauses, or scan latency > 200ms.

## Firestore as the knowledge graph

No graph database. Relations are explicit ID fields; "2-hop traversal" is two
indexed queries. The value is the state machine and the append-only audit log, not
graph query expressiveness. Describe it accurately in the submission — overclaiming
"knowledge graph" to a technical judge invites the one question you cannot answer.

## No authentication

A single hardcoded `workspace_id` threads through every record and every Pub/Sub
message. Firebase Auth later is middleware plus reading the ID from a token. The
`/internal/*` endpoints are protected by Pub/Sub OIDC and are not publicly
invocable — that is the security boundary that actually matters here.

## What we are explicitly not building

| Not building | Rationale | Trip-wire |
|---|---|---|
| Managed vector index | Hundreds of clauses; in-process cosine is correct | > 10k clauses |
| Graph database | Six ID-linked entity types | Queries the code cannot express |
| Auth / multi-tenancy | Zero demo value; boundary already exists | First real user |
| Escalating large docs to the Job | Worker timeout is far above need | Documents > worker timeout |
| Conflict resolution workflow | Detection is the thesis; adjudication is a product | Post-hackathon |
| Notification channels (email, WhatsApp) | In-app alert proves the loop | Post-hackathon |
| Regulation crawler | Different product, different failure modes | Post-hackathon |
| Readiness % as a headline KPI | Implies coverage we do not have | Only once non-numeric checks truly evaluate |
| Redis / caching layer | Nothing is hot | Never at this scale |
| Further service splitting | Three runtimes from one image is already the ceiling | Never at this scale |
| Streaming responses | One endpoint; a spinner is honest | Post-hackathon |
| Terraform / IaC | ~15 resources created once; a documented `setup.sh` of `gcloud` commands is reproducible enough and faster to write | A second environment beyond dev/demo |
| Prometheus / Grafana / Sentry | Cloud Logging, Monitoring, Trace, and Error Reporting are already integrated — see `04-observability.md` | Post-hackathon |

## How this maps to the judging criteria

| Criterion | Weight | What carries it |
|---|---|---|
| Innovation & Operational Utility | 40% | Unprompted status flip (phase 4) — the system acts without being asked, which is the "beyond standard chat loops" requirement; cross-jurisdiction conflict detection; audit trail a regulator could read |
| Architectural Discipline & Tech Stack | 30% | Guardrail-gates-the-model principle; per-stage Pub/Sub retry with DLQ; computed confidence rather than self-reported; the "not building" table above; honest labelling of which agents actually reason |
| Demo & Production Readiness | 30% | Cloud Build CI/CD with SHA-pinned rollback; Secret Manager; observability (`04-observability.md`) — structured logs, traces, five alerts, a dashboard; the full E2E suite in phase 6; one-command seed/reset via Cloud Run Job; visible failure states with retry; deployed URL; recorded fallback; README spin-up; architecture diagram |

## Repository layout

```
regulens/
  web/                    Next.js + TS + Tailwind + shadcn → Vercel
  api/
    main.py               API service entrypoint
    worker.py             worker service entrypoint (/internal/*)
    job.py                Cloud Run Job entrypoint (seed | reprocess)
    routes/
    adk/                  root agent + 4 agent definitions + tool registrations
    core/                 the plain-Python functions ADK tools wrap
      extraction/  guardrail/  reconciliation/  impact/  retrieval/
    messaging/            publish + push-handler plumbing, idempotency
    store/                Firestore repositories (event-writing enforced)
    models/               pydantic schemas
    seed/                 fixtures + demo baseline
    tests/
    observability/        structured logging, trace context, metrics helpers
  e2e/                    Playwright specs (phase 6)
  plan/
  docker/Dockerfile       one image, three entrypoints
  docker-compose.yml      full local stack incl. emulators
  cloudbuild.yaml         lint → test → build → push → deploy ×3
  scripts/setup.sh        one-time gcloud provisioning, re-runnable
```

## Delivery: Cloud Build, Secret Manager, Docker Compose

### CI/CD — Cloud Build
`cloudbuild.yaml` at the repo root, triggered on push to `main`. Steps:

1. Lint + unit tests (fails the build; no deploy on red).
2. Build one image, tag with the short commit SHA **and** `latest`.
3. Push to Artifact Registry.
4. Deploy the API service, deploy the worker service, update the Cloud Run Job —
   all pinned to the SHA tag, never `latest`, so a rollback is a redeploy of a
   known digest.
5. Run the integration test suite against the deployed dev service (phase 6).

Keep it one file with no build-config sprawl. A second trigger on pull requests
runs steps 1–2 only.

The frontend stays on Vercel's own git integration — wiring Next.js builds into
Cloud Build buys nothing here.

**Rollback:** `gcloud run services update-traffic --to-revisions=<prev>=100`.
Write this command in the README; do not look it up during a demo.

### Secrets — Secret Manager
No secrets in `cloudbuild.yaml`, in the image, in `.env` committed anywhere, or in
Cloud Run plain env vars.

| Secret | Used by |
|---|---|
| Vertex/Gemini access | via the service account, not a key — **no API key exists to leak** |
| Any third-party OCR or embedding key | worker |
| Pub/Sub OIDC audience config | non-secret; plain env var |
| Frontend `NEXT_PUBLIC_API_URL` | non-secret by definition; Vercel env var |

Cloud Run mounts secrets as environment variables via
`--set-secrets=NAME=secret:version`. The runtime service account gets
`secretmanager.secretAccessor` on those specific secrets only.

Prefer workload identity over keys wherever Google APIs are involved — the fewer
secrets that exist, the fewer there are to manage. Realistically this project has
almost none, and that is a good outcome to state in the submission.

**Non-secret configuration** (model id, thresholds, topic names, page limits) lives
in plain env vars so it is visible and greppable. Putting non-secrets in Secret
Manager makes debugging harder for no security gain.

### Local — Docker Compose
`docker-compose.yml` bringing up the whole stack offline:

```yaml
services:
  firestore-emulator     # gcr.io/google.com/cloudsdktool/google-cloud-cli
  pubsub-emulator        # same image, pubsub start
  pubsub-init            # one-shot: creates topics + push subscriptions → worker
  api                    # image entrypoint main.py, hot reload, port 8080
  worker                 # image entrypoint worker.py, hot reload, port 8081
  web                    # next dev, port 3000
```

Requirements for it to be worth having:

- **Push subscriptions point at the `worker` container**, so local behaviour matches
  production. Polling locally and pushing in production means you debug two
  different systems.
- `pubsub-init` is idempotent and runs on every `up`.
- Only Vertex AI is remote. Everything else is local, so iteration costs nothing but
  LLM tokens.
- A `FAKE_LLM=1` mode returning canned extraction responses from the fixture set,
  for tests and for working offline. This is not a stub of convenience — the E2E
  suite depends on it for determinism.
- Source mounted for hot reload; `docker compose up` is the only command in the
  README's local section.

## Environments

| Env | Web | API + worker | Data | Notes |
|---|---|---|---|---|
| local | Compose | Compose ×2 | Firestore + Pub/Sub emulators in Compose | `docker compose up`; only Vertex is remote, and `FAKE_LLM=1` removes even that |
| dev (GCP) | — | Cloud Run ×2 | dedicated project | Deployed by Cloud Build on every green `main`; integration tests run here |
| demo | Vercel | Cloud Run ×2 + Job | dedicated GCP project | The only environment judges see |

No staging beyond `dev`. Two GCP projects (`dev`, `demo`) is the ceiling.

## Cost and quota guardrails

- Budget alert on day one, before any Vertex call.
- Extraction cached on `sha256(file)` — rehearsal must not re-bill or re-run Gemini.
- Reject documents over 100 pages or 20 MB at ingest.
- Confirm Gemini 3.5+ quota in the chosen region during phase 0, not on demo day.
