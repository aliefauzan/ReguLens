# Phase 8 — Watched Sources (live regulatory monitoring)

**Estimate:** 1 day (Aug 29)
**Demo sentence:** "Nobody uploaded this. The regulator changed the page overnight and the product was already flagged when we opened the app."

**Status:** `COMPLETE` · **Started:** 29 Aug 2026 · **Completed:** 29 Aug 2026

> Added after phase 7 began, because the honest description of the product was
> "a compliance checker": nothing entered the graph unless a person went and
> found it. The pitch says *monitor*. Either the word had to go or the feature
> had to exist, and the feature is the smaller change.

<!-- MAINTAIN THIS FILE.
     Set Status to IN PROGRESS when you begin, COMPLETE when every exit criterion
     is ticked. Fill the dates. Tick each `- [ ]` as it lands — a ticked box means
     it exists in the repo and is deployed, not that it is written down somewhere.
     If you deliberately skip an item, change it to `- [~]` and add ` — SKIPPED:
     reason` on the same line so nobody re-litigates it later.
     Then update ../PROGRESS.md. -->

## Goal

A regulator's own address, re-read on a schedule, so a rule that changes
overnight is in the graph before anyone goes looking for it — and so the word
"monitoring" in the pitch describes behaviour that actually runs.

## Scope

- [x] `api/app/core/fetching.py` — conditional HTTP GET, markup-to-text, RSS and
      Atom parsing. No Firestore in it, so every decision is testable offline.
- [x] `api/app/core/sources.py` — the registry, the check, and the sweep.
- [x] `WatchedSource` / `WatchedSourceIn` / `WatchedSourcePatch` in `models.py`,
      with `SourceKind` and `SourceCheckStatus` as enums rather than strings.
