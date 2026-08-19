# ReguLens — Data Model, State Machines, API Surface

Firestore, single workspace. Every document carries `workspace_id` (hardcoded in
MVP) so that adding tenancy later is a filter, not a migration.

## Build checklist

Tick when the collection exists, its Pydantic model is written, and its repository
enforces event-writing on mutation.

- [ ] `documents` (phase 2)
- [ ] `clauses` (phase 2)
- [ ] `products` (phase 1)
- [ ] `markets` — seeded (phase 1)
- [ ] `requirements` (phase 4)
- [ ] `conflicts` (phase 3)
- [ ] `graph_events` — append-only, enforced by the repository layer (phase 1)
- [ ] `query_logs` (phase 5)
- [ ] Composite indexes deployed via `firestore.indexes.json` (phase 0)
- [ ] Every repository method writes its event in the same batch — no raw update
      method is exposed (phase 1, verified in phase 6)

## Collections

### `documents`
Raw ingestion record and pipeline state.

```json
{
  "id": "doc_001",
  "workspace_id": "ws_demo",
  "filename": "eu_food_additives_2026.pdf",
  "content_sha256": "9f2c...",
  "source_type": "official_regulation",
  "source_name": "European Commission",
  "jurisdiction": "EU",
  "declared_effective_date": "2026-01-01",
  "storage_uri": "gs://regulens-uploads/...",
  "page_count": 42,
  "status": "reconciled",
  "stage_log": [
    {"stage": "extracting", "at": "...", "ok": true},
    {"stage": "extracted",  "at": "...", "ok": true, "clause_count": 6}
  ],
  "error": null,
  "uploaded_at": "..."
}
```

`content_sha256` is the extraction cache key. Re-uploading an identical file
short-circuits to the existing clauses.

### `clauses`
A single extracted regulatory statement. The atom of the knowledge graph.

```json
{
  "id": "clause_eu_benzoate_v2",
  "workspace_id": "ws_demo",
  "document_id": "doc_001",
  "text": "The maximum permitted level of sodium benzoate (E211) in ...",
  "clause_type": "numeric_limit",
  "substance": "sodium benzoate",
  "substance_normalized": "sodium_benzoate",
  "limit_value": 0.05,
  "unit": "percent_w_w",
  "product_type": "food_beverage_powder",
  "jurisdiction": "EU",
  "effective_date": "2026-01-01",
  "authority_tier": 1.0,
  "confidence": 0.94,
  "confidence_breakdown": {
    "parse_quality": 0.95,
    "self_consistency": 1.0,
    "authority_tier": 1.0
  },
  "embedding": [0.013, -0.221, "..."],
  "status": "active",
  "supersedes": "clause_eu_benzoate_v1",
  "superseded_by": null,
  "created_at": "..."
}
```

`clause_type` is `numeric_limit` | `documentation` | `labeling` | `certification`
| `other`. Only `numeric_limit` is evaluated pass/fail in MVP; the rest are
surfaced as `needs_review`. This is a deliberate honesty constraint, not a gap to
paper over.

`unit` is a normalized enum (`percent_w_w`, `mg_per_kg`, `ppm`), not free text.
Unit normalization happens at extraction; unconvertible units make a clause
non-comparable rather than silently coerced.

### `products` — the compliance twin

```json
{
  "id": "prod_001",
  "workspace_id": "ws_demo",
  "name": "Herbal Drink Powder",
  "product_type": "food_beverage_powder",
  "origin": "ID",
  "ingredients": [
    {"name": "ginger",           "normalized": "ginger",           "amount": null, "unit": null},
    {"name": "sodium benzoate",  "normalized": "sodium_benzoate",  "amount": 0.08, "unit": "percent_w_w"}
  ],
  "packaging": "250g plastic pouch",
  "target_markets": ["market_de"],
  "created_at": "..."
}
```

### `markets`
Seeded, not user-created in MVP.

