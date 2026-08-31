# Devpost submission text — ReguLens

Draft for the Devpost form. Every number here is checkable in the repo; the
provenance note under each section says where. Delete the notes before pasting.

**Track:** Collaborative Partner · also entering Best Architectural Design and
Individual/Hobbyist.

**Tagline (one line, ~110 chars):**

> Watches regulators publish, reads the rules itself, and tells an exporter which
> product just stopped being compliant.

---

## Inspiration

Sell a drink powder into Germany and Indonesia and you are obeying two additive
rulebooks that disagree with each other. The EU caps benzoates in flavoured drinks
at 150 mg/kg. Indonesia's BPOM allows 400 mg/kg in the equivalent category. A
formulation at 300 mg/kg is perfectly legal in one market and illegal in the other,
and nobody emails you when either number moves.

The existing answer is a consultant reading gazettes, or a compliance officer with a
spreadsheet and a calendar reminder. Both are people doing lookup work, and both find
out late. We wanted the opposite failure mode: a system that notices before anyone
thinks to look, and that refuses to guess when it cannot tell.

## What it does

ReguLens keeps a structured model of a physical product — ingredients with real
amounts, packaging, origin, target markets — and keeps an opinion about it in every
market at once.

- **It finds regulations nobody uploaded.** A daily Cloud Scheduler sweep re-reads
  four regulator addresses: the EU Publications Office SPARQL catalogue, one specific
  EU act, the Commission's food-safety RSS feed, and BPOM's legal portal index. Three
  of the four *discover* — they surface acts at addresses the system has never seen.
- **It extracts rules, not summaries.** Clauses come out verbatim with a substance, a
  limit, a unit, a jurisdiction, an effective date and a citation, each carrying a
  computed confidence score.
- **It refuses to compare things that should not be compared.** A deterministic
  guardrail — ordinary typed code, no model — decides whether two clauses are even
  comparable, reading the food category the regulator prints at the head of every row.
  Ambiguous or low-authority pairs go to a human review queue instead of quietly
  moving a limit.
- **It changes its mind without being asked.** When a rule lands, affected products
  flip status and an alert names the regulation that caused it — and says whether a
  person uploaded that regulation or the scheduler found it.
- **It answers with citations you can check.** Every clause id in an answer is
  validated in code against what retrieval actually served. An invented id cites
  nothing and is rejected before it reaches a screen.

The demo is one product, two markets, one change. *Herbal Drink Powder*, sodium
benzoate 300 mg/kg. Against BPOM's 400 mg/kg it reads compliant. The moment the EU
Annex II rule at 150 mg/kg enters the graph, Germany flips to non-compliant on its
own — no question asked, no page refreshed by a human first.

> Provenance: limits and the divergence are documented in
> `data/regulations/SOURCES.md`; the demo baseline is `api/app/core/samples.py`.

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
stored, extracted, guardrailed and reviewed exactly as an upload is.

Three rules held the build together:

1. **Deterministic code owns every mutation.** A model response never reaches
   Firestore without passing a Pydantic validator and the guardrail. Agents propose;
   typed code decides.
2. **The engine does not know it is a web app.** `api/app/core/` imports neither
   FastAPI nor ADK — one grep proves it. The four ADK agents only *register* tools;
   every tool body is a plain function that imports and tests without an agent
   framework or a web server.
3. **Honest labels on the agents.** Query is genuinely agentic and picks its own
   retrieval tools. Reconciliation is guardrail-gated with one judge call.
   Extraction is a fixed pipeline with one LLM step. Impact contains **no model call
   at all** — comparing 300 to 150 is arithmetic, and a model there would be strictly
   worse.

Confidence is computed, not self-reported:
`0.3·parse_quality + 0.4·self_consistency + 0.3·authority_tier`. Low-authority
sources are capped by construction and routed to review.

Every state change writes an immutable `graph_events` record in the same Firestore
batch as the change itself. There is no raw update method to reach around it.

## Technologies

| Layer | Choice |
|---|---|
| Models | **Gemini 3.5 Flash** + embeddings, via **Vertex AI** or the Gemini Developer API |
| Agent framework | **Google ADK** — Extraction, Reconciliation, Query, Impact |
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

- **Regulation (EC) No 1333/2008** on food additives — CELEX `32008R1333`, plus the
  consolidated versions in force 18 Feb 2026 and 18 Aug 2026 (CELEX
  `02008R1333-20260218` / `02008R1333-20260818`). One day apart in force and
  genuinely different, which gives a real before/after pair instead of an invented diff.
