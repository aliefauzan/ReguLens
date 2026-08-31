# Phase 9 — Country Discovery

**Status:** `COMPLETE` — deployed and exercised from Cloud Run, not only from a
laptop.
**Started:** 31 Aug 2026
**Completed:** 31 Aug 2026
**Branch:** `feat/country-discovery`, merged

## Why

`SEED_SOURCES` is four hand-written addresses. A user importing into a country
nobody seeded gets no monitoring at all — the product silently narrows to "a
compliance checker for Germany and Indonesia". This phase lets a user name any
country and have ReguLens go and find where that country's regulator publishes.

## The measurement that shaped the design

Run against `gemma-4-31b-it` on 31 Aug 2026, six countries:

| Asked for | Result |
|---|---|
| Regulator name | 6 / 6 correct |
| Regulator root domain | 6 / 6 correct |
| A URL with a path | **0 / 14 resolved** — 404, timeout, or 403 |
| Homepage crawl for additive links | junk (SFA returned training courses) |
| Gemini + `google_search` grounding | 429 — grounding is not on this key's tier |
| FAO / FAOLEX, Codex GSFA as an aggregator | 403 to our user agent |

A model has no index. It reconstructs a plausible path and regulators rewrite
paths constantly. **No prompt fixes this**, so the model is never asked for a
path. It is asked for the regulator and the root domain — the two things it gets
right — and everything deeper is read off pages actually fetched:

```
hop 0  model: country -> regulator + root URL
hop 1  fetch the root -> its real link inventory
hop 2  model: pick the regulations index FROM THAT INVENTORY (in-list enforced)
hop 3  fetch the pick -> derive link_pattern from real paths, deterministically
commit an ordinary LISTING source + the market that makes it visible
```

Hop 2 cannot hallucinate: the model selects from a list we hand it, and a URL it
writes rather than selects is dropped and logged.

## What landed

- [x] `api/app/core/discovery.py` — the four hops, all refusals named
- [x] `api/app/core/data/countries.json` — ISO 3166-1, 249 entries, code and name
      only. No bundled regulator names: 249 hand-written facts is 249 chances to
      ship a wrong one, and the model names the regulator correctly anyway
- [x] `markets.ensure_market` — **the load-bearing half.** `impact.py:94` skips
      any clause whose jurisdiction no market lists, so a source committed
      without its market ingests regulations that never reach a verdict. Adds to
      an existing market's `jurisdictions` rather than replacing (Indonesia
      keeps `ID_BPOM`)
- [x] `llm.generate_structured` — a JSON call against an arbitrary model, reusing
      `_generate` so the closed-transport workaround is not duplicated
- [x] `country.requested` topic, `/internal/country-requested` worker handler,
      idempotent via `processed_messages` like every other handler
- [x] `GET /countries`, `POST /countries/discover`, `GET /discovery/{id}`,
      `GET /discovery/{id}/events` (SSE)
- [x] `web/app/sources/DiscoverPanel.tsx` — typeahead, live progress, and every
      rejection rendered with its reason
- [x] 52 tests across `test_discovery.py` and `test_discovery_routes.py` — 39
      when this line was written, grown by the fixes the live runs exposed
- [x] Deployed and verified from Cloud Run — 31 Aug, revision carrying
      `8ac0ed0-215957`, `DISCOVERY_API_KEY` mounted on both api and worker.
      Two runs against the deployed stack: **Singapore** committed
      `sfa.gov.sg/legislation` (4 links matched) and turned away its circulars
      page (0 matched); **Japan** committed `mhlw.go.jp/hourei/` (4 matched) and
      turned away `shokanhourei/index.html` (0 matched). Both are now in
      `/sources` and swept with the rest. The datacentre caveat below is
      therefore answered for these two, and only these two

## Follow-up — the product form only offered two countries (1 Sep 2026)

Discovery could register a source for any country, and the product form still
named Germany and Indonesia in its source. The narrowing this phase set out to
remove was therefore still there one screen away: a user who discovered Japan on
the Sources page could not tell ReguLens they sell into Japan.

Worse than cosmetic, and the reason this is written down rather than filed as a
tweak: `impact.evaluate` keeps only the target markets that exist in the
`markets` collection, so a product naming a market with no document loses that
country with **no verdict row and no error** — the same silent-omission failure
`ensure_market` was added to prevent, one layer up.

