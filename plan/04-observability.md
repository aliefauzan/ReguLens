# ReguLens — Observability & Operations

A Pub/Sub pipeline across two services fails in ways a monolith does not: a message
vanishes, a stage silently no-ops, a clause reconciles against stale state. Without
observability you debug by guessing, and there is no time in this schedule for
guessing.

Everything here is built into phase 0 and maintained per phase. None of it is
retrofitted at the end.

## Build checklist

- [ ] `trace_id` generated at upload, returned in the 202 (phase 0)
- [ ] `trace_id` on the document record, every Pub/Sub attribute, every log line,
      every `graph_event` (phase 0)
- [ ] `trace_id` surfaced and copyable in the UI (phase 2)
- [ ] Structured JSON logging helper; no `print` anywhere (phase 0)
- [ ] All named decision-point events logged (phases 2–4)
- [ ] LLM call logging: model, stage, tokens, latency, prompt hash (phase 2)
- [ ] OpenTelemetry → Cloud Trace on both services (phase 0)
- [ ] Pipeline stage spans, including parallel reconcile spans (phase 3)
- [ ] Error Reporting enabled (phase 0)
- [ ] Uptime checks on both `/health` endpoints (phase 0)
- [ ] End-to-end propagation latency metric (phase 4)
- [ ] All log-based metrics in the table below (phases 2–5)
- [ ] Five alerts configured (phase 0)
- [ ] **Each of the five alerts deliberately triggered once to prove it fires** (phase 7)
- [ ] Debug view `/debug/documents/{id}` (phase 2, extended in 3 and 4)
- [ ] Cloud Monitoring dashboard with the pipeline funnel (phase 4)

## The one thing that matters most: correlation ID

A single `trace_id` generated at upload and carried through every stage.

```
POST /documents
  → trace_id = uuid4()            returned to the client in the 202 body
  → documents.trace_id            stored on the record
  → Pub/Sub message attribute     {"trace_id": "..."} on every publish
  → every log line                {"trace_id": "..."} in structured JSON
  → every graph_event             trace_id field
  → surfaced in the UI            on the document page, copyable
```

With this, debugging is one Cloud Logging query:

```
jsonPayload.trace_id="a3f2..."
```

and you see the whole journey — API, extract, reconcile, impact — across both
services, in order. Build this in phase 0. Adding it later means touching every
handler.

## Structured logging

Cloud Logging, JSON only. Never `print`, never bare strings.

Required fields on every line:

```json
{
  "severity": "INFO",
  "trace_id": "a3f2...",
  "workspace_id": "ws_demo",
  "stage": "reconcile",
  "document_id": "doc_001",
  "clause_id": "clause_007",
  "event": "guardrail_rejected",
  "detail": {"reason": "unit_mismatch", "a": "percent_w_w", "b": "mg_per_kg"}
}
```

Log at these decision points specifically — they are the ones you will need:

| Event | Why it matters |
|---|---|
| `message_received` / `message_acked` / `message_nacked` | Distinguishes "never delivered" from "delivered and failed" |
| `idempotent_skip` | The most confusing failure mode: work that correctly did nothing |
| `extraction_candidates` | Count, plus each candidate's substance/limit/unit before validation |
| `candidate_rejected` | Which Pydantic field failed — this is how you fix prompts |
| `confidence_computed` | All three components, not just the total |
| `guardrail_rejected` | The reason enum. This is also a product feature (shown in the UI) |
| `judge_invoked` / `judge_verdict` | How often the model is actually consulted |
| `state_mutation` | Collection, entity, before, after |
| `requirement_evaluated` | Product value, limit, result |
| `status_changed` | The money event |

`severity: WARNING` for `needs_review` outcomes, `ERROR` only for genuine faults.
A low-confidence clause is not an error — if it logs as one, your error rate becomes
meaningless.

## LLM call logging

Every Vertex call logs: model id, stage, prompt token count, response token count,
latency, temperature, and a **hash** of the prompt plus the first 500 chars of the
response. Full prompts go to a `llm_calls` Firestore collection only in the dev
project, never in demo — they are large and they make debugging cheap.

