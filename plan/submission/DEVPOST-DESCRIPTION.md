# Devpost submission text — ReguLens

Draft for the Devpost form. Every number here is checkable in the repo or on the
deployed stack; the provenance note under each section says where. Delete the
notes before pasting.

**Track:** Collaborative Partner · also entering Best Architectural Design and
Individual/Hobbyist.

**Tagline (one line, ~110 chars):**

> Finds the regulation nobody sent you, reads it, and tells you which product it
> just made illegal.

---

## Inspiration

Sell a drink powder into Germany and Indonesia and you are obeying two additive
rulebooks that disagree with each other, and neither of them emails you when a number
moves. The existing answer is a consultant reading gazettes, or a compliance officer
with a spreadsheet and a calendar reminder. Both are people doing lookup work, and
both find out late.

We wanted the opposite failure mode: a system that notices before anyone thinks to
look, and that refuses to guess when it cannot tell. The test we set ourselves was not
"can it answer a question" — it was **can a verdict change while nobody is watching,
and can the system prove that is what happened.**

## What it does

ReguLens keeps a structured model of a physical product — ingredients with real
amounts, packaging, origin, target markets — and keeps an opinion about it in every
market at once.

**The chain that matters runs end to end on the deployed stack.** Commission
Regulation (EU) 2023/2108 was published at the EU Publications Office. Nobody uploaded
it. The 06:00 sweep found it at CELLAR, read it into **88 verbatim numeric limits**,
reconciled them against the rules already held — and moved *Traditional Cured Beef
Sausage* from "needs a look" to **breaks a rule** in Germany, against the nitrite row
that entered into force on 9 October 2025:

```
Your product has  120 mg/kg      Allowed up to  30 mg/kg
From COMMISSION REGULATION (EU) 2023/2108 · E 249-250 Nitrites,
"only traditionally cured products", Period of application: from 9 October 2025
```

The alert says the one thing that separates a monitor from a checker: **nobody
uploaded this.** `GET /stats/autonomy` counts the claim from stored records rather
than asserting it — regulations found unprompted, clauses read out of them, verdicts
moved. A quiet week reports zeros.

- **It finds regulations nobody uploaded.** A daily Cloud Scheduler sweep re-reads
  four regulator addresses: the EU Publications Office SPARQL catalogue, one specific
  EU act, the Commission's food-safety RSS feed, and BPOM's legal portal index. Three
  of the four *discover* — they surface acts at addresses the system has never seen.
- **It finds the addresses too.** `POST /countries/discover` takes a country nobody
  seeded and produces a watched index page. **Gemma** is asked only for the two things
  a model gets right — the regulator's name and its root domain — and every path is
  read off pages actually fetched: we fetch the root, hand the model its real link
  inventory, and a pick that is not in that inventory is dropped. Measured over six
  countries on 31 Aug: regulator names 6/6, root domains 6/6, and **every
  model-written path wrong, 0 of 14**. That measurement is why the model is never
  asked for one.
- **It extracts rules, not summaries.** Clauses come out verbatim with a substance, a
  limit, a unit, a jurisdiction, an effective date and a citation, each carrying a
  computed confidence score.
