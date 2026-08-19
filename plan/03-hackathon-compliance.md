# Hackathon Requirements — Traceability

Source: `https://allthingsagentichackathon.devpost.com`, read 19 Aug 2026.
**Re-read the official rules before submitting.** This is a working summary, not
the authoritative text, and the rules page can change.

**Deadline: 31 Aug 2026, 5:00pm PDT** — that is 1 Sep, ~07:00 WITA.
**Track: Collaborative Partner** ($20k), also eligible for Best Architectural
Design and Individual/Hobbyist.

**Tick every box in this file before submitting.** Phase 7 exit criteria require it.

## Mandatory technical requirements

| Requirement | How ReguLens satisfies it | Where built | Status |
|---|---|---|---|
| Gemini **3.5 or newer**, via Gemini API or Vertex AI | Extraction, reconciliation judge, query synthesis — all Vertex AI | Phases 2, 3, 5 | `[ ]` |
| At least one Google agent framework (ADK / GenAI SDK / Antigravity SDK / GenKit) | **Google ADK** — root agent + Extraction, Reconciliation, Impact, Query agents | Phases 2–5 | `[ ]` |
| At least one Google Cloud infrastructure service | Cloud Run (×2 services + Job), Firestore, Pub/Sub, Cloud Storage — four of them | Phase 0 onward | `[ ]` |
| Must "operate beyond standard chat loops" — autonomous action, not conversational response only | The phase-4 unprompted status flip: a document arrives, the graph mutates, the product is re-evaluated, and the user is alerted **with no question asked** | Phase 4 | `[ ]` |

The autonomy requirement is the one most projects fail on. Ours is satisfiable in
one sentence — *nobody queried it* — and the demo is built around making that
visible. Protect phase 4.

## Optional bonus

| Bonus | Plan | Priority |
|---|---|---|
| Gemma integration | Long-document section pre-filter before Gemini extraction; measure and report tokens saved | **Cut first if behind.** Nothing depends on it |
| Veo / Lyria | Not applicable to this product | Skipped |
| Published blog post or social post | Write-up of the "deterministic code gates the model" principle | Nice-to-have, ~1 hour, do it while renders/builds run |

## Submission deliverables

| ✓ | Deliverable | Notes | Owner phase |
|---|---|---|---|
| `[ ]` | Hosted project URL | Vercel frontend + Cloud Run backend. Live from phase 0, not assembled at the end | Phase 0, verified Phase 7 |
| `[ ]` | Public/private code repo (GitHub) | Push from day one; commit history is itself evidence of process | Phase 0 |
| `[ ]` | **Reproducible spin-up instructions in README** | Explicitly required. Prerequisites, env vars, `gcloud` setup, one command to run locally, one to deploy | Phase 7 |
| `[ ]` | **Architecture diagram** | Required. Render the topology from `01-architecture.md` as an image; do not submit ASCII | Phase 7 |
| `[ ]` | **~4-minute demo video proving the backend runs on Google Cloud** | Not just the UI: show the Cloud Run services, the Pub/Sub subscription delivering, and Firestore documents changing. Budget ~40s of the 4 minutes for this proof | Phase 7 |
| `[ ]` | Text description: features, technologies, data sources, learnings | "Data sources" means naming the actual regulations used — use real, citable documents so this section is answerable | Phase 7 |
| `[ ]` | Optional: blog/video/social post | Bonus content | Phase 7 if time |

The video requirement changes the demo script: `99-demo-script.md` is a 3m30s beat
sheet, compressed to ~3m10s to leave room for the Google Cloud proof segment.
Capture the raw footage in phase 6 while the E2E runs are green; edit in phase 7.

## Judging criteria → where the points come from

| Criterion | Weight | Carried by |
|---|---|---|
| Innovation & Operational Utility | **40%** | Unprompted impact propagation (phase 4); cross-jurisdiction conflict detection (phase 3); regulator-readable audit trail (phase 5A). This is the largest single weight and it maps to phases 3–5 — do not trade them for polish |
| Architectural Discipline & Tech Stack | **30%** | Guardrail gates the model; per-stage Pub/Sub retry + DLQ; computed rather than self-reported confidence; the explicit "not building" table; honest labelling of which agents actually reason |
| Demo & Production Readiness | **30%** | Cloud Build CI/CD with SHA-pinned rollback; Secret Manager; the observability stack in `04-observability.md`; the phase-6 E2E suite covering every use case; phase 7's seed/reset Job, failure states, deployed URL, recorded fallback, README, diagram |

Note the split: 40% is product substance, 60% is architecture and execution
quality. A smaller system that is disciplined and demos flawlessly beats a larger
one that is neither. This is the justification for every cut in
`01-architecture.md`.

## Eligibility check — do this now, not on 31 Aug

- [ ] Confirm Indonesia is not on the excluded countries/territories list in the
      official rules. **Blocking if it is** — verify before spending another day.
- [ ] Confirm age-of-majority requirement.
- [ ] Confirm individual vs. team entry rules and whether the Individual/Hobbyist
      prize category applies.
- [ ] Register on Devpost and join the hackathon before the deadline (registration
      and submission can have different cut-offs — check).

## Rules-risk notes

- "Gemini 3.5 or newer" — verify the exact model identifier available to your
  project in Vertex AI at phase 0 and pin it. Do not assume a model string.
- Deployment "doesn't need to be live at submission", but a live URL is heavily
  encouraged and directly serves the Production Readiness weight. Keep it live.
- The repo may be private, but if private, confirm how judges are granted access.
