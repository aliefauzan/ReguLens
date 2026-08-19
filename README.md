# ReguLens

Cross-jurisdiction regulatory compliance for food and beverage products. A
product is described once; ReguLens tells you where it fails, in which market,
against which clause — and tells you again when a regulation moves.

**Status: phase 0 (walking skeleton) — deployed and verified.** See
[`plan/PROGRESS.md`](plan/PROGRESS.md) for exactly what is real.

## Architecture

Three runtimes over one container image:

| Runtime | Entrypoint | Job |
|---|---|---|
| API service (Cloud Run, public) | `app/main.py` | Accepts requests, writes Firestore, publishes to Pub/Sub. Does no extraction. |
| Worker service (Cloud Run, private) | `app/worker.py` | Consumes Pub/Sub **push** with OIDC. Every handler is idempotent. |
| Job (Cloud Run Job) | `app/job.py` | Seeding and reprocessing. Runs to completion. |

Frontend is Next.js (App Router) reading the API server-side.

Agents are Google ADK. Tool bodies are plain functions in `api/app/core/`; ADK
registration is a thin wrapper in `api/app/adk/`. Agents propose — deterministic
typed code decides and owns every mutation.

## Configuration

| Setting | Value | Why |
|---|---|---|
| Project | `regulens-506014` | |
| Infra region | `asia-southeast1` | Latency from Indonesia |
| Gemini | `gemini-3.5-flash` @ **`global`** | `asia-southeast1` carries only `gemini-2.5-flash`, which fails the 3.5+ requirement |
| Embeddings | `text-multilingual-embedding-002` @ `asia-southeast1` | Available in-region, handles Indonesian |
| Secrets | none | Workload identity throughout. Nothing to leak. |

ADK reaches Vertex only when `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`
and `GOOGLE_CLOUD_LOCATION` are set. Without them it looks for a Gemini API key
and fails at request time, not at boot.

## Provisioning from scratch

```bash
gcloud auth login && gcloud auth application-default login
PROJECT_ID=your-project ./scripts/setup.sh
```

Every step guards on a `describe` first, so running it twice is a no-op. Run it
again after the first deploy — push subscriptions need the worker's URL, which
does not exist until then.

Quota note: a fresh project needs no Vertex quota request. A live
`generateContent` call and a live embedding call both returned `ON_DEMAND` on
first use.

## Deploy

```bash
gcloud builds submit --config cloudbuild.yaml --region asia-southeast1 --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)
```

Lint → test → build one SHA-tagged image → deploy API, worker and Job pinned to
that SHA.

### Rollback

```bash
gcloud run services update-traffic regulens-api --region asia-southeast1 --to-revisions REVISION=100
```

Use the revision, not the image. Redeploying an older image is **not** a
rollback: environment variables persist from the newer revision, so the service
reports the new version while running old code. Practised once, deliberately.

## Local development

```bash
cd api && uv venv --python 3.12 .venv && uv pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q && .venv/bin/ruff check .
```

```bash
cd web && npm install && NEXT_PUBLIC_API_URL=<api-url> npm run dev
```

The container pins Python 3.12 regardless of the host version, because ADK and
the GCP client libraries are tested against it.

`FAKE_LLM=1` returns canned model responses so tests never touch Vertex.

## Verifying the skeleton

```bash
curl -s "$API_URL/health"
```

Returns `firestore: "ok"` from a real Firestore round-trip, not a hardcoded
string, plus an `x-trace-id` response header.

```bash
gcloud pubsub topics publish document.uploaded --message='{"document_id":"probe"}' --attribute=trace_id=my-trace
gcloud logging read 'resource.labels.service_name="regulens-worker" AND jsonPayload.trace_id="my-trace"'
```

The worker's log lines carry the publisher's `trace_id`. That is the property the
whole debugging story rests on: one id, one query, the entire journey.

## Observability

Structured JSON logs with a `trace_id` on every line. No `print` anywhere.
OpenTelemetry → Cloud Trace on both services, wrapped so a tracing failure can
never stop the app serving.

Budget alert: Rp 540,000/month (≈ $30 — the billing account is IDR-denominated),
firing at 50/90/100% to a Cloud Monitoring email channel.

Uptime check on the public API `/health`. The worker has none: it is private, and
uptime checks cannot present an OIDC token to Cloud Run. Worker liveness is
covered by the Pub/Sub round-trip and the dead-letter subscription instead.

## Data

Real regulation PDFs live in `data/regulations/`, catalogued with sources, CELEX
ids and checksums in [`data/regulations/SOURCES.md`](data/regulations/SOURCES.md).
Nothing there is synthetic.
