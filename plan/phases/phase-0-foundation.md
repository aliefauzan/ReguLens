# Phase 0 — Foundation (walking skeleton)

**Estimate:** 2 days (Aug 19–20)
**Demo sentence:** "The deployed web app reads a record the deployed API wrote to Firestore, and a Pub/Sub message round-trips through the deployed worker."

**Status:** `NOT STARTED` · **Started:** — · **Completed:** —

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
- [ ] GCP project created; **budget alert set** (do this before any Vertex call).
- [ ] Enable: Cloud Run, Cloud Storage, Firestore (Native mode), Pub/Sub, Vertex AI, Artifact Registry.
- [ ] **Verify the exact Gemini 3.5+ model identifier available in your region** and
      pin it in config. The rules require 3.5 or newer; a guessed model string is a
      disqualification risk and a day-one discovery, not a day-ten one.
- [ ] Create topics `document.uploaded`, `clause.extracted`, `graph.changed`, plus
      a dead-letter topic. Push subscriptions to the worker service with OIDC auth,
      ack deadline 600s, max delivery attempts 5.
- [ ] Create GCS bucket `regulens-uploads`, uniform access, no public reads.
- [ ] Service account for the API with the narrow roles it needs
      (`datastore.user`, `storage.objectAdmin` on that one bucket, `aiplatform.user`,
      `pubsub.publisher`). A separate invoker service account for Pub/Sub push.
      Do not use the default compute service account.
- [ ] Deploy `firestore.indexes.json` with the composite indexes from `02-data-model.md`.
- [ ] Verify Vertex AI quota for the chosen Gemini model in the chosen region.

### API (`api/`)
- [ ] FastAPI app, Python 3.12, `uv` or `pip-tools` for pinned deps.
- [ ] `GET /health` returning `{status, version, firestore: "ok"}` — the Firestore
      check is a real round-trip, not a hardcoded string.
- [ ] Firestore client initialization with credentials working both locally
      (emulator or ADC) and on Cloud Run.
- [ ] `POST /markets/seed` + `GET /markets` — the trivial real payload for this phase.
- [ ] Pydantic settings module; every config value from env, none hardcoded.
- [ ] CORS configured for the Vercel origin and localhost.
- [ ] `POST /internal/echo` on the **worker** entrypoint: accepts a Pub/Sub push
      envelope, decodes it, writes a Firestore record, acks. This is the phase-0
      round-trip proof.
- [ ] `messaging/` module: publish helper, push-envelope parser, idempotency check
      stub. Build this now — every later phase depends on the shape.
- [ ] One Dockerfile, three entrypoints (`main.py`, `worker.py`, `job.py`); deploy
      the API service and the worker service to Cloud Run and register the Job.

### ADK scaffold
- [ ] Install Google ADK; stand up a root agent with one trivial tool and confirm it
      executes on Cloud Run, not just locally. **ADK is a hard rules requirement —
      prove it runs in the deployed environment on day one.**
- [ ] Establish the pattern that will hold for the whole build: the tool body is a
      plain Python function in `core/`, and the ADK registration is a thin wrapper
      in `adk/`. Write one test that calls the plain function directly.

### Web (`web/`)
- [ ] Next.js App Router + TypeScript + Tailwind + shadcn/ui initialized.
- [ ] `lib/api.ts` — single typed fetch client reading `NEXT_PUBLIC_API_URL`.
- [ ] Home page listing markets from the live API.
- [ ] Deployed to Vercel with the env var pointing at Cloud Run.

### CI
- [ ] **Cloud Build** `cloudbuild.yaml`: lint → unit test → build one image →
      push to Artifact Registry (SHA-tagged) → deploy API service, worker service,
      and the Job, all pinned to the SHA.
- [ ] PR trigger running lint + test only.
- [ ] Practise the rollback command once and write it in the README.
- [ ] Keep it one file. No build-config sprawl.

### Secrets & config
- [ ] **Secret Manager** for anything secret; Cloud Run mounts via `--set-secrets`.
      Grant `secretmanager.secretAccessor` per-secret, not project-wide.
- [ ] Non-secret config (model id, thresholds, topic names, limits) stays in plain
      env vars so it is visible and greppable.
- [ ] Prefer workload identity over API keys for Google APIs. Count the secrets that
      actually exist — ideally close to zero.
- [ ] `scripts/setup.sh`: every `gcloud` provisioning command, re-runnable. This is
      the IaC substitute and it feeds the README's spin-up section.

### Observability baseline — see `../04-observability.md`
- [ ] **`trace_id` end to end**: generated at upload, returned in the 202, stored on
      the document, set as a Pub/Sub message attribute, present on every log line
      and every `graph_event`. Build it now — retrofitting means touching every
      handler.
- [ ] Structured JSON logging helper. No `print`, no bare strings, ever.
- [ ] OpenTelemetry FastAPI instrumentation → Cloud Trace, on both services.
- [ ] Enable Error Reporting.
- [ ] Uptime checks on both `/health` endpoints.
- [ ] Budget alert (already listed above — this is the first of the five alerts).

### Local dev
- [ ] **`docker-compose.yml`**: firestore-emulator, pubsub-emulator, a one-shot
      idempotent `pubsub-init` creating topics and **push** subscriptions pointing at
      the `worker` container, plus api, worker, and web with hot reload.
      Push locally, push in production — never poll in one and push in the other.
- [ ] `FAKE_LLM=1` mode returning canned responses. Phase 6's test suite depends on
      it, so the switch goes in now even though the fixtures come later.
- [ ] `docker compose up` is the entire local setup instruction.
- [ ] `README.md` at repo root: prerequisites, env vars, one command to run.

## Exit criteria

- [ ] A public Vercel URL renders two markets that came from Firestore via Cloud Run.
- [ ] `GET /health` returns `firestore: "ok"` from the deployed service.
- [ ] Publishing to `document.uploaded` in the deployed project causes the deployed
      worker to write a Firestore record. Verified in Cloud Run logs.
- [ ] An ADK agent with one tool executes successfully **on Cloud Run**.
- [ ] The pinned Gemini 3.5+ model identifier is confirmed and a one-line completion
      succeeds against it.
- [ ] A pushed commit deploys both services without manual steps.
- [ ] `docker compose up` from a clean clone brings up the full stack, and a locally
      published message reaches the local worker.
- [ ] Cloud Build deploys both services and the Job from a push, and the rollback
      command has been executed successfully once.
- [ ] A log line from the deployed worker carries the same `trace_id` as the API
      request that triggered it — verified by one Cloud Logging query.
- [ ] Budget alert is active; quota check recorded in the README.

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