This gives you, for free: cost attribution per stage, the token saving from the
Gemma pre-filter if you build it, and the ability to answer "why did it extract
that?" without re-running anything.

## Tracing

OpenTelemetry → Cloud Trace. Spans:

```
document_pipeline (root, linked by trace_id)
├── extract
│   ├── text_extraction
│   ├── gemma_prefilter        (if enabled)
│   ├── gemini_extraction      × 2 samples
│   └── persist_clauses
├── reconcile (× N clauses, parallel)
│   ├── embed
│   ├── find_similar
│   ├── guardrail
│   ├── judge                  (only when reached)
│   └── apply_verdict
└── impact
    ├── materialize_requirements
    ├── evaluate
    └── rollup_status
```

The parallel reconcile spans make the fan-out visible, which is exactly what you
need when debugging the concurrency race from phase 3.

Do not hand-roll this. Use the OpenTelemetry FastAPI instrumentation plus manual
spans on the pipeline stages. Budget two hours, not a day.

## Metrics

Log-based metrics in Cloud Monitoring — no separate metrics backend.

| Metric | Type | Alert |
|---|---|---|
| Pipeline stage duration | Distribution, by stage | p95 extract > 120s |
| **End-to-end propagation latency** (upload → `status_changed`) | Distribution | **> 90s** — this is the PRD's headline metric; measure it, do not eyeball it |
| Extraction confidence | Distribution | — |
| Guardrail rejections by reason | Counter | — |
| Judge invocation rate | Counter | Sudden spike means the guardrail regressed |
| Verdict distribution | Counter by verdict | Any `conflict` on same-jurisdiction pairs = bug |
| DLQ message count | Gauge | **> 0** |
| Documents in `failed` | Gauge | > 0 |
| Vertex token spend | Counter | Daily budget threshold |
| Query grounding failures | Counter | > 0 — an ungrounded answer is a product failure |

## Alerts

Five, to a channel you actually read. More than five and you ignore all of them.

1. **DLQ non-empty** — something failed five times.
2. **End-to-end latency > 90s** — the demo promise is broken.
3. **Any `failed` document** — visible immediately, not on next page load.
4. **Uptime check failure** on `/health` for either service.
5. **Budget threshold** at 50% and 90%.

## Error Reporting

Enable Cloud Error Reporting. Unhandled exceptions in either service group
automatically. This costs one line of setup and saves an hour the first time a
worker throws.

## The debug view (highest value per hour of work)

`GET /debug/documents/{id}` plus a simple page, gated behind an env flag:

- `trace_id`, copyable, with a deep link to the Cloud Logging query
- Full `stage_log` with timings
- Every extracted candidate, including the **rejected** ones and why
- Confidence breakdown per clause
- Every guardrail decision with its reason
- Whether the judge was invoked, and its raw verdict
- Every `graph_event` written by this document
- Raw model responses, truncated

Build this in phase 2 and extend it each phase. It will save more time than it
costs by phase 3, and it is a genuinely impressive thing to show a technical judge
— it demonstrates the "deterministic code gates the model" claim rather than
asserting it.

## Dashboard

One Cloud Monitoring dashboard, the pipeline as a funnel:

```
documents uploaded → extracted → clauses created → reconciled
  → verdicts (new / supersede / conflict / needs_review)
  → requirements evaluated → status changes
+ DLQ depth · p95 stage latency · token spend
```

If a number drops to zero mid-demo, you see where.

## What we are not building

| Not building | Why |
|---|---|
| Prometheus / Grafana | Cloud Monitoring is already there and integrated |
| Sentry or third-party APM | Error Reporting covers it at this scale |
| Custom log aggregation | Cloud Logging queries are sufficient |
| SLOs / error budgets | Meaningful over weeks, not twelve days |
| Distributed tracing across the frontend | The backend pipeline is where the mystery lives |
| Log-based anomaly detection | Five alerts and a dashboard is the right amount of machinery here |
