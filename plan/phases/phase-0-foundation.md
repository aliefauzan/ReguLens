# Phase 0 — Foundation (walking skeleton)

**Estimate:** 2 days (Aug 19–20)
**Demo sentence:** "The deployed web app reads a record the deployed API wrote to Firestore, and a Pub/Sub message round-trips through the deployed worker."

**Status:** `COMPLETE` · **Started:** 19 Aug 2026 · **Completed:** 31 Aug 2026
(every box ticked or deliberately skipped with its reason; the four skips are all
the same decision — Vercel and a push trigger were replaced by one Cloud Build
path, not left pending)

<!-- MAINTAIN THIS FILE.
     Set Status to IN PROGRESS when you begin, COMPLETE when every exit criterion
     is ticked. Fill the dates. Tick each `- [ ]` as it lands — a ticked box means
     it exists in the repo and is deployed, not that it is written down somewhere.
     If you deliberately skip an item, change it to `- [~]` and add ` — SKIPPED:
     reason` on the same line so nobody re-litigates it later.
     Then update ../PROGRESS.md. -->

## Goal

Prove the whole delivery path end-to-end with the least possible product in it.
Every later phase then only adds product, never plumbing.

## Why this phase exists

The single most common way a hackathon project dies is discovering on the last day
that deployment, IAM, or CORS does not work. Doing it first with a trivial payload
costs one day and removes that risk permanently.

## Scope

### Infrastructure
- [x] GCP project created; **budget alert set** — `regulens-506014`, budget Rp 540,000/mo (~$30) at 50/90/100%, email channel to afindo.mi01@gmail.com.
- [x] Enable: Cloud Run, Cloud Storage, Firestore (Native mode), Pub/Sub, Vertex AI, Artifact Registry — plus Secret Manager, Trace, Error Reporting, Cloud Build. Done by `scripts/setup.sh`.
- [x] **Verify the exact Gemini 3.5+ model identifier available in your region** and
      pin it in config — `gemini-3.5-flash`, confirmed by a live `generateContent`
      call, not by guessing. `asia-southeast1` carries only `gemini-2.5-flash`, so
      generation runs against the **`global`** Vertex endpoint while embeddings
      (`text-multilingual-embedding-002`) stay in `asia-southeast1`. Pinned in
      `scripts/setup.sh`.
- [x] Create topics `document.uploaded`, `clause.extracted`, `graph.changed`, plus
      a dead-letter topic. Push subscriptions to the worker service with OIDC auth,
      ack deadline 600s, max delivery attempts 5 — all four topics and three push
      subscriptions exist, each with OIDC as `regulens-pubsub-invoker`, ack deadline
      600s, dead-lettering to `regulens.deadletter` after 5 attempts, plus a pull
      subscription on the dead-letter topic so failures are inspectable.
- [x] Create GCS bucket — `gs://regulens-506014-uploads` (the bare name is taken globally), uniform bucket-level access, public access prevention on.
- [x] Service accounts with narrow roles — `regulens-api`, `regulens-worker`,
      `regulens-pubsub-invoker`. `datastore.user`, `aiplatform.user`,
      `pubsub.publisher`, `logging.logWriter`, `cloudtrace.agent`,
      `errorreporting.writer` at project level; `storage.objectAdmin` (api) and
      `storage.objectViewer` (worker) **bucket-scoped**, not project-wide. The
      Pub/Sub service agent has `serviceAccountTokenCreator` for OIDC push. Default
      compute SA unused.
- [~] Deploy `firestore.indexes.json` with the composite indexes from `02-data-model.md`. — SKIPPED: no query in the finished app needs one. Every Firestore filter is equality-only, and the two places that would otherwise sort or range (`list_alerts`, `/clauses`) read a bounded page and refine in process on purpose. Verified 31 Aug: `gcloud firestore indexes composite list` returns nothing and nothing is broken by that. The file stays as the record of where a composite index would become necessary; `scripts/setup.sh` no longer claims to submit it, because the command it used (`gcloud firestore indexes create --file=`) does not exist and had been silently failing on every run.
- [x] Verify Vertex AI quota — live `generateContent` and embedding calls both succeeded, `trafficType: ON_DEMAND`. No quota request needed.

### API (`api/`)
- [x] FastAPI app, Python 3.12, pinned deps — `api/requirements.txt` fully pinned, `uv` venv on 3.12 locally, container on `python:3.12-slim`.
- [x] `GET /health` returning `{status, version, firestore: "ok"}` — verified against
      the deployed service; the check is a real Firestore read, and the endpoint
      returns 503 when it fails.
- [x] Firestore client initialization working locally (ADC) and on Cloud Run
      (workload identity), no code difference.