- **Commission Regulation (EU) No 1129/2011** — the Annex II Union list, where the
  E 210–213 benzoates limit of 150 mg/kg for category 14.1.4 "flavoured drinks" lives.
  CELEX `32011R1129`.
- **Peraturan Badan POM No. 11 Tahun 2019** *tentang Bahan Tambahan Pangan* — 1,156
  pages from JDIH BPOM, the Indonesian regulator's own legal portal. Natrium benzoat,
  INS 211, 400 mg/kg in category 14.1.4.1.
- **Commission Regulation (EU) 2023/2108** — ingested live by the scheduled sweep
  during testing; 68 clauses came out of it.

Watched addresses: the EU Publications Office **CELLAR** SPARQL endpoint, an EUR-Lex
act, the Commission's food-safety feed, and BPOM's JDIH index page.

`scripts/build_library.py` slices the corpus into 28 verbatim excerpts (12 EU food
categories, 16 BPOM additive sections), each carrying its citation — the bundled
rulebook a user can load without hunting for a regulation. The excerpts are cut,
never rewritten.

## Challenges we ran into

Four cost real debugging sessions and each one changed the design.

- **A change is a change of wording, not of bytes.** EUR-Lex stamps a fresh session
  id into every response, so a byte hash reported a change every night — and would
  have billed a model run for it nightly, forever. The signal is a hash of the
  *extracted text*, with a conditional GET short-circuiting ahead of it wherever a
  server sends validators.
- **What works from a laptop is not evidence it works from Cloud Run.** The EUR-Lex
  HTML URL was verified locally three times. Deployed, it answered our datacentre
  address with `202` and a challenge page, and the first scheduled sweep recorded an
  error. The EU source now points at CELLAR, which serves the same 48,417 characters
  and sends an `ETag`. Content negotiation matters too: without an explicit `Accept`
  header you get RDF *about* the regulation, which reaches extraction and fails there.
- **Own your HTTP transport.** `google-genai`'s `BaseApiClient` closes the httpx
  client it created when the owning object is collected. Our direct-extraction
  fallback kept dying on a transport that a finished ADK runner had already shut, and
  a document with a working path left was recorded `failed`. Seen in production three
  times before we handed both clients a transport the process owns.
- **A queue that only a human can empty is a queue nobody empties.** Thirty-six BPOM
  rows sat waiting for a person to confirm a regulation does not contradict itself —
  which is not a judgement call, it is a missing field. The fix was not a bulk-accept
  button (a person clicking through 36 decisions they cannot check); it was teaching
  the guardrail to read the food category the regulator already prints. Only
  `judge_ambiguous` rows are ever reopened. Low confidence and low authority stay a
  person's job forever.

## Accomplishments we're proud of

- **The verdict moves with nobody watching.** That is the hackathon's "beyond
  standard chat loops" requirement, and it is satisfiable in one sentence: *nobody
  queried it.* `GET /stats/autonomy` counts the claim from stored records rather than
  asserting it.
- **393 tests**, and `make test-all` runs lint, unit tests, a type check, a
  production web build and a full local emulator drill from a clean checkout — no
  Google Cloud account, no API key, no cost. `FAKE_LLM=1` exercises the real pipeline
  with the model stubbed out.
- **Idempotency proven, not assumed.** Extract, reconcile and impact were each
  redelivery-tested against the deployed stack; a concurrency probe caught and closed
  a double-write race we would otherwise have shipped.
- **The limitations list is written down.** No OCR. Numeric limits only. Sources
  registered by hand. One workspace, no auth. It is in the README so nobody discovers
  it during a demo.

## What we learned

The interesting decisions were all about *what not to let the model do*. A language
model is excellent at pulling a verbatim clause out of 177 pages of annex, and it is
the wrong tool for deciding whether 300 exceeds 150. Once we drew that line, the
architecture mostly fell out of it: agents propose, typed code decides, and every
mutation carries its own audit event in the same write.

The second lesson is that a filter which hides something has to say how much and why.
The review queue states its held-back count. A source that cannot be read renders its
error rather than disappearing. Silence is exactly what turns a monitoring claim into
a lie — and for a compliance product, that is the whole product.

## What's next

- OCR, so a scanned gazette is ingestible.
- Non-numeric clauses — labelling, certification, documentation — currently extracted
  and surfaced as `needs_review` but never auto-evaluated.
- Source discovery: something that works out on its own which page a regulator
  publishes on, instead of a human registering the address.
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
`vertex-ai` `gemini` `google-adk` `python` `fastapi` `pydantic` `nextjs` `react`
`typescript` `tailwindcss` `docker`