```json
{"id": "market_de", "country": "Germany",   "country_code": "DE", "jurisdictions": ["EU"]}
{"id": "market_id", "country": "Indonesia", "country_code": "ID", "jurisdictions": ["ID_BPOM"]}
```

`jurisdictions` is a list because a market can inherit multiple regimes
(EU-wide plus national). MVP seeds two markets and two jurisdictions.

### `requirements`
The materialized join: *this clause binds this product in this market*. This is
what makes impact propagation cheap.

```json
{
  "id": "req_001",
  "workspace_id": "ws_demo",
  "product_id": "prod_001",
  "market_id": "market_de",
  "jurisdiction": "EU",
  "clause_id": "clause_eu_benzoate_v2",
  "requirement_type": "numeric_limit",
  "substance_normalized": "sodium_benzoate",
  "limit_value": 0.05,
  "unit": "percent_w_w",
  "product_value": 0.08,
  "evaluation": "fail",
  "severity": "high",
  "status": "active",
  "evaluated_at": "..."
}
```

`evaluation` is `pass` | `fail` | `needs_review` | `not_applicable`.
`severity` is derived deterministically: `fail` on a numeric limit → `high`;
`needs_review` → `medium`; a superseded-but-unresolved clause → `medium`.

### `conflicts`

```json
{
  "id": "conf_001",
  "workspace_id": "ws_demo",
  "clause_a": "clause_id_benzoate",
  "clause_b": "clause_eu_benzoate_v2",
  "type": "cross_jurisdiction_limit_mismatch",
  "detail": {"a": 0.10, "b": 0.05, "unit": "percent_w_w"},
  "severity": "high",
  "status": "open",
  "detected_by": "reconciliation_agent",
  "created_at": "..."
}
```

`type` is `limit_tightened` | `limit_loosened` | `cross_jurisdiction_limit_mismatch`
| `effective_date_conflict` | `ambiguous`.

Note the distinction that matters: two clauses from the *same* jurisdiction with
different limits is a **supersede** question (which is current?). Two clauses from
*different* jurisdictions is a **cross-jurisdiction conflict** (both are true, and
the stricter one binds the export). Conflating these produces nonsense; the
guardrail separates them before the judge is called.

### `graph_events`
Append-only. Never updated, never deleted. This is the audit trail and the
timeline data source.

```json
{
  "id": "evt_001",
  "workspace_id": "ws_demo",
  "event_type": "requirement_changed",
  "entity_type": "requirement",
  "entity_id": "req_001",
  "before": {"limit_value": 0.10, "evaluation": "pass"},
  "after":  {"limit_value": 0.05, "evaluation": "fail"},
  "cause": {"document_id": "doc_001", "clause_id": "clause_eu_benzoate_v2"},
  "triggered_by": "reconciliation_agent",
  "confidence": 0.94,
  "occurred_at": "..."
}
```

`event_type`: `document_ingested`, `clause_created`, `clause_superseded`,
`clause_flagged_review`, `conflict_opened`, `requirement_created`,
`requirement_changed`, `product_status_changed`.

Every write to `clauses`, `requirements`, or `conflicts` goes through a repository
method that writes the event in the same batch. Not a convention — the repository
does not expose a raw update.

### `query_logs`

```json
{
  "id": "q_001",
  "workspace_id": "ws_demo",
  "question": "Why is my product at risk?",
  "product_id": "prod_001",
  "retrieved_clause_ids": ["clause_eu_benzoate_v2", "clause_id_benzoate"],
  "answer": "...",
  "cited_clause_ids": ["clause_eu_benzoate_v2"],
  "confidence": 0.91,
  "latency_ms": 3120,
  "created_at": "..."
}
```

Logged for evaluation, not analytics. Phase 5 uses it to check grounding.

## State machines

### Document
```
uploaded → extracting → extracted → reconciling → reconciled
             ↓              ↓            ↓
           failed        failed       failed
```
`failed` records the stage and error and is retryable from that stage.

