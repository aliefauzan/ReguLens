# Devpost form — the three fields, ready to paste

Track: Collaborative Partner · All Things Agentic Hackathon.
Every number is checkable in the repo or on the deployed stack.

---

## 1 · Elevator pitch (tagline)

**Primary:**

> Finds the food-safety regulation nobody sent you, reads it, and tells you which
> of your products it just made illegal — before anyone thinks to look.

**Shorter alternates:**

- ReguLens watches the regulators, reads new and amended rules into a knowledge
  graph, and flips a product's compliance verdict the moment a limit moves.
- Autonomous regulatory monitoring for food & beverage exporters: it notices the
  change, re-checks every product, and refuses to guess when it can't tell.

---

## 2 · About the project

### Inspiration

Sell a drink powder into Germany and Indonesia and you are obeying two additive
rulebooks that disagree with each other, and neither of them emails you when a
number moves. The EU caps benzoates in flavoured drinks at $150\ \mathrm{mg/kg}$;
Indonesia's BPOM allows $400\text{–}900\ \mathrm{mg/kg}$ for the same category.
The current answer is a consultant reading gazettes or a compliance officer with a
spreadsheet and a calendar reminder — people doing lookup work, and finding out
late.

We wanted the opposite failure mode: a system that notices *before* anyone thinks
to look, and that refuses to guess when it cannot tell. The bar we set was not
"can it answer a question" — it was **can a verdict change while nobody is
watching, and can the system prove that is what happened.**

### What it does

ReguLens keeps a structured model of a physical product — ingredients with real
amounts, packaging, origin, target markets — and holds an opinion about it in
every market at once.

The chain that matters runs end to end on the deployed stack. Commission
Regulation (EU) 2023/2108 was published at the EU Publications Office. Nobody
uploaded it. The 06:00 sweep found it at CELLAR, read it into **88 verbatim
numeric limits**, reconciled them against the rules already held — and moved
*Traditional Cured Beef Sausage* from "needs a look" to **breaks a rule** in
Germany, against the nitrite row that entered into force on 9 October 2025:

```
Your product has  120 mg/kg      Allowed up to  30 mg/kg
From COMMISSION REGULATION (EU) 2023/2108 · E 249-250 Nitrites,
"only traditionally cured products", Period of application: from 9 October 2025
```

The alert says the one thing that separates a monitor from a checker: **nobody
uploaded this.** `GET /stats/autonomy` counts that claim from stored records
rather than asserting it — regulations found unprompted, clauses read out of
them, verdicts moved. A quiet week reports zeros.

- **Finds regulations nobody uploaded.** A daily Cloud Scheduler sweep re-reads
  four regulator addresses — the EU Publications Office SPARQL catalogue, one
  specific EU act, the Commission's food-safety RSS feed, and BPOM's legal
  portal. Three of the four *discover*: they surface acts at addresses the system
  has never seen.
- **Finds the addresses too.** `POST /countries/discover` takes a country nobody
  seeded and produces a watched index page. **Gemma** is asked only for the two
  things a model gets right — the regulator's name and its root domain — and every
  path is read off pages actually fetched. Measured over six countries: regulator
  names 6/6, root domains 6/6, and **every model-written path wrong, 0 of 14** —
  which is why the model is never asked for one.
- **Extracts rules, not summaries.** Clauses come out verbatim with a substance,
  a limit, a unit, a jurisdiction, an effective date and a citation, each carrying
  a computed confidence score.
- **Refuses to compare things that should not be compared.** A deterministic
  guardrail — plain typed code, no model — decides whether two clauses are even
  comparable, and routes anything ambiguous or low-authority to a human review
  queue instead of quietly moving a limit.
- **Changes its mind without being asked**, and names the strictest rule in force
  the product actually fails — not whichever clause happened to trigger the run.

### How we built it

One container image, four Cloud Run services, and everything slow behind Pub/Sub.
The API hashes, stores, publishes, and returns `202`.

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

There is no third way into the graph. A regulation the scheduler discovers is
hashed, stored, extracted, guardrailed and reviewed exactly as an upload is.

Three rules held the build together:

1. **Deterministic code owns every mutation.** A model response never reaches
   Firestore without passing a Pydantic validator and the guardrail. Agents
   propose; typed code decides.
2. **The engine does not know it is a web app.** `api/app/core/` imports neither
   FastAPI nor ADK — one grep proves it. The ADK agents only *register* tools;
   every tool body is a plain function that imports and tests without an agent
   framework or a web server.
3. **Honest labels on the agents.** The Query agent is genuinely agentic — it
   picks its own retrieval tools. Impact contains **no model call at all**:
   comparing $120$ to $30$ is arithmetic, and a model there would be strictly
   worse.

