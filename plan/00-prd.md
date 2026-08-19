# ReguLens — Product Requirements (MVP)

*Requirements only. Implementation detail lives in `01-architecture.md` and `phases/`.*

**Context:** All Things Agentic Hackathon, Collaborative Partner track.
Deadline 31 Aug 2026 5:00pm PDT. Google ADK and Gemini 3.5+ are mandatory; the
project must "operate beyond standard chat loops". Full traceability in
`03-hackathon-compliance.md`.

## Problem

Small exporters must satisfy several jurisdictions at once for a single product.
The binding requirements live in scattered, differently-authoritative sources —
government PDFs, association announcements, screenshots, forwarded chat messages —
and they change. The exporter's real question is not "what does this document say"
but **"which requirement applies to my product and destination right now, and did
anything change or conflict with what I already believed?"** Getting this wrong is
expensive: a rejected shipment, a destroyed batch, or a blocked customs clearance.

Concrete instance: Indonesia/BPOM allows sodium benzoate ≤ 0.10%; the EU allows
≤ 0.05%. A product formulated at 0.08% is compliant at home and non-compliant at
its destination. Nothing in the exporter's toolchain tells them this, and nothing
tells them when the EU limit moves.

## Evidence

- **Assumption — needs validation via user interviews with 5 Indonesian SME exporters.**
  The persona (Ibu Sari, herbal drink powder, exporting to UAE and Germany, no
  in-house compliance team) is a design construct from the concept session, not an
  interviewed user.
- **Verifiable and worth citing in the demo:** the regulatory divergence itself is
  real and checkable (EU additive limits vs. BPOM limits). The demo should use a
  real, citable pair of clauses rather than invented numbers, so the *problem* is
  evidenced even while the *user demand* is still an assumption.
- **Open validation gap:** we have no data on how often the relevant regulations
  actually change, which determines whether the "monitoring" loop is valuable or
  merely impressive.

## Users

- **Primary:** owner-operator of a micro/small food or herbal export business, 1–20
  staff, no compliance officer, exporting or attempting to export to 1–3 foreign
  markets. Triggered when entering a new market, or when they hear secondhand that
  "something changed".
- **Secondary (read-only in MVP):** export consultant tracking several client
  products. Portfolio view is out of MVP scope but the data model must not
  preclude it.
- **Not for:** large enterprises with a compliance department, domestic-only
  sellers, consumers, or anyone wanting a general-purpose regulation chatbot.

## Hypothesis

We believe a **living compliance twin — a structured model of one product,
continuously reconciled against ingested regulatory clauses** — will let a small
exporter **know which requirement currently binds them and what a regulatory change
just broke**, for **SME exporters without compliance staff**.

We will know we are right when, given a product and a newly ingested regulation
that tightens a limit, the system **autonomously flips that product's status,
names the causing requirement, and cites its source clauses — with no user query
required**.

That last clause is also the hackathon's "beyond standard chat loops" requirement.
The hypothesis and the qualifying criterion are the same sentence, which is a good
sign about the concept's fit for this competition.

## Success Metrics (MVP / demo-scale)

| Metric | Target | How measured |
|---|---|---|
| *(All of the below are asserted by the phase-6 suite and measured from the metrics in `04-observability.md`, not by hand.)* | | |
| End-to-end change propagation | Upload → status flip → alert in **< 90s**, unattended | Timed run of the demo scenario |
| Extraction correctness | **≥ 8 of 10** seeded clauses extracted with correct substance + limit + unit + jurisdiction | Hand-labelled fixture set, checked in |
| False conflict rate | **0** conflicts raised between non-comparable clauses (different substance, product type, or unit) | Guardrail unit tests over adversarial fixture pairs |
| Evidence grounding | **100%** of query answers cite ≥ 1 stored clause; none answer from model world-knowledge | Assertion in the query response path + manual review of 10 questions |
| Auditability | **100%** of state transitions have a matching `graph_events` record | Integrity test over the demo run |

Note the second and third metrics matter more than a readiness percentage.
A confident wrong answer is worse than an honest `needs_review`.

## Scope

### MVP

One product, two jurisdictions (Indonesia/BPOM and EU/Germany), one substance
dimension (numeric ingredient limits), and the full loop over them:

1. Create a product with ingredients and quantities, and pick a destination market.
2. Upload a regulatory document (PDF or pasted text) with a declared source type.
3. Extract structured clauses with a composite confidence score.
4. Deterministically decide which existing clauses are comparable.
5. Reconcile: new requirement / supersedes / conflicts / needs review.
6. Mutate clause + requirement state, and append an immutable audit event.
7. Propagate to affected products and markets, producing a risk status.
8. Show readiness, a before/after timeline, and an alert.
9. Answer "why is my product at risk?" with cited clauses and confidence.

### Out of scope