- [x] Four source kinds: `document` (the wording changed), and three that can
      surface a rule never seen before — `feed` (a new RSS/Atom entry),
      `listing` (a new link on a regulator's index), `sparql` (a new act in a
      publisher's catalogue).
- [x] `GET|POST /sources`, `PATCH|DELETE /sources/{id}`, `POST /sources/seed`,
      `POST /sources/{id}/check`.
- [x] `POST /internal/check-sources` on the worker — the scheduled sweep, OIDC
      gated like every other internal route.
- [x] Cloud Scheduler job in `scripts/setup.sh`: daily 06:00 `Asia/Jakarta`,
      OIDC as `regulens-pubsub-invoker`, audience = the worker's root URL.
- [x] `/sources` page: every row shows last read, last change, check count, the
      error if there is one, and a "Check now" button.
- [x] Four seeded addresses, all verified against the live endpoints before
      being written down. Both markets can discover, not only re-read.
- [x] 83 tests in `api/tests/test_sources.py`.

## The decisions, and why

- [x] **A change is a change of wording, not of bytes.** EUR-Lex stamps a fresh
      session id into every response; the raw body differs on every fetch while
      the regulation has not moved. Hashing bytes would have reported a change —
      and billed a model run — every single night. The signal is a hash of the
      extracted text. Verified live: three consecutive checks of the same
      EUR-Lex page, `changed` then `unchanged` then `unchanged`.
- [x] **Conditional GET is a bonus, not the mechanism.** CELLAR sends an
      `ETag`; the EUR-Lex web page sends neither it nor `Last-Modified`. Both
      are used when a server offers them and short-circuit the download
      entirely; the text hash covers the rest.
- [x] **The seeded EU source is CELLAR, not the EUR-Lex page.** Found the hard
      way. The EUR-Lex HTML URL works from a laptop and was verified locally
      three times; deployed, the first scheduled sweep recorded
      `status: error` against it, and the log said `http_status 202, bytes 2031,
      chars 0` — a challenge page served to a datacentre address. CELLAR, the
      Publications Office's machine-readable endpoint, returns the same 48,417
      characters of the same regulation and sends an `ETag`. Two things changed
      because of it: an empty 2xx body is now its own named failure rather than
      being reported as "a login page or a scan", and `Accept` is sent
      explicitly — CELLAR content-negotiates, and a request without it is
      answered with 124,304 characters of RDF *about* the regulation, which
      reached extraction once and failed there.
- [x] **Ingestion goes through `documents.create_document`.** Same hash, same
      Pub/Sub message, same extraction, same guardrail, same review queue.
      Nothing read from a watched address can become a clause by a route an
      upload could not use.
- [x] **Watching a known address cannot find an unknown regulation.** A
      `document` source reports that a rule you already hold was edited, and
      nothing more — a regulation published tomorrow arrives at an address
      nobody has seen, and no amount of re-reading the old one will mention it.
      That gap is what `listing` closes: a regulator's index page, a pattern
      saying which links are regulations, and any link not seen before treated
      as a new document. The pattern is required rather than defaulted, because
      an index page also links to news, social media and a language switcher,
      and a watcher that followed all of them would ingest the website.
- [x] **Asked, not scraped, where the publisher offers it.** A listing depends
      on a regex still matching a page a designer may rewrite. A catalogue query
      depends on the publisher's own classification of its own acts, which is
      what that classification is for. The EU both offers one and requires it,
      since EUR-Lex's web pages refuse datacentre addresses. Measured on the
      live endpoint before writing the query down: 133 works a year carry the
      EuroVoc *food additive* concept, and the CELEX shape filter
      (`^3\d{4}R\d{4}$`) leaves roughly a dozen regulations — dropping merger
      notices, proposals and corrigendum notices.
- [x] **A catalogue query looks back a fixed window, not "since the last
      check".** A missed run, a clock skew or a restored backup would otherwise
      open a gap nobody notices. Re-asking for the same 120 days costs nothing:
      everything already read is already remembered.
- [x] **An identifier is not a name.** A CELEX id says which act a row is; it is
      not what anyone wants to read on a document row. Catalogue items carry
      `prefer_detected_title`, so the act states its own title and detection
      reads it — the same detection that already produced "COMMISSION REGULATION
      (EU) 2023/2108" off a fetched page.
- [x] **A pattern that matches nothing is an error, not a quiet pass.** A site
      redesign means nobody is watching that regulator any more, and "no links
      matched" would otherwise be indistinguishable from "no new regulations".
- [x] **A permanent refusal is remembered; a transient one is not.** BPOM's
      Kategori Pangan annex is 308 pages and will be 308 pages tomorrow, so the
      refusal is final and the item is marked seen. A timeout or an empty page
      is not — EUR-Lex serves an empty challenge page to datacentre addresses,
      and abandoning a regulation because it was briefly behind one is the worse
      mistake. Without the split, one oversized PDF is downloaded and refused
      every night forever, holding a slot in the per-run cap that a readable new
      regulation needed.
- [x] **A feed's first read ingests nothing.** Adopting a feed means "tell me
      what happens next", not "read the last twenty things that happened" —
      which would have been twenty extraction runs on adoption. The first check
      records the entry ids and returns `baselined`.
- [x] **A burst is capped at three entries per run.** The rest stay unseen and
      come back next time, so a regulator publishing ten things overnight is not
      an unbounded bill before anyone is awake.
- [x] **A failed entry stays new.** Only entries actually read are marked seen,
      so a regulation that was briefly unreachable is retried rather than
      skipped forever.
- [x] **Refused, not truncated.** A document past `MAX_FETCH_CHARS` is rejected
      with a reason. A confident answer drawn from the half of a regulation that
      happened to fit is worse than no answer.
- [x] **A broken source is rendered, not swallowed.** A 403, a login wall, a PDF
      with no text layer: recorded on the source, shown on the page. A source
      erroring quietly for a week means nobody is watching it, and if that is
      invisible the monitoring claim is a lie.
- [x] **The check lock is a Firestore transaction.** Cloud Scheduler retries,
      and a user pressing "Check now" during the nightly sweep is not exotic.
      Two simultaneous checks would both see "no stored hash" and both ingest.
      A lock older than `SOURCE_CHECK_LOCK_SECONDS` is treated as belonging to a
      crashed process rather than stranding the source forever.
- [x] **A feed's XML is parsed with the DOCTYPE refused.** Entity expansion in
      XML fetched from an address a user typed is a denial of service against
      the nightly job. No real RSS or Atom feed carries a DOCTYPE, so the whole
      construct is rejected before the parser sees it — no new dependency.
- [x] **`<main>` wins where a page names one.** A government CMS wraps the page
      in five kilobytes of navigation and a twenty-four-language switcher, and
      every character of it would go to the model. Falls back to the whole
      document, which EUR-Lex needs: its pages predate `<main>`. A content
      region under a fifth of the page is treated as a widget and ignored.

## The seeded watch list

Both were fetched, size-checked and read twice before being written into
`SEED_SOURCES`.

| Address | Kind | Type | Size | Why this one |
|---|---|---|---|---|
| `publications.europa.eu/resource/celex/32023R2108` | `document` | `official_regulation` | 48,417 chars | A real amendment to the Annex II of Regulation 1333/2008 the app already carries excerpts of. Reached through CELLAR, not the EUR-Lex page — see below |
| `food.ec.europa.eu/node/2/rss_en` | `feed` | `news_article` | 30 entries | The Commission's own food-safety feed. Tier 0.35, so anything read here waits for a human — which is the guardrail doing its job, visibly |
| Publications Office SPARQL endpoint | `sparql` | `official_regulation` | ~12 regs/yr in scope | The EU's own catalogue, asked directly. The only EU route that finds an act at an address nobody has seen, and the only one that works from Cloud Run at all |
| `jdih.pom.go.id/` | `listing` | `official_regulation` | 12 links | BPOM's legal-documentation portal. The only seeded source that can find a regulation nobody knew about; its download links carry the number, year and full title in the path |

**A fifth route exists and is deliberately unseeded.** EUR-Lex serves a saved
search as RSS, which plugs into `feed` with no code at all. It is the right tool
for a scope narrower or wider than the seeded query — but the feed id is tied to
a EUR-Lex account, so there is nothing generic to ship.

Deliberately **not** seeded, and each for a stated reason:

- [~] Regulation 1129/2011 (Annex II itself) — SKIPPED: ~800,000 characters,
      past `MAX_FETCH_CHARS` by four times. The app already holds verbatim
      excerpts; watching the whole thing would spend a model pass on the entire
      annex to notice a typo fix. A user can register it and see the size
      refusal.
- [~] The EUR-Lex web page as a watched address — SKIPPED: it answers Cloud Run
      with `202` and a challenge page. It is not blocked in code — a user can
      register it and will get the exact reason on the row — but nothing ships
      pointed at it.
- [~] BPOM JDIH annexes — SKIPPED: `jdih.pom.go.id` is reachable and serves
      stable PDF URLs (`/download/rule/<id>/<no>/<year>/<title>`), but Perka
      34/2019 Kategori Pangan is 308 pages, past `MAX_DOCUMENT_PAGES`. Verified
      by downloading it. Left to the user with a specific annex.
- [x] A crawler that works out on its own which page a regulator publishes on —
      **built in phase 9 after all**, once the failure mode had a safe shape. It is
      not guessing from a hostname: the model names the regulator and its root, and
      every address below that is read off a page that was actually fetched, so a
      URL it invents cannot be committed. `link_pattern` is still derived in code,
      from real paths. See `plan/phases/phase-9-country-discovery.md`.

## Exit criteria

Everything below was run against the local stack with real network calls to the
real regulator sites on 29 Aug.

- [x] `POST /sources/seed` registers both addresses idempotently.
- [x] First check of the EUR-Lex document returns `changed` with
      `first_read: true` and ingests one document, 48,417 chars.
- [x] That document reaches `extracted` through the ordinary pipeline —
      `origin: watched_source`, stage log `extracting → extracted`, no error.
- [x] Detection reads the document's own title off the fetched page:
      `COMMISSION REGULATION (EU) 2023/2108`.
- [x] Second and third checks return `unchanged` / `same_text` against a site
      whose bytes differ on every request. **This is the load-bearing test.**
- [x] First check of the feed returns `baselined`, 30 entries seen, nothing
      ingested. Second check returns `unchanged` / `no_new_entries`.
- [x] With entry ids removed to simulate a publication, the feed check returns
      `changed` and ingests the new entry as a `news_article`.
- [x] The worker sweep honours each source's interval (`not_due`), and
      `{"force": true}` overrides it. A body-less POST works, because Cloud
      Scheduler may send none.
- [x] A 404 address records `status: error` with a readable sentence, and the
      row renders it.
- [x] A paused source is skipped by the sweep; resuming and deleting work; a
      check against a deleted source is a 404.
- [x] Documents already read from a source survive that source being deleted —
      they are rules that verdicts cite.
- [x] `graph_events` carries `source_added`, `source_updated`, `source_removed`
      with `trace_id` on each.
- [x] `/sources` renders in the browser; "Check now" round-trips and prints the
      outcome in a sentence.
- [x] 369 tests green, ruff clean, `next build` clean.
- [x] Deployed, and the Cloud Scheduler job created against the live worker.
- [x] **The scheduler fired for real and the loop closed.** `gcloud scheduler
      jobs run regulens-source-check` → the worker swept both sources under
      OIDC → the EU regulation was fetched from CELLAR, ingested, extracted by
      Gemini, and **68 clauses** now exist that nobody uploaded. 67 landed in
      the review queue and one went active — the guardrail doing exactly what
      it is for on an unfamiliar annex.
- [x] The next forced check in production returned `unchanged / not_modified`:
      CELLAR's `ETag` means the daily run transfers no body at all.
- [x] **A verdict moved because of a regulation nobody uploaded, 31 Aug.** The
      chain this phase exists for ran end to end in production: Commission
      Regulation (EU) 2023/2108 was found by the scheduler at CELLAR, read into
      88 verbatim limits, and — once the guardrail could tell its rows apart —
      moved `Traditional Cured Beef Sausage` from `attention_required` to
      `non_compliant` in Germany against the 30 mg/kg nitrite row that entered
      into force on 9 October 2025. The alert names the regulation and says
      `unprompted: true`; `/stats/autonomy` counts it, reading
      `verdicts_changed: 2` where it had read `0` since the phase shipped. The
      second is `diet lemon soda`, moved by a BPOM decision from the same sweep.
- [x] The five things standing between "found" and "moved a verdict" are fixed
      and recorded under **Decisions taken** in `../PROGRESS.md`: a name the
      dictionary has since learned, one reason recorded twice, the scope a row
      states in words, the period a row applies for, and a purity ceiling that
      names no food.
- [x] **Discovery proven in production, against the live BPOM portal.** The
      JDIH index baselined at 12 links from Cloud Run. With two of them
      forgotten — standing in for BPOM publishing two things overnight — the
      next check returned `changed`, `new_entries: 2`, and ingested both:
      Keputusan 366/2026 (5,670 chars) and Keputusan 104/2022 (117,180 chars),
      titles read out of the URL path because the index links are icons with no
      text. Both reached `extracted`. Neither address had ever been seen by the
      system. The check after that returned `no_new_entries`.

## Found on the way, and fixed

- [x] **`Cannot send a request, as the client has been closed`.** The first
      scheduled sweep ingested a real regulation and the document then failed
      extraction. Not caused by this phase — the same error is in the logs for
      23 and 28 Aug — but this phase is what made it reproducible, because a
      48,000-character regulation splits into five parts and the ADK path
      emitting nothing for any one of them sends the whole document to the
      direct fallback. `google.genai`'s `BaseApiClient` closes its httpx client
      on garbage collection and guards that with
      `if not self._http_options.httpx_client`; both clients are now handed a
      transport this process owns, so nothing else's collection can shut it.
      Retrying the failed document afterwards took it to `extracted`.

## Not in this phase

Noted here rather than built, so nobody rediscovers them as gaps:

- The seeded EU query is scoped to one EuroVoc concept, *food additive*. A
  regulation about contaminants or packaging materials is outside it and will
  not be found. A deliberate scope, not a bug — unscoped, the query returns
  everything the EU publishes — but the watch list is only as wide as the
  concepts somebody chose.
- A window, not a guarantee, on listings: JDIH's front page shows the twelve
  most recent items, so a regulation published and pushed off that list between
  two checks would be missed. Daily against a portal publishing a few items a
  month has slack to spare; a busier index would need its paginated view.
- A per-source relevance filter. Watching one broad annex put 68 clauses into
  the review queue in a single run, most of them nitrite limits for cured meats
  that no product in the workspace resembles. That is the guardrail behaving
  correctly and it is also a queue nobody will read. The fix is filtering at
  ingestion — by product family, not by confidence — and it is not built.

- A digest of what changed overnight, delivered somewhere a user reads. The
  alerts banner already surfaces the consequences; a per-run summary email or
  Slack post is the obvious next step and is not built.
- Per-source diffs — "these four lines changed" — rather than a new document.
  The citation view already highlights clause spans, so the pieces exist.
- Sub-daily intervals as anything other than a manual override.