Confidence is computed, not self-reported:

$$\text{confidence} = 0.3 \cdot \text{parse\_quality} + 0.4 \cdot \text{self\_consistency} + 0.3 \cdot \text{authority\_tier}$$

Low-authority sources are capped by construction and routed to review. Every
state change writes an immutable `graph_events` record in the same Firestore
batch as the change itself — there is no raw update method to reach around it.

### Challenges we ran into

- **`verdicts_changed: 0`, and it was the honest number.** For two days the
  scheduler found regulations, read them, and stored clauses that could never
  bind anything. Five things sat in the last inch of the pipeline — a substance
  name the dictionary learned two days too late, one refusal recorded twice under
  two names, an EU annex that prints no category code, an amendment written as two
  undated-looking rows, and a purity ceiling that names no food but would have
  been the strictest nitrite limit in the graph. Each was found by *simulating*
  the fix against the live queue before running it.
- **A change is a change of wording, not of bytes.** EUR-Lex stamps a fresh
  session id into every response, so a byte hash reported a change every night —
  and would have billed a model run for it nightly, forever. The signal is a hash
  of the *extracted text*.
- **What works from a laptop is not evidence it works from Cloud Run.** The
  EUR-Lex HTML URL was verified locally three times. Deployed, it answered our
  datacentre address with `202` and a challenge page. The EU source now points at
  CELLAR, which serves the same regulation and sends an `ETag`.
- **A model cannot tell you a URL that exists.** Six countries, 14 model-written
  paths, 0 that resolved — while regulator names and root domains were 6 for 6.
  The whole architecture of country discovery is that measurement.
- **Own your HTTP transport.** `google-genai`'s `BaseApiClient` closes the httpx
  client it created when the owning object is collected. Our direct-extraction
  fallback kept dying on a transport a finished ADK runner had already shut, and a
  document with a working path left was recorded `failed` — three times in
  production before we handed both clients a transport the process owns.

### Accomplishments we're proud of

- The verdict moves with nobody watching, and the count is a **query** over the
  same `graph_events` the timeline renders — the number and the audit trail
  cannot disagree.
- **618 tests**, and `make test-all` runs lint, unit tests, a type check, a
  production web build and a full local emulator drill from a clean checkout — no
  Google Cloud account, no API key, no cost.
- Idempotency proven, not assumed: extract, reconcile and impact were each
  redelivery-tested against the deployed stack; a concurrency probe caught and
  closed a double-write race.
- Every limitation is written down in the README rather than discovered in a demo.

### What we learned

The interesting decisions were all about *what not to let the model do*. A
language model is excellent at pulling a verbatim clause out of 177 pages of
annex, and it is the wrong tool for deciding whether $120$ exceeds $30$. Once we
drew that line, the architecture fell out of it.

The second lesson took longer: **a pipeline that works stage by stage is not a
pipeline that works.** Every stage of ours was green while the thing the product
exists to do had never once happened end to end — and `verdicts_changed: 0` was
sitting on the dashboard the whole time. Four defects were only findable *after* a
verdict finally moved.

The third: a filter that hides something has to say how much and why. The review
queue states its held-back count; a source that cannot be read renders its error.
Silence is what turns a monitoring claim into a lie — and for a compliance
product, that is the whole product.

### What's next

- OCR, so a scanned gazette is ingestible.
- Auto-evaluation of non-numeric clauses (labelling, certification,
  documentation), currently extracted and surfaced as `needs_review`.
- Multi-workspace and user auth — the `/internal/*` routes are already OIDC-gated;
  user identity is the missing half.

### Data sources

Real, citable documents — nothing synthetic. Checksums and provenance in
`data/regulations/SOURCES.md`.

- **Commission Regulation (EU) 2023/2108** (CELEX `32023R2108`) — nitrites/nitrates
  amendment, found and ingested by the scheduled sweep, not by us.
- **Regulation (EC) No 1333/2008** on food additives (CELEX `32008R1333`), plus
  the consolidated versions in force 18 Feb 2026 and 18 Aug 2026.
- **Commission Regulation (EU) No 1129/2011** — the Annex II Union list (CELEX
  `32011R1129`).
- **Peraturan Badan POM No. 11 Tahun 2019** *tentang Bahan Tambahan Pangan* —
  1,156 pages from JDIH BPOM, the Indonesian regulator's own legal portal.

---

## 3 · Built with (tags — 24)

```
google-cloud-run
google-cloud-firestore
google-cloud-pubsub
google-cloud-storage
google-cloud-scheduler
google-cloud-build
secret-manager
artifact-registry
vertex-ai
gemini
gemma
google-adk
python
fastapi
pydantic
next.js
react
typescript
tailwindcss
docker
pub-sub
sparql
oidc
firestore
```