- [x] `POST /markets/seed` + `GET /markets` — two markets (EU/Germany, Indonesia/BPOM) seeded and read back from the deployed API. Seeding is idempotent.
- [x] Pydantic settings module; every config value from env, none hardcoded.
- [x] CORS configured for the web origin and localhost — Vercel never happened; the web service runs on Cloud Run and answers on two hostnames, so `CORS_ORIGINS` carries both plus the two local ports. Read back off the deployed service 31 Aug.
- [x] Worker push endpoint `/internal/document-uploaded`: decodes the envelope,
      writes a Firestore record, acks. **Round-trip proven end to end** — published a
      message, the deployed worker wrote `echo_events/21371888646828420` and logged
      a 200, and both carry the publisher's `trace_id`.
- [x] `messaging/` module: publish helper (stamps `trace_id` on every message),
      push-envelope parser, and a real idempotency check keyed on
      `(handler, message_id)` — not a stub. Verified: the marker document was
      written alongside the echo record.
- [x] One Dockerfile, three entrypoints (`main.py`, `worker.py`, `job.py`); API and
      worker deployed to Cloud Run and the Job registered, all from the one image.

### ADK scaffold
- [x] Google ADK 2.7.1; root agent with one tool, **executing on Cloud Run** —
      `POST /internal/adk-smoke` returns a real Gemini 3.5 answer and shows
      `tool_calls: ["lookup_market"]`. First attempt 500'd because ADK looks for a
      Gemini API key unless `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT` and
      `GOOGLE_CLOUD_LOCATION` are set; those are now in the deploy config. Exactly
      the day-one discovery this phase exists to force.
- [x] Pattern established: tool bodies are plain functions in `app/core/`, ADK
      registration is a thin wrapper in `app/adk/`. `tests/test_tools.py` calls the
      plain function with no runner, no agent and no network.

### Web (`web/`)
- [~] Next.js App Router + TypeScript + Tailwind + shadcn/ui initialized. — Next 16.3.1 + TS + Tailwind 4 done and building. **shadcn/ui was never added** and the whole UI shipped without it: SKIPPED, because the components that got built (`web/app/_ui/`) are few and specific, and a component library would have been a dependency carried for nothing.
- [x] `lib/api.ts` — single typed fetch client reading `NEXT_PUBLIC_API_URL`, surfacing status and `x-trace-id` on failure.
- [x] Home page listing markets from the live API — verified against a production build: both markets render, with `data-testid` hooks for phase 6. A dead API renders an explicit error, never an empty list.
- [~] Deployed to Vercel with the env var pointing at Cloud Run. — SKIPPED: the frontend runs on Cloud Run instead (`regulens-web`), built and deployed by the same `cloudbuild.yaml` as everything else. One deploy path beats two, and the Vercel dependency is gone rather than pending.

### CI
- [x] **Cloud Build** `cloudbuild.yaml`: lint → test → build one image → push
      SHA-tagged to Artifact Registry → deploy API, worker and Job pinned to the SHA.
      Two green builds so far.
- [~] PR trigger running lint + test only. — SKIPPED: the build trigger is manual by design for a single-maintainer hackathon build. A push trigger needs GitHub-app OAuth from the repo owner and buys nothing before the deadline. `cloudbuild.yaml` runs ruff and the full pytest suite ahead of every image it builds, so nothing ships untested.
- [x] Rollback practised — traffic moved to an earlier revision, `/health` reported
      the older version, then rolled forward. Learned the hard way that redeploying
      an older *image* is not a rollback: env vars persist from the newer revision,
      so `VERSION` lied. `update-traffic --to-revisions` is the real command and it
      is what goes in the README.
- [x] Keep it one file. No build-config sprawl.

### Secrets & config
- [x] **Secret Manager** for anything secret; Cloud Run mounts via `--set-secrets`.
      Grant `secretmanager.secretAccessor` per-secret, not project-wide. — two
      secrets live, `gemini-api-key` and `gemini-discovery-key`, both mounted on
      api and worker and read back off the deployed services 31 Aug. Nothing
      secret is in the image or the repo.
- [x] Non-secret config (model id, topic names, bucket, limits) in plain env vars,
      declared in `app/settings.py`.
- [x] Workload identity throughout; **zero secrets exist so far.** Vertex, Firestore,
      Storage and Pub/Sub all authenticate as the service account.
- [x] `scripts/setup.sh`: every `gcloud` provisioning command, re-runnable — written
      and executed 19 Aug. Every step guards on a `describe` first, so a second run
      is a no-op. Feeds the README's spin-up section.

### Observability baseline — see `../04-observability.md`
- [x] **`trace_id` end to end** — minted or adopted in API middleware, echoed on the
      response as `x-trace-id`, stamped on every published message, re-adopted by the
      worker, present on every log line. Verified with one Cloud Logging query on
      `jsonPayload.trace_id`: the worker's lines carry the publisher's id. Storing it
      on documents and `graph_event`s comes with those collections in phase 1.
