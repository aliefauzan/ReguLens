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
regulation enters — bundled library entry, uploaded PDF, or pasted announcement
  -> a deterministic pass reads the document's own words for jurisdiction,
     publisher, source type and effective date (no model call); a low-confidence
     guess is handed back to the user, never silently defaulted
  -> extracted into structured, confidence-scored clauses (Gemini x2 samples)
  -> deterministic guardrail decides whether two clauses may be compared
  -> judge (LLM) only settles genuinely ambiguous same-jurisdiction pairs
  -> transactional verdict mutates the knowledge graph + audit event
  -> impact engine re-evaluates every affected product and market
  -> product status flips on its own; an alert names the cause and the sources
```

A first-time user with no regulation of their own starts from the built-in
library — verbatim excerpts of the two real corpus regulations — and still gets
a grounded answer. Every uploaded clause and every library clause travels the
identical hash → store → publish → extract → reconcile path.

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

Three Cloud Run runtimes from one container image, plus a fourth for the web,
one Cloud Run Job, Pub/Sub push with dead-lettering, Firestore, Cloud Storage,
Secret Manager, and Gemini 3.5 through either Vertex AI or the Gemini Developer
API.

![ReguLens on Google Cloud](docs/architecture.png)

The diagram is generated, not drawn — [`docs/architecture.py`](docs/architecture.py)
uses [`mingrammer/diagrams`](https://github.com/mingrammer/diagrams) with GCP
nodes. Regenerate it after any infrastructure change:

```bash
brew install graphviz                      # or apt-get install graphviz
pip install -r docs/requirements.txt
python docs/architecture.py                # rewrites docs/architecture.png
```

The request path and the event pipeline in words:

```
Exporter (browser)
  -> regulens-web (Cloud Run, public)
  -> regulens-api (Cloud Run, public)  -- writes Firestore + GCS, publishes --> Pub/Sub: document.uploaded
                                                                                     |  push, OIDC
                                                                              regulens-worker (Cloud Run, private)
   /internal/document-uploaded -> extract (Gemini x2)            -> clause.extracted
   /internal/clause-extracted  -> reconcile (guardrail + judge)  -> graph.changed
   /internal/graph-changed     -> impact (pure code)             -> Firestore verdict + graph_events
   /internal/dead-letter       <- any topic after max retries
  -> alerts, readiness, timeline, grounded query
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

Next.js 16 (App Router) · FastAPI · Google ADK 2.7 · Gemini 3.5 through **either**
Vertex AI (`gemini-3.5-flash` global endpoint; `text-multilingual-embedding-002`
in asia-southeast1) **or** the Gemini Developer API (`gemini-3.5-flash` +
`gemini-embedding-001`), chosen at runtime by whether `GEMINI_API_KEY` is set ·
Firestore · Cloud Storage · Pub/Sub push · Secret Manager · Cloud Run x4 ·
Cloud Run Jobs · Artifact Registry · Cloud Build · Cloud Logging.

## Repository layout

