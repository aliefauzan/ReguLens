# Phase 1 — Compliance Twin

**Estimate:** 1 day (Aug 21)
**Demo sentence:** "This is my product, these are its ingredients and amounts, and I want to ship it to Germany."

**Status:** `NOT STARTED` · **Started:** — · **Completed:** —

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
- [ ] `products` collection per `02-data-model.md`.
- [ ] `markets` seeded: Germany (`EU`) and Indonesia (`ID_BPOM`).
- [ ] Ingredient normalization: a small dictionary mapping input names and common
      synonyms/E-numbers to `substance_normalized`
      (`sodium benzoate`, `natrium benzoat`, `E211` → `sodium_benzoate`).
      Start with ~20 entries covering the demo substances. Unknown names pass
      through slugified and are flagged as unnormalized — do not silently guess.
- [ ] Unit parsing: accept `%`, `percent`, `mg/kg`, `ppm`; normalize to the enum;
      reject anything else with a clear field error.

### API
- [ ] `POST /products`, `GET /products`, `GET /products/{id}`, `PATCH /products/{id}`.
- [ ] Validation: ingredient amounts must have a unit if present; product_type is
      an enum, not free text (the guardrail depends on it matching clause
      `product_type`).
- [ ] Every create/update writes a `graph_events` record. Build the
      event-writing repository wrapper **now** — retrofitting it later is how audit
      trails end up with holes.

### Web
- [ ] Product create form: name, product type, origin, packaging, destination
      market, and an ingredient list with name + amount + unit rows.
- [ ] Product detail page rendering the twin (the "Compliance Twin" card from the
      concept: ingredients, packaging, origin, destination).
- [ ] Empty state on the home page that leads into the create form.
- [ ] A placeholder readiness panel that honestly says "No regulatory data ingested
      yet" — not a fake 0% or a fake 100%.

## Exit criteria

- [ ] Creating the demo product through the UI persists it and it survives a reload.
- [ ] `sodium benzoate 0.08%` round-trips as
      `{normalized: "sodium_benzoate", amount: 0.08, unit: "percent_w_w"}`.
- [ ] `E211` and `natrium benzoat` normalize to the same substance.
- [ ] `GET /products/{id}/events` shows the `product_created` event.
- [ ] Deployed.

## Out of scope

Editing history UI, multiple products in the demo path (the model supports many;
the demo uses one), product images, SKU/volume fields, market management UI.

## Risk notes

- Substance normalization is the hidden load-bearing piece of this whole system: if
  the product says `sodium benzoate` and the clause says `E211`, nothing downstream
  matches and the demo silently shows "no issues". Write unit tests for the
  synonym table in this phase, not later.
