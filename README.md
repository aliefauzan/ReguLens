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
regulation enters — a watched regulator address re-read on a schedule, a
                    bundled library entry, an uploaded PDF, or pasted text
  -> a deterministic pass reads the document's own words for jurisdiction,
     publisher, source type and effective date (no model call); a low-confidence
     guess is handed back to the user, never silently defaulted
  -> extracted into structured, confidence-scored clauses by the ADK Extraction
     Agent (two samples per part, run concurrently, for self-consistency)
  -> deterministic guardrail decides whether two clauses may be compared
  -> the ADK Reconciliation Agent is consulted ONLY on a genuinely ambiguous
     same-jurisdiction pair, and it must walk the guardrail's tools to reach
     its verdict
  -> transactional verdict mutates the knowledge graph + audit event
  -> impact engine re-evaluates every affected product and market
  -> product status flips on its own; an alert names the cause and the sources
```

A first-time user with no regulation of their own starts from the built-in
library — verbatim excerpts of the two real corpus regulations — and still gets
a grounded answer. Every uploaded clause, every library clause and every clause
read off a watched address travels the identical hash → store → publish →
extract → reconcile path.

## Watching for changes, without being asked

A compliance tool that only knows what somebody remembered to upload is a
checker, not a monitor. `/sources` is the watch list: a regulator's own address,
re-read on a schedule, so a rule that moves overnight is in the graph before
anyone goes looking for it.

- **Cloud Scheduler → worker, daily 06:00 Asia/Jakarta.** One HTTP call to
  `/internal/check-sources`, OIDC-gated like every other internal route. The
  same sweep runs on demand from the "Check now" button on any row.
- **A change means the *wording* changed, not the bytes.** EUR-Lex stamps a
  fresh session id into every response, so a byte hash reports a change — and
  bills a model run — every single night. The change signal is a hash of the
  extracted text. Conditional GET (`ETag` / `If-Modified-Since`) short-circuits
  ahead of that where a server supports it. A check that finds nothing never
  reaches Gemini.
- **What works from a laptop may not work from Cloud Run.** EUR-Lex answers a
  datacentre address with `202 Accepted` and a two-kilobyte challenge page. The
  seeded EU source therefore points at CELLAR, the Publications Office's own
  machine-readable endpoint, which serves the same 48,417 characters of the same
  regulation *and* sends an `ETag`. Found by deploying it, watching it fail in
  production, and reading the log — which is why an empty 2xx body now has its
  own error message instead of being reported as "a login page".
- **Four kinds of address, because "changed" means four different things.**
  `document` is one regulation whose wording can change under you — it can only
  ever tell you that a rule you already hold was edited. The other three find
  rules you have never seen: `feed` (RSS or Atom, a new entry appeared),
  `listing` (a regulator's index page, a new *link* is a new act), and `sparql`
  (a publisher's catalogue, asked directly). Adopting any of the three records
  what it already carries and reads none of it, then reads at most three new
  items per run.
- **Asked, not scraped, where the publisher offers it.** A listing depends on a
  regex still matching a page a designer may rewrite. A catalogue query depends
  on the publisher's own classification of its own acts, which is what that
  classification is for. The EU offers one — and needs it, because EUR-Lex's web
  pages refuse datacentre addresses outright. The seeded query asks the
  Publications Office for regulations carrying the EuroVoc *food additive*
  concept, filtered by CELEX shape to acts rather than merger notices and
  proposals: 133 works a year carry that concept, of which roughly a dozen are
  regulations.
- **A failure that can never succeed is remembered; one that might is not.**
  BPOM's Kategori Pangan annex is 308 pages and will be 308 pages tomorrow, so
  refusing it is final. A timeout or an empty page is not — EUR-Lex serves an
  empty challenge page to datacentre addresses, and giving up on a regulation
  because it was briefly behind one is the worse mistake. Without the
  distinction the same oversized PDF is downloaded and refused every night,
  holding a slot in the per-run cap a readable new regulation needed.
- **No back door.** A change is ingested by calling the same
  `documents.create_document` an upload calls. Same hash, same Pub/Sub message,
  same extraction, same guardrail, same review queue. Nothing read from a
  watched address can become a clause by a route an upload could not use — a
  news item comes in at authority tier 0.35 and waits for a human.
- **A broken source says so.** A 403, a login wall, a PDF with no text layer:
  each is recorded on the source and rendered on the page. A source that has
  been erroring for a week means nobody is watching it, and that has to be
  visible or the monitoring claim is a lie.
- **Refused, not truncated.** A document past `MAX_FETCH_CHARS` is rejected
  with a reason. A confident answer drawn from the half of a regulation that
  happened to fit is worse than no answer.

Four addresses ship registered, all verified against the live endpoints before
being written down:

| Address | Kind | Answers |
|---|---|---|
| Publications Office SPARQL endpoint | `sparql` | "Which food-additive regulations has the EU published lately?" — including ones at addresses nobody has seen |
| `publications.europa.eu/resource/celex/32023R2108` | `document` | "Has this specific additives amendment been rewritten?" |
| `food.ec.europa.eu/node/2/rss_en` | `feed` | "What has the Commission announced?" — news, tier 0.35, so it waits for a human |
| `jdih.pom.go.id/` | `listing` | "What has BPOM published?" — new links on the portal index |

Both markets can therefore discover a regulation nobody knew about; watching a
document you already hold could only ever report that it was edited.

A fifth route exists and is deliberately unseeded: EUR-Lex serves a saved search
as RSS, which plugs into `feed` with no code at all. It is the right tool for a
scope narrower or wider than the seeded query, but the feed id is tied to a
EUR-Lex account, so there is nothing generic to ship.

## Why you can trust the answers

- **Deterministic code owns every mutation.** A model response never reaches
  Firestore without passing a Pydantic validator and the guardrail.
- **Computed confidence, not self-reported**: `0.3*parse_quality +
  0.4*self_consistency + 0.3*authority_tier`. Low-authority sources are capped
  by construction and routed to a human review queue instead of mutating state.
- **Grounded query**: the answer comes from an ADK agent choosing its own
  retrieval tools, but every clause id those tools serve is recorded, and the
  answer's citations are validated in code against that record. An id the model
  invented cites nothing. When the agent has no relevant evidence it says so in
  one fixed word that typed code turns into an explicit refusal — because an
  agent left to phrase its own emptiness will write "I have no information" and
  cite the clauses it looked at anyway, which is an ungrounded answer wearing a
  grounded answer's citations. That exact failure happened, and the deployed
  E2E caught it.
- **Audit trail**: every state change writes an immutable `graph_events`
  record; `scripts/` walker asserts state and events agree.
- **The engine does not know it is a web app.** `api/app/core/` imports neither
  FastAPI nor ADK — checkable with one grep. Agents are confined to four files
  in `api/app/adk/` that register tools whose bodies are plain functions in
  `core/`, so every decision in this system runs and tests without an agent
  framework or a web server.
- **An alert says why.** A verdict that moved names the regulation that moved
  it, and whether anybody uploaded that regulation. `GET /stats/autonomy` counts
  the same thing from stored records — regulations found unprompted, rules read
  out of them, verdicts changed — so "it watches for changes" is a number you
  can click through, not a sentence in a README.
- **A rule that cannot apply to you is not put in front of you.** The review
  queue is filtered to what could bear on products in the workspace, computed on
  every read so adding a product changes it with no migration. Nothing is
  deleted or downgraded, and the queue always says how many rules it is holding
  back and why.

## Architecture

Three Cloud Run runtimes from one container image, plus a fourth for the web,
one Cloud Run Job, Cloud Scheduler driving the daily source sweep, Pub/Sub push
with dead-lettering, Firestore, Cloud Storage, Secret Manager, and Gemini 3.5
through either Vertex AI or the Gemini Developer API.

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
Two ways in. Both end up on the same Pub/Sub message.

A. Exporter (browser)
     -> regulens-web (Cloud Run, public)
     -> regulens-api (Cloud Run, public)   -- uploads a PDF or pastes text

B. Cloud Scheduler, 06:00 Asia/Jakarta
     -> regulens-worker /internal/check-sources (OIDC)
     -> re-reads every watched address: a known act (has the wording changed?),
        a feed, a regulator's index, a catalogue query (what is new?)
     -> nothing changed  -> a conditional GET and a hash comparison. No model call.
     -> something changed -> create_document, the SAME call an upload makes

                          both paths publish --> Pub/Sub: document.uploaded
                                                       |  push, OIDC
                                                regulens-worker (Cloud Run, private)
   /internal/document-uploaded -> extract (Extraction Agent x2)  -> clause.extracted
   /internal/clause-extracted  -> reconcile (guardrail; Reconciliation
                                  Agent only when ambiguous)     -> graph.changed
   /internal/graph-changed     -> impact (pure code, no model)   -> Firestore verdict + graph_events
   /internal/dead-letter       <- any topic after max retries
  -> alerts, readiness, timeline, grounded query
```