- [x] Structured JSON logging helper; no `print` anywhere in `api/`.
- [x] OpenTelemetry FastAPI instrumentation → Cloud Trace on both services, wrapped so a tracing failure can never stop the app serving.
- [x] Enable Error Reporting — API enabled; both services hold `errorreporting.writer` and unhandled exceptions surface automatically from the structured logs.
- [~] Uptime checks on both `/health` endpoints — SKIPPED (worker): the public API has one. The worker is private and Cloud Monitoring uptime checks cannot present an OIDC token to Cloud Run, so a check there would report a permanent false outage. Worker liveness is covered by the Pub/Sub round-trip and the dead-letter subscription.
- [x] Budget alert (first of the five) — live. *The email channel still needs the user to click Google's verification mail.*

### Local dev
- [x] **`docker-compose.yml`**: firestore-emulator, pubsub-emulator, a one-shot
      idempotent `pubsub-init` creating topics and **push** subscriptions pointing at
      the `worker` container, plus api, worker, and web with hot reload.
      Push locally, push in production — never poll in one and push in the other.
      Run and verified 25 Aug. Three local-only env vars carry the differences:
      `FIRESTORE_DATABASE=local` (the emulator rejects the URL-encoded `(default)`
      id the client sends), `LOCAL_STORAGE_DIR` (no Cloud Storage emulator exists,
      so api and worker share an uploads volume through `app/storage.py`), and
      `API_INTERNAL_URL` (server components inside the web container cannot reach
      `localhost:8080`).
- [x] `FAKE_LLM=1` mode returning canned responses — switch is in `settings` and
      honoured by the ADK path. Fixtures come in phase 6.
- [x] `docker compose up` is the entire local setup instruction — plus the one-shot
      `pubsub-init` and the seed job, both documented in the README.
- [x] `README.md` at repo root: architecture, config table, provisioning, deploy,
      the real rollback command, local dev, and how to verify the skeleton.

## Exit criteria

- [x] A public URL renders markets that came from Firestore via Cloud Run — on Cloud Run rather than Vercel. Verified from a cold browser 31 Aug: the hosted site renders both markets and every product's verdict against them.
- [x] `GET /health` returns `firestore: "ok"` from the deployed service.
- [x] Publishing to `document.uploaded` in the deployed project causes the deployed
      worker to write a Firestore record. Verified in Cloud Run logs.
- [x] An ADK agent with one tool executes successfully **on Cloud Run**.
- [x] The pinned Gemini 3.5+ model identifier is confirmed and a one-line completion
      succeeds against it.
- [~] A pushed commit deploys both services without manual steps. — SKIPPED with the PR trigger above and for the same reason. One command deploys everything (`gcloud builds submit --config cloudbuild.yaml`), and it is the only path that has ever deployed this app.
- [x] `docker compose up` from a clean clone brings up the full stack, and a locally
      published message reaches the local worker — verified 25 Aug by
      `scripts/verify_local.sh`, which additionally proves the EU upload, the
      cross-jurisdiction conflict, the unprompted Germany flip, the alert, the
      upload cache, and redelivery-without-duplicates, all with zero GCP calls.
- [~] Cloud Build deploys both services and the Job, and the rollback command has
      been executed successfully once — SKIPPED (partial): builds are green and
      rollback is practised, but they are triggered manually with `gcloud builds
      submit`. The **push trigger** is not wired yet, so "from a push" is not true;
      see the unticked PR-trigger item above.
- [x] A log line from the deployed worker carries the same `trace_id` as the
      publisher — verified by one Cloud Logging query on `jsonPayload.trace_id`.
- [x] Budget alert is active; quota check recorded in the README.

## Out of scope for this phase

Auth, real extraction, any upload, any styling beyond default shadcn. Resist making
the home page look good — it is replaced in phase 1. The one LLM call permitted here
is the model-availability smoke test.

## Risk notes

- Cloud Run cold start plus Firestore init can exceed a naive health-check timeout;
  set the startup probe generously.
- If the Firestore emulator fights you, fall back to a real `dev` project rather
  than losing hours — Firestore usage at this scale is effectively free.
- Pub/Sub push to a private Cloud Run service is the classic day-one time sink:
  the push subscription needs a service account with `run.invoker`, and the
  subscription must be configured for OIDC. Budget an hour for this specifically.
- ADK on Cloud Run may need a specific Python version or extra dependency. Finding
  that out today costs an hour; finding it out in phase 3 costs the project.
- The Pub/Sub emulator does not enforce OIDC, so local push "works" in ways
  production will not. Deploy the phase-0 echo round-trip to real Cloud Run before
  calling this phase done — that is exit criterion 3, and it exists for this reason.
- This phase is now 2 days and it is all plumbing with nothing to show. That is
  correct. Every hour spent here is an hour not lost on Aug 30.