```
api/app/main.py        API service (upload, detect, products, clauses, conflicts,
                       compliance, alerts, query, library, substances, debug view)
api/app/worker.py      Pub/Sub push consumers: extract / reconcile / impact / DLQ
api/app/job.py         Cloud Run Job: idempotent demo seed
api/app/core/          the plain-Python engine: extraction/, detection.py (what is
                       this document), guardrail.py, reconciliation.py, impact.py,
                       query.py, citations.py (grounded source spans),
                       normalization.py, substances.py, library.py + library_data.json,
                       integrity.py (state vs event-log walker)
api/app/adk/           thin ADK registrations over those functions
api/tests/             257 unit tests + fixture corpus + live-Vertex eval
web/                   Next.js app (twin, self-describing upload + stepper,
                       readiness, timeline, ask panel, conflicts, review queue,
                       rulebook, cited source-text view)
data/regulations/      real source PDFs (EU + BPOM) with provenance in SOURCES.md
scripts/setup.sh       one-command GCP provisioning (idempotent)
scripts/build_library.py  rebuild api/app/core/library_data.json from the corpus
scripts/measure_latency.py  upload -> re-evaluated, stage by stage
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
bash scripts/setup.sh

# 3. Put your Gemini Developer API key in Secret Manager. cloudbuild.yaml mounts
#    gemini-api-key:latest into api and worker, so the secret must exist and both
#    service accounts must be able to read it. The key must come from a project
#    with no billing linked, or the free tier disappears.
printf %s "$GEMINI_KEY" | gcloud secrets create gemini-api-key \
  --project "$PROJECT_ID" --data-file=- \
  || printf %s "$GEMINI_KEY" | gcloud secrets versions add gemini-api-key \
       --project "$PROJECT_ID" --data-file=-
for sa in regulens-api regulens-worker; do
  gcloud secrets add-iam-policy-binding gemini-api-key --project "$PROJECT_ID" \
    --member "serviceAccount:$sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role roles/secretmanager.secretAccessor
done

# 4. Deploy API + worker + job + web in one pipeline.
gcloud builds submit --project "$PROJECT_ID" --config cloudbuild.yaml \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)-$(date +%H%M%S)

# 5. Push subscriptions need the worker URL, so re-run provisioning once.
bash scripts/setup.sh

# 6. Edit cloudbuild.yaml once: point NEXT_PUBLIC_API_URL and the CORS origin
#    at your real *.run.app URLs (they are derived from project id).

# 7. Seed the demo baseline (idempotent).
gcloud run jobs execute regulens-job --region asia-southeast1 \
  --project "$PROJECT_ID" --wait
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
pytest -q                       # 257 unit tests, no network
REGULENS_EVAL=1 pytest tests/test_extraction_quality.py -q -s
                                # live-Vertex fixture accuracy (costs tokens)

bash scripts/verify_local.sh    # full E2E against the local emulator stack
                                # (free, offline, ~2 minutes)

python3 scripts/measure_latency.py \
  data/regulations/excerpts/EU-annex-II-14.1.4-flavoured-drinks-excerpt.pdf
                                # upload -> re-evaluated, stage by stage,
                                # against whichever stack $API points at

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
| `GEMINI_API_KEY` | unset | when set, every model call goes to the Gemini Developer API; unset keeps the Vertex path |
| `GEMINI_MODEL` | `gemini-3.5-flash` | pinned 3.5+ model |
| `FAKE_LLM` | off | deterministic offline mode |
| `DEBUG_VIEW` | off | enables `/debug/documents/{id}` |
| `NEXT_PUBLIC_API_URL` | localhost:8080 | API URL used by the browser |
| `API_INTERNAL_URL` | unset | API URL used by server components (compose: `http://api:8080`) |
| `FIRESTORE_DATABASE` | `(default)` | set to `local` against the emulator |
| `LOCAL_STORAGE_DIR` | unset | filesystem uploads instead of GCS (local only) |

Secrets: exactly one. `GEMINI_API_KEY` is stored in Secret Manager as
`gemini-api-key` and mounted into the api and worker services as an ordinary env
var (`cloudbuild.yaml`, `--set-secrets`). It is never committed — `.gitignore`
excludes every `.env` — and never logged. Everything else authenticates via
service accounts with narrow IAM. If `GEMINI_API_KEY` is unset the stack falls
back to Vertex AI and keeps working, so a missing secret is a cost line, not an
outage.

## Rollback

```bash
gcloud run services update-traffic regulens-api --region asia-southeast1 \
  --to-revisions PREVIOUS_REVISION=100
```

Use revisions, not images — redeploying an older image keeps newer env vars
and lies about what is running.

## Honest limitations

Things the system does not do. Not excuses — the list is here so nobody has to
discover them in a demo.

- Numeric limits only are evaluated pass/fail. Labelling, certification and
  documentation clauses are extracted and surfaced as `needs_review`, never
  silently counted as checks we did not run.
- Uploads are PDFs with a text layer plus pasted text. No OCR, no screenshots.
- One hardcoded workspace; no auth. `/internal/*` endpoints are private and
  OIDC-gated — that is the security boundary that matters here.
- Propagation latency scales with how many rules a document contains, not with
  pipeline overhead, and a dense annex misses the 90s target. Measured 29 Aug
  on the deployed stack with [`scripts/measure_latency.py`](scripts/measure_latency.py),
  upload to re-evaluated product:

  | Document | Clauses | Extraction | Reconciliation | Impact | Total |
  |---|---|---|---|---|---|
  | One pasted rule | 1 | 15.9s | 6.8s | 2.7s | **25.5s** |
  | EU Annex II excerpt, 4 pages | 55 | 125.7s | 47.9s | 0.7s | **174.3s** |

  Extraction is ~72% of the annex figure and is bound by output tokens: 55
  verbatim clauses have to leave the model. The two self-consistency samples
  run concurrently — logged at 95.9s and 110.4s inside a 110.4s window — so
  sampling twice costs wall clock only for the slower of the two, not the sum.
  The 90s target holds for announcement-sized documents and does not hold for
  an annex.

### Deliberate choices, not shortfalls

These read like limitations and are not. Each is a decision with a reason, and
the reason is recorded in `plan/PROGRESS.md` under **Decisions taken**.

- The substance-family table (benzoates, sorbates) is documented domain
  mapping, not inferred magic; both source regulations state the shared basis.
  A guessed equivalence would be worse than none.
- Readiness shows issue counts, not a percentage. A percentage would need a
  denominator — the number of rules that *should* apply — which nobody has.

## Evidence trail

`plan/PROGRESS.md` and `plan/phases/phase-*.md` carry per-box evidence for
every claim above — live drill results, fixture accuracy, latency
measurement, and the honest gaps. `data/regulations/SOURCES.md` documents the
real regulation corpus with checksums.