There is no third way in. A regulation discovered by the scheduler is hashed,
stored, published, extracted, guardrailed and reviewed exactly as an upload is —
which is why a news item found in a feed lands in the review queue at authority
tier 0.35 instead of quietly moving a limit.

| ADK agent | Runs | What it actually does | Honest label |
|---|---|---|---|
| Extraction | every document, twice per part | loads its part through its own tool, emits candidates through another | pipeline, one LLM step |
| Reconciliation | only on a genuinely ambiguous pair | must walk comparability → classification → judge; the tool graph, not the prompt, stops it judging a pair the guardrail rejected | code decides, agent advises |
| Query | every question | picks its own retrieval tools; every id its tools serve is recorded and the answer's citations are checked against that record | genuinely agentic |
| Impact | every graph change | requirements, evaluation, status rollup | **no agent and no model call at all** |

Google ADK is used throughout; every tool body is a plain Python function in
`api/app/core/` that runs and tests without ADK.

Two things worth being precise about, because both are easy to overclaim.
**Reconciliation deliberately does not run per clause**: a 55-clause annex would
be 55 agent runs on the critical path, and the common case is settled by typed
code in microseconds — so the agent is wired exactly where the LLM judge was
already the only option. **Impact has no agent at all**, on purpose: turning a
limit and a measured amount into pass or fail is arithmetic, and arithmetic
should not be delegated to a model. A fourth agent (`app/adk/agent.py`) exists
only as the phase-0 smoke test that proves ADK executes on Cloud Run, and is
labelled as such rather than counted as a fifth pipeline stage.