| Deferred | Why |
|---|---|
| Authentication / multi-tenant | Adds a full surface for zero demo value; single hardcoded workspace |
| Managed vector search | Clause count is in the hundreds; in-process cosine over Firestore-stored embeddings is correct here |
| Non-numeric requirement evaluation (labeling, certification) | Extracted and displayed, but evaluated as `needs_review` rather than pass/fail — pretending to evaluate them would be fabrication |
| Screenshot/OCR and chat-export ingestion | Phase 2 stretch only; PDF + pasted text prove the same pipeline |
| WhatsApp/email notification delivery | In-app alert only |
| Consultant portfolio / multi-client view | Data model supports it; UI does not |
| Automated regulation crawling | User-triggered upload only; a crawler is a separate product |
| Conflict *resolution* workflow | Conflicts are raised and displayed, not adjudicated |

## Delivery Milestones

| # | Milestone | User-visible outcome | Status | Plan |
|---|---|---|---|---|
| 0 | Foundation | App loads, reads and writes real data | pending | [phase-0](phases/phase-0-foundation.md) |
| 1 | Compliance Twin | "This is my product and where I'm sending it" | pending | [phase-1](phases/phase-1-compliance-twin.md) |
| 2 | Ingestion & Extraction | "My PDF became structured, sourced clauses" | pending | [phase-2](phases/phase-2-ingestion-extraction.md) |
| 3 | Guardrail & Reconciliation | "The system noticed this contradicts what it knew" | pending | [phase-3](phases/phase-3-guardrail-reconciliation.md) |
| 4 | Impact Engine | "My product just became non-compliant for Germany" | pending | [phase-4](phases/phase-4-impact-engine.md) |
| 5 | Timeline & Query | "Here is what changed, when, and why it breaks me" | pending | [phase-5](phases/phase-5-timeline-query.md) |
| 6 | End-to-End Testing | Every use case verified green against the deployed stack | pending | [phase-6](phases/phase-6-e2e-testing.md) |
| 7 | Hardening & Submission | Reproducible demo, video, diagram, Devpost entry filed | pending | [phase-7](phases/phase-7-demo-hardening.md) |

## Open Questions

- [ ] Do real target users care about *change monitoring*, or only about *first-time
      market entry*? These imply different products; the MVP hedges by doing both,
      but a real answer should cut one.
- [ ] How often do the relevant regulations actually change? If the answer is
      "twice a year", the monitoring loop is a compliance archive, not a live feed.
- [ ] What authority tiers should exist, and who decides a source's tier? MVP has
      the uploader declare it, which is trivially gameable and fine for a demo but
      not for production.
- [ ] Is an aggregate "readiness %" honest, or does it imply coverage the system
      does not have? Consider showing counts (`3 issues`) instead of a percentage.
- [x] ~~Does the hackathon require a specific agent framework?~~ **Resolved:**
      Google ADK is required. All four agents are ADK agents; every tool body stays
      a plain Python function so the framework is a wrapper, not a dependency of the
      demo path. See `01-architecture.md` §ADK agent design.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Extraction quality on real regulatory PDFs is poor (tables, multi-column, legalese) | High | High | Phase 2 pins a small fixture set of real pages and measures against it before building anything downstream; pre-filter relevant sections before deep extraction |
| The system confidently declares a false conflict, destroying trust in the demo | Medium | High | Deterministic guardrail gates the LLM judge; low confidence routes to `needs_review`, never to `conflict` |
| Demo depends on live LLM latency and can stall on stage | Medium | High | Phase 6 seeds a pre-warmed state and a recorded fallback; extraction runs async with visible progress |
| Scope creep into agent-count theatre (many agents to look agentic) | High | Medium | Agent count is capped at four, and two of them are mostly deterministic pipelines with one LLM call |
| **13 days of work against a 13-day window** — zero float after adding CI/CD, observability, and the E2E phase | High | Critical | Cut Gemma and OCR on day one (see `README.md`) to buy ~0.75 day; submit 14 hours early |
| Pub/Sub at-least-once delivery produces duplicate clauses or duplicate alerts | Medium | High | Every handler is idempotent by state check; redelivery is tested explicitly in phases 2, 3, and 4 |
| Parallel per-clause reconciliation races on a shared existing clause | Medium | High | Firestore transactions around every clause mutation (phase 3); fallback is a per-document lock |
| ADK behaves differently on Cloud Run than locally, late in the build | Medium | High | ADK proven on deployed Cloud Run in phase 0; all tool bodies callable without ADK |
| Ineligible to enter (country exclusion) | Low | Critical | Verified before any further work — see `03-hackathon-compliance.md` |
| Vertex AI quota / billing limits hit mid-demo | Low | High | Phase 0 verifies quota and sets a budget alert; cache extraction results by document hash |
| Using invented regulation numbers gets called out by judges | Medium | Medium | Use real, citable clause text in the demo fixtures; label any synthetic document as synthetic in the UI |

---
*Status: DRAFT — requirements approved for build. Implementation detail deliberately excluded; see phase plans.*
