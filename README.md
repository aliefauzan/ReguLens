# ReguLens

**A living compliance twin for small exporters.**
Describe a product once. ReguLens ingests real regulations, decides what
applies to your product in each destination market, and when a new regulation
arrives it tells you — unprompted — what just broke, why, and with which
sources.

| Live environment | URL |
|---|---|
| Web app | https://regulens-web-babuvy7w3a-as.a.run.app |
| API | https://regulens-api-babuvy7w3a-as.a.run.app |

A 5-minute click-by-click walkthrough lives in
[docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## The core loop

```
regulation document arrives
  -> extracted into structured, confidence-scored clauses (Gemini x2 samples)
  -> deterministic guardrail decides whether two clauses may be compared
  -> judge (LLM) only settles genuinely ambiguous same-jurisdiction pairs
  -> transactional verdict mutates the knowledge graph + audit event
  -> impact engine re-evaluates every affected product and market
  -> product status flips on its own; an alert names the cause and the sources
```

## Why you can trust the answers

- **Deterministic code owns every mutation.** A model response never reaches
  Firestore without passing a Pydantic validator and the guardrail.
- **Computed confidence, not self-reported**: `0.3*parse_quality +
  0.4*self_consistency + 0.3*authority_tier`. Low-authority sources are capped
  by construction and routed to a human review queue instead of mutating state.
- **Grounded query**: every answer must cite stored clause ids; citations are
  validated in code against the retrieved set. No data means an explicit
  refusal — never world-knowledge guesses about regulations.
- **Audit trail**: every state change writes an immutable `graph_events`
  record; `scripts/` walker asserts state and events agree.

## Architecture

Three Cloud Run runtimes from one container image, plus a fourth for the web:

```
Next.js web (Cloud Run, public)
        |
        v
API service (Cloud Run)  --publish-->  Pub/Sub: document.uploaded
        |                                      |
   Firestore                          Worker (Cloud Run, private)
   GCS uploads                        /internal/document-uploaded  -> extract (ADK agent)
                                              | clause.extracted
                                      /internal/clause-extracted -> reconcile (guardrail + judge)
                                              | graph.changed
                                      /internal/graph-changed -> impact (pure code)
                                              |
                                      alerts, readiness, timeline, query
```

| ADK agent | What it actually does | Honest label |
|---|---|---|
| Extraction | fixed pipeline; Gemini structured output x2 samples | pipeline, one LLM step |
| Reconciliation | guardrail gates pairs; judge only on ambiguous same-jurisdiction pairs | code decides, judge advises |
| Impact | requirements, evaluation, status rollup | **no model call at all** |
| Query | retrieval + grounded synthesis with citation validation | genuinely agentic |

Google ADK is used throughout; every tool body is a plain Python function in
`api/app/core/` that runs and tests without ADK.

## Tech stack

Next.js 16 (App Router) · FastAPI · Google ADK 2.7 · Vertex AI
(`gemini-3.5-flash` global endpoint; `text-multilingual-embedding-002` in
asia-southeast1) · Firestore · Pub/Sub push · Cloud Run x4 · Cloud Run Jobs ·
GCS · Cloud Build.

## Repository layout

```
api/app/main.py        API service (upload, products, clauses, conflicts,
                       compliance, alerts, query, debug view)
api/app/worker.py      Pub/Sub push consumers: extract / reconcile / impact / DLQ
api/app/job.py         Cloud Run Job: idempotent demo seed
api/app/core/          the plain-Python engine: extraction/, guardrail.py,
                       reconciliation.py, impact.py, query.py, normalization.py
api/app/adk/           thin ADK registrations over those functions
api/tests/             62 unit tests + fixture corpus + live-Vertex eval
web/                   Next.js app (twin, upload+stepper, readiness, timeline,
                       ask panel, conflicts, review queue)
data/regulations/      real source PDFs (EU + BPOM) with provenance in SOURCES.md
scripts/setup.sh       one-command GCP provisioning (idempotent)
scripts/verify_e2e.sh  end-to-end verification against the deployed stack
scripts/verify_local.sh  same drill against the local emulator stack
plan/                  full build plan and per-phase evidence trail
```

## Run it in the cloud (from a bare GCP project)

The deployed stack was built exactly this way; every step is idempotent.

```bash
# 1. Prerequisites: gcloud CLI, a GCP project with billing linked, Owner role.
gcloud auth login && gcloud auth application-default login

# 2. Provision everything: APIs, Firestore, GCS, Pub/Sub topics + push
#    subscriptions with OIDC and dead-lettering, service accounts with narrow
#    IAM, budget alert. Re-running is a no-op.
export PROJECT_ID=your-project-id
PROJECT_ID=$YOUR_PROJECT_ID bash scripts/setup.sh

# 3. Deploy API + worker + job + web in one pipeline.
gcloud builds submit --project $YOUR_PROJECT_ID --config cloudbuild.yaml \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)-$(date +%H%M%S)

# 4. Push subscriptions need the worker URL, so re-run provisioning once.
PROJECT_ID=$YOUR_PROJECT_ID bash scripts/setup.sh

# 5. Edit cloudbuild.yaml once: point NEXT_PUBLIC_API_URL and the CORS origin
#    at your real *.run.app URLs (they are derived from project id).

# 6. Seed the demo baseline (idempotent).
gcloud run jobs execute regulens-job --region asia-southeast1 \
  --project $YOUR_PROJECT_ID --wait
```

## Run it locally — no GCP, no cost

The whole system runs on your machine: Firestore and Pub/Sub emulators, a
filesystem stand-in for Cloud Storage, and `FAKE_LLM=1` canned extraction. No
credentials, no billing, no network calls to Google.

```bash
docker compose up -d firestore pubsub api worker web
docker compose up pubsub-init                 # creates topics + push subscriptions
curl -X POST http://localhost:8080/markets/seed
docker compose run --rm api python -m app.job # demo baseline, idempotent
open http://localhost:3000
```

| Service | URL |
|---|---|
| Web | http://localhost:3000 |
| API | http://localhost:8080 |
| Worker | http://localhost:8081 |

One command verifies the whole local pipeline end to end:

```bash
bash scripts/verify_local.sh
```

It asserts the baseline (Indonesia compliant, Germany unknown), uploads the
real EU excerpt PDF, waits for extraction, checks that a cross-jurisdiction
conflict opens, that Germany flips to non-compliant **with no user action**,
that an alert fires, that an identical re-upload hits the cache, and that a
redelivered Pub/Sub message creates no duplicate clauses.

**What local mode proves:** the pipeline, the push wiring, idempotency, the
guardrail, the conflict rule, the impact flip, and every screen in the UI.

**What it cannot prove:** extraction accuracy, embedding quality, judge
behaviour, IAM, and real Vertex output — `FAKE_LLM` returns canned clauses
keyed on the document text (an Indonesian source yields 400 mg/kg, an EU source
150 mg/kg). For those, run `scripts/verify_e2e.sh` against the deployed stack.

Two local details worth knowing, both env-driven and absent in production:
`FIRESTORE_DATABASE=local` (the emulator rejects the URL-encoded `(default)`
id the client sends) and `LOCAL_STORAGE_DIR` (there is no Cloud Storage
emulator, so api and worker share an uploads volume).

### Run services directly against your own GCP project

```bash
cd api
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

export PROJECT_ID=your-project-id
uvicorn app.main:app --port 8080        # API
uvicorn app.worker:app --port 8081      # worker (second terminal)

cd ../web && npm install && npm run dev  # web (third terminal)
```

The browser reads `NEXT_PUBLIC_API_URL` (default http://localhost:8080); server
components read `API_INTERNAL_URL` when set. `FAKE_LLM=1` gives deterministic
offline behaviour without Vertex calls.

## Tests and verification

```bash
cd api
pytest -q                       # 62 unit tests, no network
REGULENS_EVAL=1 pytest tests/test_extraction_quality.py -q -s
                                # live-Vertex fixture accuracy (costs tokens)

bash scripts/verify_local.sh    # full E2E against the local emulator stack
                                # (free, offline, ~2 minutes)

bash scripts/verify_e2e.sh      # full E2E against the deployed stack:
                                # baseline, EU upload, conflict, unprompted
                                # flip, alert, grounded query, refusal,
                                # cache hit, Pub/Sub redelivery
```

`PYTHONPATH=. python -m app.core.integrity` walks live state vs the event log.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PROJECT_ID` | `regulens-506014` | GCP project |
| `GEMINI_MODEL` | `gemini-3.5-flash` | pinned 3.5+ model |
| `FAKE_LLM` | off | deterministic offline mode |
| `DEBUG_VIEW` | off | enables `/debug/documents/{id}` |
| `NEXT_PUBLIC_API_URL` | localhost:8080 | API URL used by the browser |
| `API_INTERNAL_URL` | unset | API URL used by server components (compose: `http://api:8080`) |
| `FIRESTORE_DATABASE` | `(default)` | set to `local` against the emulator |
| `LOCAL_STORAGE_DIR` | unset | filesystem uploads instead of GCS (local only) |

Secrets: none exist. Everything authenticates via workload identity / service
accounts; nothing to leak.

## Rollback

```bash
gcloud run services update-traffic regulens-api --region asia-southeast1 \
  --to-revisions PREVIOUS_REVISION=100
```

Use revisions, not images — redeploying an older image keeps newer env vars
and lies about what is running.

## Honest limitations

- Numeric limits only are evaluated pass/fail. Labelling, certification and
  documentation clauses are extracted and surfaced as `needs_review`, never
  silently counted as checks we did not run.
- Uploads are PDFs with a text layer plus pasted text. No OCR, no screenshots.
- One hardcoded workspace; no auth. `/internal/*` endpoints are private and
  OIDC-gated — that is the security boundary that matters here.
- Propagation latency measured ~183s in an unattended run against a 90s
  target; double-sampling and judge calls dominate. Recorded, not hidden.
- The substance-family table (benzoates, sorbates) is documented domain
  mapping, not inferred magic; both source regulations state the shared basis.
- Readiness shows issue counts, not a percentage — we do not claim coverage
  we do not have.

## Evidence trail

`plan/PROGRESS.md` and `plan/phases/phase-*.md` carry per-box evidence for
every claim above — live drill results, fixture accuracy, latency
measurement, and the honest gaps. `data/regulations/SOURCES.md` documents the
real regulation corpus with checksums.