When any agent fails, the deterministic path underneath it runs instead and the
failure is logged. A degraded answer is worth having; a wrong one is not.

## Tech stack

Next.js 16 (App Router) · FastAPI · Google ADK 2.7 · Gemini 3.5 through **either**
Vertex AI (`gemini-3.5-flash` global endpoint; `text-multilingual-embedding-002`
in asia-southeast1) **or** the Gemini Developer API (`gemini-3.5-flash` +
`gemini-embedding-001`), chosen at runtime by whether `GEMINI_API_KEY` is set ·
Firestore · Cloud Storage · Pub/Sub push · Secret Manager · Cloud Run x4 ·
Cloud Run Jobs · Artifact Registry · Cloud Build · Cloud Logging.

## Repository layout

```
api/app/main.py        API service (upload, detect, delete documents, products,
                       clauses, conflicts, compliance, alerts, query, library,
                       substances, debug view)
api/app/worker.py      Pub/Sub push consumers: extract / reconcile / impact / DLQ,
                       plus the scheduled watched-source sweep
api/app/job.py         Cloud Run Job: idempotent demo seed
api/app/core/          the plain-Python engine: extraction/, detection.py (what is
                       this document), guardrail.py, reconciliation.py, impact.py,
                       query.py, citations.py (grounded source spans),
                       normalization.py, substances.py, library.py + library_data.json,
                       sources.py + fetching.py (watched regulator addresses),
                       relevance.py (which rules bear on this workspace),
                       alerts.py + autonomy.py (why a verdict moved, and what
                       was done unprompted), integrity.py (state vs event walker)
api/app/adk/           the four ADK agents: extraction, reconciliation, query,
                       plus the phase-0 smoke test. Registrations only — every
                       tool body is a plain function in core/
api/tests/             392 unit tests + fixture corpus + live-Vertex eval
web/                   Next.js app (twin, self-describing upload + stepper,
                       readiness, timeline, ask panel, conflicts, review queue,
                       rulebook, watch list, cited source-text view)
data/regulations/      real source PDFs (EU + BPOM) with provenance in SOURCES.md
Makefile               `make test-all` — lint, tests, build, local drill, one table
firestore.indexes.json the three composite indexes; `setup.sh` submits them
regulens.env.example   the one file a clone edits (copy to regulens.env)
scripts/quickstart.sh  clone to running stack, one command
scripts/setup.sh       GCP provisioning on its own (idempotent)
scripts/build_library.py  rebuild api/app/core/library_data.json from the corpus
scripts/measure_latency.py  upload -> re-evaluated, stage by stage
scripts/verify_e2e.sh  end-to-end verification against the deployed stack
scripts/verify_local.sh  same drill against the local emulator stack
plan/                  full build plan and per-phase evidence trail
```