- [ ] `POST /markets` — makes a market exist for an ISO country so a product can
      name it. Country name comes from the bundled list; an unknown code is
      refused. `ensure_market` takes an optional regulator, because a market can
      exist before anybody has found who writes its rules, and does not claim to
      have been `discovered` when nothing discovered it. Not deployed
- [ ] `web/app/products/MarketsField.tsx` — tiles for the markets that exist
      (the two seeded plus every country anybody has watched), a dropdown for the
      remaining 240-odd. Picking one creates the market, **then starts watching
      it** — the same discovery run the Sources page offers, streamed onto the
      tile: `Looking up its regulator…` → the regulator's name, or
      `Could not find where it publishes` with the reason underneath. A country
      discovery cannot read stays selectable and says `not watched yet`, because
      the product still records where it is sold. A target market missing from
      `/markets` still renders, so editing a product cannot silently drop a
      country. Not deployed
- [ ] One country, one rulebook on the tile. A discovered market accumulates
      both its named regime and the bare country code its sources are registered
      under (`["ID_BPOM", "ID"]`), and rendering both read "BPOM, National
      rules" — a country with two separate rulebooks, which is not a thing. A
      named regime now wins over the country code, and the regulator's own name
      is used before the word "national". Not deployed
- [ ] `marketName` falls back to the country's name via `Intl.DisplayNames`, so a
      market this phase created reads "Japan" rather than "JP" on every page that
      names one. Not deployed
- [x] 5 tests in `test_market_routes.py`; 669 passing, ruff and tsc clean
- [x] Verified against the emulators, both endings. Adding Japan created
      `market_jp`, the saved product listed it, and its verdict read "No rules
      added yet". Adding Singapore ran the whole path — market created,
      `country.requested` published, worker discovered, `Singapore —
      Legislation` committed as a watched LISTING — and the tile went from
      "Starting to watch it…" to "Singapore Food Agency rules" without a reload.
      The failure ending was exercised too (worker with no model credentials):
      the tile said "Could not find where it publishes" and printed the reason


## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Gemma 4 via the **Gemini Developer API**, not Vertex | Vertex does not serve Gemma as a publisher model — verified, it 404s. The Developer API serves it **free of charge with no paid tier at all**, so this flow cannot generate a bill |
| 2 | The model proposes, never writes | Measured: 0/14 model-authored URLs exist. Hop 2 picks from fetched links; an out-of-list pick is dropped |
| 3 | `link_pattern` is derived in code, never asked for | A regex is exactly what a model produces confidently and wrongly, and it decides what the nightly sweep ingests |
| 4 | Commit a `LISTING`, not a `DOCUMENT` | Same reason the BPOM seed watches `jdih.pom.go.id/`: a watched document only sees edits to rules you already know about |
| 5 | SSE reads the job row, not a per-job Pub/Sub topic | The API service holds `pubsub.publisher` only. A topic per job needs a new role, runtime topic creation, and a reaper. The job row already holds every state |
| 6 | One worker handler, no per-candidate fan-out | Two candidates inside a 600-second ack deadline. A second topic buys a DLQ and an idempotency table for nothing |
| 7 | Only an exhausted quota is retried | Free tier is 16,000 input tokens/min/model (measured — undocumented). It refills; a regulator's 403 does not |

## Known limits — state these, do not paper over them

- **Yield is roughly one country in three**, now confirmed on the deployed stack
  rather than a laptop. Measured: Singapore and Japan commit
  a real source; Malaysia 403s, India and Vietnam time out, the Philippines
  serves a JavaScript application with no anchors in the HTML. Every one renders
  its reason.
- The six-country measurement above was taken from a laptop. The standing rule
  says a URL that answers a laptop can answer a datacentre with a challenge page,
  so the deployed yield may differ from it. Singapore and Japan have since been
  re-run from Cloud Run and behaved identically; the other four have not been
  re-run there, and the one-in-three figure is still the laptop's number.
- Discovery finds *where regulations are published*. Whether what it then ingests
  is on-topic is the extraction pipeline's job, unchanged by this phase.