- **It refuses to compare things that should not be compared.** A deterministic
  guardrail — ordinary typed code, no model — decides whether two clauses are even
  comparable: same substance family, same unit basis, same food. It reads the GSFA
  category code BPOM prints at the head of a row, and, where an EU annex prints no
  code, the scope the row states in words (*"only dry cured bacon"*, *"except
  sterilised meat products"*). Ambiguous or low-authority pairs go to a human review
  queue instead of quietly moving a limit.
- **It changes its mind without being asked**, and names the rule it changed its mind
  on — the strictest one in force that the product actually fails, not whichever
  clause happened to trigger the run.
- **A queue only a human can empty is a queue nobody empties.** `POST /clauses/recheck`
  re-decides the backlog through the ordinary reconciliation path, but only where
  typed code has genuinely gained something: a food category it can now read, or a
  substance name the dictionary has since learned. Low confidence and low authority
  stay a person's job forever.

> Provenance: the flip above is `GET /products/{id}/compliance` on the live stack and
> the top row of `GET /alerts`; the counts are `GET /stats/autonomy`. Limits and
> divergences are documented in `data/regulations/SOURCES.md`.

## How we built it

One container image, four Cloud Run services, and everything slow behind Pub/Sub.
The API hashes, stores, publishes and returns 202.

```
A. a person uploads a PDF or pastes text
B. Cloud Scheduler (06:00 daily) re-reads every watched address
     nothing changed  → conditional GET + text hash. No model call, no cost.
     something changed → create_document — the SAME call an upload makes

              both paths publish → Pub/Sub: document.uploaded   (push, OIDC)
  /internal/document-uploaded → extract (ADK Extraction Agent ×2) → clause.extracted
  /internal/clause-extracted  → reconcile (guardrail first; agent only if ambiguous)
  /internal/graph-changed     → impact — pure arithmetic, no model — → verdict + audit event
  /internal/dead-letter       ← any topic after max delivery attempts
```

There is no third way into the graph. A regulation the scheduler discovers is hashed,
stored, extracted, guardrailed and reviewed exactly as an upload is. Country discovery
does not touch this pipeline at all: it produces a watched *address*, which path B
then reads like every other.

Three rules held the build together:

1. **Deterministic code owns every mutation.** A model response never reaches
   Firestore without passing a Pydantic validator and the guardrail. Agents propose;
   typed code decides.
2. **The engine does not know it is a web app.** `api/app/core/` imports neither
   FastAPI nor ADK — one grep proves it. The ADK agents only *register* tools; every
   tool body is a plain function that imports and tests without an agent framework or
   a web server.
3. **Honest labels on the agents.** Reconciliation is guardrail-gated and reaches its
   judge call only for a same-jurisdiction pair whose dates cannot settle it.
   Extraction is a fixed pipeline with one LLM step, sampled twice for
   self-consistency. Impact contains **no model call at all** — comparing 120 to 30 is
   arithmetic, and a model there would be strictly worse.

Confidence is computed, not self-reported:
`0.3·parse_quality + 0.4·self_consistency + 0.3·authority_tier`. Low-authority sources
are capped by construction and routed to review.

Every state change writes an immutable `graph_events` record in the same Firestore
batch as the change itself. There is no raw update method to reach around it.

## Technologies

| Layer | Choice |
|---|---|
| Models | **Gemini 3.5 Flash** + embeddings, via **Vertex AI** or the Gemini Developer API; **Gemma** (`gemma-4-31b-it`) for country discovery |
| Agent framework | **Google ADK** — Extraction, Reconciliation, Query |
| Compute | **Cloud Run** — `api`, `worker`, `web`, plus a `seed` Job, one image |
| Events | **Pub/Sub** push subscriptions, OIDC-authenticated, dead-lettered |
| Data | **Firestore** (native) + **Cloud Storage** |
| Scheduling | **Cloud Scheduler** → worker, daily 06:00 Asia/Jakarta |
| CI/CD | **Cloud Build** → **Artifact Registry** → Cloud Run, SHA-pinned rollback |
| Secrets | **Secret Manager**, mounted via `--set-secrets` |
| API | Python 3.12, FastAPI, Pydantic |
| Web | Next.js 16 (App Router), React 19, TypeScript, Tailwind 4 |

## Data sources

Real, citable documents. Nothing synthetic, and every file has a text layer verified
with `pdftotext`. Checksums and provenance are in `data/regulations/SOURCES.md`.

- **Commission Regulation (EU) 2023/2108**, amending Annex II as regards nitrites
  (E 249-250) and nitrates (E 251-252) — CELEX `32023R2108`. **Found and ingested by
  the scheduled sweep, not by us**, and the source of the verdict above.
- **Regulation (EC) No 1333/2008** on food additives — CELEX `32008R1333`, plus the
  consolidated versions in force 18 Feb 2026 and 18 Aug 2026 (CELEX
  `02008R1333-20260218` / `02008R1333-20260818`). One day apart in force and genuinely
  different, which gives a real before/after pair instead of an invented diff.
- **Commission Regulation (EU) No 1129/2011** — the Annex II Union list, where the
  E 210–213 benzoates limit of 150 mg/kg for category 14.1.4 "flavoured drinks" lives.
  CELEX `32011R1129`.
- **Peraturan Badan POM No. 11 Tahun 2019** *tentang Bahan Tambahan Pangan* — 1,156
  pages from JDIH BPOM, the Indonesian regulator's own legal portal. Natrium benzoat,
  INS 211, 400 mg/kg in category 14.1.4.1.

Watched addresses: the EU Publications Office **CELLAR** SPARQL endpoint, an EUR-Lex
act, the Commission's food-safety feed, and BPOM's JDIH index page.

`scripts/build_library.py` slices the corpus into 28 verbatim excerpts (12 EU food
categories, 16 BPOM additive sections), each carrying its citation — the bundled
rulebook a user can load without hunting for a regulation. The excerpts are cut, never
rewritten.

## Challenges we ran into

- **`verdicts_changed: 0`, and it was the honest number.** For two days the scheduler
  found regulations, read them, and stored 123 clauses that could never bind anything.
  Five things sat in the last inch of the pipeline, and every one of them was found by
  *simulating* the fix against the live queue before running it. A substance name the
  dictionary learned two days after that regulation was read. One refusal recorded
  twice under two names, so a clause scoring 1.0 on every confidence component looked
  like a clause nobody trusted. An EU annex that prints no category code, which would
  have sent 24 nitrite rows to the model in pairs — 96 judge calls — until the
  guardrail learned to read the scope the row states in words. An amendment written as
  two rows, `until 9 October 2025` and `from 9 October 2025`, where only the second is
  an effective date, so 16 supersedes the rows answer themselves were going to a model.
  And a purity ceiling from a specifications table — *"Nitrites, not more than
  20 mg/kg expressed as KNO2"* — which names no food and, at 20 mg/kg, would have been
  the strictest nitrite limit in the graph and failed every cured meat in it.
  Afterwards: the queue fell from 200 to 141 with every remaining reason named, 58 rows
  were released, 16 amendments were settled by the dates the regulator printed, and the
  judge was not called once.
- **A change is a change of wording, not of bytes.** EUR-Lex stamps a fresh session id
  into every response, so a byte hash reported a change every night — and would have
  billed a model run for it nightly, forever. The signal is a hash of the *extracted
  text*, with a conditional GET short-circuiting ahead of it wherever a server sends
  validators.
- **What works from a laptop is not evidence it works from Cloud Run.** The EUR-Lex
  HTML URL was verified locally three times. Deployed, it answered our datacentre
  address with `202` and a challenge page. The EU source now points at CELLAR, which
  serves the same 48,417 characters and sends an `ETag`. Content negotiation matters
  too: without an explicit `Accept` header you get RDF *about* the regulation, which
  reaches extraction and fails there.
- **A model cannot tell you a URL that exists.** Six countries, 14 model-written paths,
  0 that resolved — while the regulator names and root domains were 6 for 6. The
  architecture of country discovery is that measurement: the model is asked for what it
  knows and never for a path, and it selects from a link inventory we fetched rather
  than producing links.
- **Own your HTTP transport.** `google-genai`'s `BaseApiClient` closes the httpx client
  it created when the owning object is collected. Our direct-extraction fallback kept
  dying on a transport a finished ADK runner had already shut, and a document with a
  working path left was recorded `failed`. Seen in production three times before we
  handed both clients a transport the process owns.

## Accomplishments we're proud of

- **The verdict moves with nobody watching, and the count is a query.** Not a metric we
  increment — `GET /stats/autonomy` reads the same `graph_events` the timeline renders,
  so the number and the audit trail cannot disagree.
- **601 tests**, and `make test-all` runs lint, unit tests, a type check, a production
  web build and a full local emulator drill from a clean checkout — no Google Cloud
  account, no API key, no cost. `FAKE_LLM=1` exercises the real pipeline with the model
  stubbed out.
- **Idempotency proven, not assumed.** Extract, reconcile and impact were each
  redelivery-tested against the deployed stack; a concurrency probe caught and closed a
  double-write race we would otherwise have shipped.
- **Every limitation is written down** in the README, including the one we found last:
  the query agent refused questions phrased around a market while holding the clause
  the product page cites — retrieval never asked the graph for the jurisdiction the
  question had just named.

## What we learned

The interesting decisions were all about *what not to let the model do*. A language
model is excellent at pulling a verbatim clause out of 177 pages of annex, and it is
the wrong tool for deciding whether 120 exceeds 30. Once we drew that line, the
architecture mostly fell out of it: agents propose, typed code decides, every mutation
carries its own audit event in the same write.

The second lesson took longer. **A pipeline that works stage by stage is not a pipeline
that works.** Every stage of ours was tested and green while the thing the product
exists to do had never once happened end to end — and the metric that said so,
`verdicts_changed: 0`, was sitting on the dashboard the whole time. Four defects were
only findable *after* a verdict finally moved: an event that never recorded which
document caused it, a requirement that outlived the rule it came from, an alert that
named the clause which triggered the run instead of the one the verdict rested on.

The third: a filter that hides something has to say how much and why. The review queue
states its held-back count. A source that cannot be read renders its error rather than
disappearing. Silence is exactly what turns a monitoring claim into a lie — and for a
compliance product, that is the whole product.

## What's next

- OCR, so a scanned gazette is ingestible.
- Non-numeric clauses — labelling, certification, documentation — currently extracted
  and surfaced as `needs_review` but never auto-evaluated.
- Multi-workspace and auth. The `/internal/*` routes are already OIDC-gated; user
  identity is the missing half.

## Try it

```bash
git clone https://github.com/aliefauzan/ReguLens.git
cd ReguLens
make run          # full stack on emulators. No GCP account, no key, no cost.
```

Open <http://localhost:3000>, press **Try it with sample data**, then **Add rules →
Rules we already have** and feed it the EU limit. The verdict flips on its own.

## Built with

`google-cloud-run` `google-cloud-firestore` `google-cloud-pubsub` `google-cloud-storage`
`google-cloud-scheduler` `google-cloud-build` `secret-manager` `artifact-registry`
`vertex-ai` `gemini` `gemma` `google-adk` `python` `fastapi` `pydantic` `nextjs`
`react` `typescript` `tailwindcss` `docker`