## Run it in the cloud — one file, one command

You edit one file and run one script. No hostname to paste anywhere: Cloud Run
publishes a service at `https://SERVICE-PROJECTNUMBER.REGION.run.app`, which is
known before the first deploy, so the URLs are computed rather than configured.

```bash
gcloud auth login && gcloud auth application-default login

cp regulens.env.example regulens.env    # set PROJECT_ID; GEMINI_API_KEY optional
bash scripts/quickstart.sh
```

That provisions the infrastructure (APIs, Firestore, GCS, Pub/Sub topics and
push subscriptions with OIDC and dead-lettering, service accounts with narrow
IAM), stores your key in Secret Manager and grants both services access,
deploys api + worker + job + web, wires the push subscriptions once the worker
has a URL, seeds the demo baseline, and prints the URL to open. Every step is
idempotent — run it again after a code change and it redeploys, touching
nothing that already exists.

`GEMINI_API_KEY` is optional. Leave it empty and every model call goes to Vertex
AI, which works identically and bills per token. Set it and the same calls go to
the Gemini Developer API, whose free tier covers these models — but the key must
come from a project with **no billing linked**, or the free tier disappears.

The steps individually, if you would rather run them yourself:

```bash
PROJECT_ID=your-project-id bash scripts/setup.sh     # infrastructure
gcloud builds submit --config cloudbuild.yaml \      # build + deploy
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)-$(date +%H%M%S),\
_API_URL=https://regulens-api-NUMBER.REGION.run.app,\
_WEB_ORIGINS=https://regulens-web-NUMBER.REGION.run.app
PROJECT_ID=your-project-id bash scripts/setup.sh     # push subscriptions
gcloud run jobs execute regulens-job --region "$REGION" --wait
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

## One command

```bash
make test-all
```

Lint, unit tests, a type check, a production web build, and — if Docker is up —
the whole pipeline drill against emulators: upload, extract, reconcile, open a
conflict, flip a market unprompted, redeliver a message and prove nothing
duplicated. It prints a pass/fail table and nothing else, costs nothing, and
touches no Google Cloud project.

```
STEP                         RESULT
----                         ------
ruff (api)                   PASS
pytest (api)                 PASS
tsc (web)                    PASS
next build (web)             PASS
local e2e drill              PASS
```

`make help` lists the rest. `make verify-deployed` runs the same drill against
the deployed stack — kept as a separate target on purpose, because it spends
money and mutates a real workspace.

## Tests and verification

```bash
cd api
pytest -q                       # 279 unit tests, no network
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

