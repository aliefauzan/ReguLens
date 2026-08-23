# Phase 1 — Compliance Twin

**Estimate:** 1 day (Aug 21)
**Demo sentence:** "This is my product, these are its ingredients and amounts, and I want to ship it to Germany."

**Status:** `IN PROGRESS` · **Started:** 19 Aug 2026 · **Completed:** —

<!-- MAINTAIN THIS FILE.
     Set Status to IN PROGRESS when you begin, COMPLETE when every exit criterion
     is ticked. Fill the dates. Tick each `- [ ]` as it lands — a ticked box means
     it exists in the repo and is deployed, not that it is written down somewhere.
     If you deliberately skip an item, change it to `- [~]` and add ` — SKIPPED:
     reason` on the same line so nobody re-litigates it later.
     Then update ../PROGRESS.md. -->

## Goal

Give the system something to have an opinion *about*. Every later phase reasons
against the twin; without it, extraction and reconciliation have no consequence.

## Why this phase comes before ingestion

Impact propagation is the product thesis. Building extraction first tempts you to
build a document-analysis tool and bolt the product on later — which is exactly
the positioning the concept explicitly rejects.

## Scope

### Data
- [x] `products` collection per `02-data-model.md`.
- [x] `markets` seeded: `market_de` (Germany, `EU`) and `market_id` (Indonesia, `ID_BPOM`), matching the data model's ids and `jurisdictions` list.
- [x] Ingredient normalization — 20 canonical substances in
      `app/core/normalization.py`, each with English and Indonesian names plus
      E-/INS-numbers. `sodium benzoate`, `natrium benzoat`, `E211`, `INS 211` and
      `Sodium Benzoate (E211)` all converge. Unknown names slugify through with
      `unnormalized: true` and the UI badges them "unrecognised" — no guessing.
- [x] Unit parsing — `%`, `percent`, `% w/w`, `mg/kg`, `ppm` and case variants map
      to the enum; anything else raises `unrecognised unit '<x>'. Use one of: %,
      mg/kg, ppm`. Nothing is silently coerced.

### API
- [x] `POST /products`, `GET /products`, `GET /products/{id}`, `PATCH /products/{id}`, plus `GET /products/{id}/events`. All exercised against the deployed service.
- [x] Validation — an amount without a unit returns 422 with the ingredient named;
      a free-text `product_type` returns 422. Both verified against the deployed
      API, not just in unit tests.
- [x] Every create/update writes a `graph_events` record **in the same Firestore
      batch** as the change. `app/core/repository.py` exposes no raw update, so
      reaching around the audit trail is not possible from the API surface. Each
      event carries the request's `trace_id`.

### Web
- [x] Product create form — all fields plus repeatable ingredient rows, with
      `data-testid` on every control for phase 6.
- [x] Product detail page rendering the twin, each ingredient showing both the
      entered name and its normalized form, plus the audit trail.
- [x] Empty state on the home page that leads into the create form — and a distinct error state, so an unreachable API never looks like an empty account.
- [x] Readiness panel says "No regulatory data ingested yet. Nothing has been
      evaluated against this product, so there is no readiness figure to report."
      No number, fake or otherwise.

## Exit criteria

- [x] Creating the demo product **through the UI** persists it and it survives a reload — driven in a real browser, not simulated. Surfaced a genuine CORS failure on the way (the form calls the API directly from the browser); origin list fixed and now pinned in `cloudbuild.yaml`.
- [x] `sodium benzoate 0.08%` round-trips as
      `{normalized: "sodium_benzoate", amount: 0.08, unit: "percent_w_w"}`.
- [x] `E211` and `natrium benzoat` normalize to the same substance — `natrium benzoat` entered through the UI rendered as `sodium_benzoate`.
- [x] `GET /products/{id}/events` shows `product_created`, and `product_updated` after a PATCH.
- [x] Deployed. — API, worker and **web** all serving on Cloud Run
      (`regulens-web`); the Vercel dependency was dropped on 23 Aug when the
      Next.js app shipped as a fourth Cloud Run service with CORS pinned.
      Verified from a cold browser: home page renders products from Firestore
      via the API.

## Out of scope

Editing history UI, multiple products in the demo path (the model supports many;
the demo uses one), product images, SKU/volume fields, market management UI.

## Risk notes

- Substance normalization is the hidden load-bearing piece of this whole system: if
  the product says `sodium benzoate` and the clause says `E211`, nothing downstream
  matches and the demo silently shows "no issues". Write unit tests for the
  synonym table in this phase, not later.
