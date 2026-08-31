# Production verification — 31 Aug 2026

What is checked against the **deployed** stack after `9376429`, and why each check
exists. Written before the run so the result cannot be graded on a curve.

Rule for every row: a claim counts only if the deployed system produced the
evidence. "It passes locally" is not evidence — three of the four faults found
earlier today were invisible on a developer machine and only existed in
production.

**Target:** `regulens-api-babuvy7w3a-as.a.run.app` · project `regulens-506014`
· region `asia-southeast1`

---

## A. Configuration and identity

| # | Check | Passes when |
|---|---|---|
| A1 | Deployed version | `/health` reports `9376429`; Firestore `ok` |
| A2 | Secrets exist | `gemini-api-key` v2 (real) and `gemini-discovery-key` both present, both readable by the api and worker service accounts |
| A3 | Secrets are **mounted** | `GEMINI_API_KEY` *and* `DISCOVERY_API_KEY` on both services. This is the check that failed last time: the secret existed and the env var did not |
| A4 | Which provider is live | Determined from evidence, not assumed. `use_gemini_api` decides generation *and* embeddings; the answer changes what A9 has to do |
| A5 | Pub/Sub topology | 5 topics + dead-letter; `country.requested.worker` pushes to `/internal/country-requested` |
| A6 | The route the subscription targets exists | With an OIDC token, `/internal/country-requested` → 200 and `/internal/country-discover` → 404. The reverse was true this morning, and every discovery message was dead-lettering |
| A7 | Scheduler | `regulens-source-check` ENABLED, 06:00 Asia/Jakarta, audience = worker root URL |

## B. The pipeline, stage by stage

Each stage is exercised through the deployed path, not called directly.

| # | Check | Passes when |
|---|---|---|
| B1 | Ingestion | A rule loaded from the built-in library reaches `documents` and publishes `document.uploaded` |
| B2 | **Extraction agent** | The document reaches `extracted`; `/debug/documents/{id}` shows the ADK path ran and lists accepted vs rejected candidates |
| B3 | Guardrail | Rejected candidates carry a reason. Nothing enters `clauses` without one |
| B4 | **Reconciliation agent** | A same-jurisdiction amendment produces a supersede or a conflict, and the judge agent is visible in the worker logs for an ambiguous pair |
| B5 | Impact | A product's verdict moves, and the run records **no model call** — this stage is arithmetic on purpose |
| B6 | **Query agent** | `/query` answers with citations drawn from clauses it actually read |
| B7 | Query refusal | A country with no ingested rule returns the refusal with **0 citations**. The regression this guards against is an answer that says "no information" and cites five documents |

## C. Country discovery

| # | Check | Passes when |
|---|---|---|
| C1 | Country list | `/countries` → 249 entries, `available: true`, model `gemma-4-31b-it` |
| C2 | End to end | A discovery job for SG reaches `done`/`partial` — **not stuck in `queued`**, which is what the route mismatch produced |
| C3 | What it commits | A `listing` source with a derived `link_pattern`, plus the market row, both readable through the API |
| C4 | Honest failure | A regulator that refuses automated reads is reported with its reason, not as an empty success |
| C5 | Idempotency | Pressing Discover twice joins the running job; a second run after completion adds no duplicate source |
| C6 | Fetching from Cloud Run | The regulator site answers the datacentre, not just a laptop — the trap EUR-Lex set for this codebase once already |

## D. Monitoring

| # | Check | Passes when |
|---|---|---|
| D1 | The sweep runs | `/internal/check-sources` with an OIDC token returns per-source results |
| D2 | A broken source says so | Any source that cannot be read carries its error, and the UI renders it |

## E. Interface

| # | Check | Passes when |
|---|---|---|
| E1 | The console loads | The deployed web service renders `/sources` against the deployed API |
| E2 | The panel works in a browser | Typeahead → Discover → live progress → committed and rejected rows, each with its reason |

## F. Data integrity — the one with a real hazard

| # | Check | Passes when |
|---|---|---|
| F1 | Vector space is uniform | Every stored clause is embedded by the **same** backend the app now uses |

This is not routine. `gemini-api-key` was a placeholder, which forced Vertex; it
now holds a real key. Vertex returns 768 numbers from
`text-multilingual-embedding-002` and the Developer API returns 768 from
`gemini-embedding-001`, so `find_similar`'s "length mismatch scores -1.0" guard
**never fires** on a split corpus. Nothing errors and nothing logs; reconciliation
simply stops recognising that two clauses concern the same substance, which is
how a superseding amendment lands as an unrelated new rule.

If A4 shows the app is on the Developer API, `scripts/reembed.py` must run before
B4 means anything.

---

## Out of scope, and why

- **Load and latency.** Measured on 29 Aug; nothing in this change touches the
  hot path.
- **The Gemma bonus claim.** Already evidenced by C2 naming the model that
  answered.
- **Re-testing the reskin.** Not this change; A1 and E1 only confirm it still
  serves.

## Known costs of running this

- Discovery and ingestion mutate the real workspace: a watched source, a market
  row, documents and clauses. Listed here so nothing appears in the workspace
  later without an explanation.
- Extraction and embeddings now draw on the free tier's per-minute limits, so a
  `RESOURCE_EXHAUSTED` during this run is a rate limit, not a defect — it is
  retried, not reported as a failure.