`measure_latency.py` deletes the document it uploaded when it is done — pass
`KEEP=1` to inspect it instead. That is not tidiness: six unattended runs left
six near-identical copies of the same EU regulation in the demo workspace, and
the next verification run counted them as nine open conflicts and six separate
benzoate clauses. A measurement that changes what the next measurement sees is
not a measurement.

### What the E2E proved, and what it cannot

Run 29 Aug against the live stack, with the ADK agents on the answer path:

| Check | Result |
|---|---|
| Baseline: Indonesia compliant, Germany unknown | pass |
| EU excerpt uploaded, extracted | pass |
| Cross-jurisdiction conflict opens | pass |
| Germany flips `non_compliant` with no user action | pass |
| Alert fires naming market, clause and transition | pass |
| Grounded answer cites stored clauses | pass — 8 citations, `refusal: false` |
| No data for Japan | pass — `refusal: true`, 0 citations |
| Identical re-upload hits the cache | pass |
| Redelivered `document.uploaded` creates no duplicate clauses | pass — 42 before, 42 after |

**`verify_e2e.sh` has a precondition it now states out loud.** The headline it
checks is that Germany flips *without being asked*, and that can only be watched
on a workspace holding no EU rules yet. A workspace that has loaded the bundled
rulebook already has them, so the flip has already happened and the drill has
nothing left to observe. It says exactly that and exits non-zero, rather than
asserting something that cannot hold. `verify_local.sh` gets a wiped stack every
time, which is why the flip is proven there on every run.

Four defects that suite found, all fixed rather than filed:

1. **The grounded-query regression** described above — an answer saying "I have
   no information" while citing clauses, reported as grounded.
2. **The script reported `ALL CHECKS PASSED` while a check crashed.** Every check
   was a pipeline ending in a Python assertion and nothing read the exit status,
   so a query that came back empty printed a traceback into a passing run. Each
   check now ends in `|| fail "<name>"`. That fix immediately exposed the third.
3. **The baseline check had been failing in silence on every re-run**, because
   the script uploads the EU document and never removed it. It cleans up after
   itself now, so the run is repeatable.
4. **There was no way to delete a document.** A product could always be deleted;
   the PDF you uploaded by mistake was permanent unless you had Firestore
   access. That is also how six copies of one regulation accumulated in the demo
   workspace during latency measurement. `DELETE /documents/{id}` removes the
   document, its clauses, the requirements they produced, the conflicts they
   opened and the debug record, then re-evaluates every affected product — a
   delete that leaves a stale red verdict on screen is worse than no delete.

**Query latency, measured on the deployed stack:** 19–28s for a grounded answer.
The agent chooses its own tools, and each choice is a model turn. Two changes cut
it from a measured 42s: repeated searches within one run are answered from the
first result, and the retrieval the caller already did is handed to the agent up
front so searching is no longer compulsory. It is still the slowest thing a user
can press, and it is a question they asked rather than a page waiting to load.

## Configuration

One file: [`regulens.env`](regulens.env.example), read by `quickstart.sh`,
`setup.sh`, `verify_e2e.sh` and `measure_latency.py`. A real environment
variable always wins over it, so CI needs no file at all. It is gitignored;
`regulens.env.example` is the copy in the repo.

Only `PROJECT_ID` is required. Everything below is the full set of knobs,
including the ones the services read directly in production.