### Clause
```
                  ┌──────────────┐
pending_review ◄──┤              │
                  │  extracted   │
   active ◄───────┤              │
                  └──────────────┘
active → superseded        (a newer same-jurisdiction clause replaces it)
active → conflicted        (open cross-jurisdiction conflict references it)
active → needs_review      (confidence dropped below threshold, or judge abstained)
needs_review → active      (human confirms — MVP: a button, no workflow)
```

### Conflict
```
open → resolved            (MVP: manual only; no auto-resolution)
```

### Requirement evaluation
```
not_applicable  — product has no matching substance
pass            — product value ≤ limit
fail            — product value > limit
needs_review    — non-numeric clause, unit mismatch, or clause confidence < 0.5
```

Absence of data is `needs_review`, never `pass`. A product with an unmeasured
ingredient must never render as compliant.

## Pub/Sub messages

Contract detail lives in `01-architecture.md`; the data-model obligations are:

| Topic | Payload | Idempotency key |
|---|---|---|
| `document.uploaded` | `{document_id, workspace_id}` | `documents.status` past `extracted` → ack, no-op |
| `clause.extracted` | `{clause_id, document_id, workspace_id}` | `clauses.status` past `pending_reconciliation` → ack, no-op |
| `graph.changed` | `{entity_type, entity_id, clause_id, workspace_id}` | last `graph_events` entry for the entity already reflects this cause → ack, no-op |

Delivery is at-least-once. Every handler reads current state before acting. A
redelivered message must never create a second clause, a second conflict, or a
second alert — this is asserted by test in phases 2, 3, and 4.

Clause mutations run inside a Firestore transaction that re-reads the target clause
and aborts if its status changed, because per-clause fan-out means several
reconciliations can target the same existing clause at once.

## API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/products` | Create a compliance twin |
| `GET` | `/products` | List |
| `GET` | `/products/{id}` | Twin detail |
| `PATCH` | `/products/{id}` | Edit ingredients / markets |
| `GET` | `/markets` | Seeded markets |
| `POST` | `/documents` | Multipart upload + source metadata → `202 {document_id}` |
| `GET` | `/documents` | List with status |
| `GET` | `/documents/{id}` | Status + `stage_log` (polled by the stepper) |
| `POST` | `/documents/{id}/retry` | Retry from the failed stage |
| `GET` | `/clauses` | Filter by jurisdiction / substance / status |
| `GET` | `/conflicts` | Open conflicts |
| `GET` | `/products/{id}/compliance?market_id=` | Readiness view: requirements + evaluations + issue counts |
| `GET` | `/products/{id}/events` | Timeline (from `graph_events`) |
| `GET` | `/alerts` | Unacknowledged `product_status_changed` events |
| `POST` | `/query` | `{question, product_id?}` → answer + citations + confidence |
| `POST` | `/admin/seed` | Trigger the seed Cloud Run Job — reset to demo baseline (phase 6) |
| `POST` | `/internal/extract` | Pub/Sub push target, OIDC-authenticated, worker service only |
| `POST` | `/internal/reconcile` | Pub/Sub push target, OIDC-authenticated, worker service only |
| `POST` | `/internal/impact` | Pub/Sub push target, OIDC-authenticated, worker service only |

Polling, not websockets. A 2-second poll on one document during a demo is not a
problem worth a socket layer.

The `/internal/*` endpoints live on the worker service and are never exposed to the
browser. They are the security boundary that matters in an unauthenticated MVP.

## Firestore indexes required

- `clauses`: `(workspace_id, jurisdiction, status)` — retrieval candidate set
- `clauses`: `(workspace_id, substance_normalized, status)` — guardrail lookup
- `requirements`: `(workspace_id, product_id, market_id)` — readiness view
- `requirements`: `(workspace_id, clause_id)` — impact propagation from a clause
- `graph_events`: `(workspace_id, entity_id, occurred_at desc)` — timeline
- `graph_events`: `(workspace_id, event_type, occurred_at desc)` — alerts

Create these in phase 0 as `firestore.indexes.json` and deploy them. Discovering a
missing composite index during the demo is an avoidable failure.