| Env var | Default | Purpose |
|---|---|---|
| `PROJECT_ID` | none — must be set | GCP project. The fallback is a name that does not exist, so a clone that forgets fails loudly instead of reading someone else's data |
| `REGION` | `asia-southeast1` | Cloud Run, Firestore, GCS, Pub/Sub, embeddings |
| `UPLOADS_BUCKET` | `<project-id>-uploads` | derived, because bucket names are globally unique |
| `GEMINI_API_KEY` | unset | when set, every model call goes to the Gemini Developer API; unset keeps the Vertex path |
| `GEMINI_MODEL` | `gemini-3.5-flash` | pinned 3.5+ model |
| `FAKE_LLM` | off | deterministic offline mode |
| `DEBUG_VIEW` | off | enables `/debug/documents/{id}` |
| `NEXT_PUBLIC_API_URL` | localhost:8080 | API URL used by the browser; baked into the web image at build time by `cloudbuild.yaml` |
| `API_INTERNAL_URL` | unset | API URL used by server components (compose: `http://api:8080`) |
| `FIRESTORE_DATABASE` | `(default)` | set to `local` against the emulator |
| `LOCAL_STORAGE_DIR` | unset | filesystem uploads instead of GCS (local only) |
| `SOURCE_SPARQL_LOOKBACK_DAYS` | `120` | how far back a catalogue query asks; a fixed window, so a missed run cannot open a silent gap |
| `SOURCE_CHECK_INTERVAL_HOURS` | `24` | default re-read interval for a new watched source |
| `SOURCE_MAX_NEW_PER_CHECK` | `3` | most feed entries read in one run, so an overnight burst is not an unbounded bill |
| `MAX_FETCH_CHARS` | `200000` | a watched document past this is refused, not truncated |
| `MAX_FETCH_MB` | `20` | download ceiling per fetch |
| `FETCH_TIMEOUT_SECONDS` | `30` | per-request timeout when reading a watched address |
| `SOURCE_USER_AGENT` | ReguLens/1.0 … | what regulator sites see in their logs |

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
  A watched address is read the same way, so a scanned PDF behind a URL fails
  there for the same reason it fails on upload.
- Watching is a scheduled re-read, not a subscription. The floor on noticing a
  change is the source's check interval — 24 hours by default — because no
  regulator in the corpus publishes a webhook. A user who needs it sooner
  presses "Check now" or shortens the interval.
- A watched source is registered by hand, and a `listing` needs a pattern saying
  which of its links are regulations while a `sparql` source needs a query. There is no crawler that works out
  by itself which page a regulator publishes on, and a listing registered as a
  `document` will be read as one document rather than followed. A pattern that
  stops matching — a site redesign — is reported as an error rather than as "no
  new regulations", because those two would otherwise look identical.
- The seeded EU query is scoped to one EuroVoc concept, *food additive*. A
  regulation about, say, contaminants or packaging materials is outside it and
  will not be found. That is a deliberate scope, not a bug — an unscoped query
  returns everything the EU publishes — but it means the watch list is only as
  wide as the concepts somebody chose.
- A listing only sees what its index page shows. JDIH's front page carries the
  twelve most recent items; a regulation published and pushed off that list
  between two checks would be missed. At a daily interval against a portal that
  publishes a few items a month this has slack to spare, but it is a window, not
  a guarantee.
- There is no per-source relevance filter. Watching one broad annex put 68
  clauses into the review queue in a single scheduled run, most of them nitrite
  limits for cured meats that no product in the workspace resembles. That is the
  guardrail behaving correctly — none of them silently changed a verdict — and
  it is also a queue nobody will read. Filtering at ingestion by product family
  is the fix and it is not built.
- BPOM's JDIH portal is reachable and serves stable PDF URLs, but the annexes
  that matter run to 308 pages — past `MAX_DOCUMENT_PAGES`. Nothing from BPOM
  ships in the watch list for that reason; a user can register a specific
  annex and will get an explicit size refusal if it is too large.
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
