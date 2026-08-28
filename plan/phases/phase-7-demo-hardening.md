# Phase 7 — Demo Hardening & Submission

**Estimate:** 1 day (Aug 31) — includes the submission itself
**Demo sentence:** "Run one command, get the exact same demo, every time."

**Status:** `IN PROGRESS` · **Started:** 26 Aug 2026 · **Completed:** —

<!-- MAINTAIN THIS FILE.
     Set Status to IN PROGRESS when you begin, COMPLETE when every exit criterion
     is ticked. Fill the dates. Tick each `- [ ]` as it lands — a ticked box means
     it exists in the repo and is deployed, not that it is written down somewhere.
     If you deliberately skip an item, change it to `- [~]` and add ` — SKIPPED:
     reason` on the same line so nobody re-litigates it later.
     Then update ../PROGRESS.md. -->

## Goal

Make the demo reproducible, resettable, survivable, and recorded. A working system
that fails once on stage scores worse than a smaller system that never does.

## Scope

### Reproducible state
- [ ] **Cloud Run Job** `seed` that wipes the demo workspace and rebuilds the
      baseline. A Job is the right home for this: batch, no HTTP, re-runnable from
      the console mid-demo. `POST /admin/seed` triggers it for convenience.
- [ ] Second Job mode `reprocess`: re-run extraction over stored documents after a
      prompt change, without re-uploading. This saves real time during the last
      two days.
- [ ] The baseline:
      markets seeded, demo product created, BPOM 0.10% clause ingested and active,
      Indonesia evaluating `compliant`, Germany `unknown` or `compliant` per the
      chosen narrative.
- [ ] The EU 0.05% document stays **un-ingested** — that upload is the demo's
      inflection point.
- [ ] Seeding is idempotent and takes under 30 seconds.
- [ ] Fixture documents committed to the repo so seeding needs no network fetch of
      third-party files.

### First-run self-service (added 26 Aug)

The plan's "Out of scope" line below says *onboarding flows*. That was written
assuming the demo is always driven by us. It is not: a judge opens the hosted URL
cold, with no product, no regulation PDF, and nobody to ask. Two hours of
onboarding is cheaper than a judge who reaches an empty page and leaves. Scope is
deliberately minimal — no tour, no coach marks, no modal.

Verified on the local docker-compose stack. **Not yet redeployed to Cloud Run.**

- [x] `GET /samples` — regulation excerpts bundled in the image (`app/core/samples.py`),
      quoted verbatim from the corpus with their citations. Needed because only
      `app/` is copied into the container, so `data/regulations/` is not there.
- [x] `POST /demo/seed` — creates the demo product and ingests the BPOM rule
      **through the normal async path** (Pub/Sub → worker), so the button exercises
      the real pipeline rather than writing state directly. Returns 202 while
      extraction runs, 200 when an identical seed already exists.
- [x] Seeding idempotent twice over: product matched by name, document by content
      hash. Pressed twice → same product id, same document id, one product.
- [x] The EU rule stays un-ingested by the seed, so the inflection point is still
      the user's own upload — now available as a one-click sample.
- [x] Home page: "Try it with sample data" on an empty workspace, landing on the
      document page while extraction runs (landing on the product would show
      "no rules added yet" and read as a broken button).
- [x] Add-rules page: sample picker fills the form (source type, publisher,
      jurisdiction, text) and the user still presses the button.
- [x] Three-step checklist persists until all three steps are genuinely done,
      computed from real state — a product exists, a document reached `extracted`,
      a market reads something other than `unknown`. It previously vanished the
      moment the first product existed, taking step two with it.
- [x] `tests/test_samples.py` — nine tests pinning the thing the samples claim:
      EU excerpt yields 150, BPOM yields 400, the two disagree, the demo product's
      300 mg/kg sits between them, and every demo ingredient normalizes.
- [x] Redeploy api + web to Cloud Run so the hosted URL has the seed button — done 29 Aug.

### Self-service, round two (28 Aug)

Same question as the first round — what still needs a person standing next to
the user — answered for the seven things left. Local stack only; **Cloud Run
redeploy still pending**.

- [x] **Honest waiting.** The upload button said "about a minute" against a
      measured 183s. Both places now say three minutes, and the document page
      carries a live clock against that estimate plus a distinct
      "taking longer than usual" state past five minutes.
- [x] **Correct a product.** `ProductForm` serves both create and edit;
      `/products/{id}/edit` uses the existing `PATCH /products/{id}`, which had
      no caller. Editing opens on the ingredient rows, not the paste box.
- [x] **Delete a product.** `DELETE /products/{id}` plus `delete_with_event` in
      the repository, so the cascade over derived requirements and the
      `product_deleted` event are written in one batch. Confirmation names what
      goes.
- [x] **Reject a clause.** `POST /clauses/{id}/dismiss` and a second button in
      the review queue. `dismissed` is terminal and inert; the record and its
      event survive.
- [x] **A number to act on.** A failing requirement now says what to bring the
      amount down to, and names the stricter market when meeting one meets both.
- [x] **Counts on the navigation bar**, refreshed on navigation and on any queue
      action. Phone keeps four tabs — five labels do not fit.
- [x] **`/rules`** — every clause in one list with why each does or does not
      count. Previously a clause was only visible inside its own document.
- [x] **Glossary** (`_ui/Term.tsx`) for jurisdiction, clause, authority,
      confidence, supersede, conflict, requirement.
- [x] Ask suggestions built from the product's own markets and failing market.
- [x] Missing ingredient amounts link to the edit form; "1 ingredients" fixed.

Three real defects surfaced by building these, all fixed here:

- [x] **A corrected amount never reached the requirement row.** The idempotency
      check compared only `{limit_value, evaluation, severity, clause_id}`, so
      an edit that did not flip the verdict wrote nothing and the page kept
      quoting the old amount under the new limit. Now compares every field the
      UI shows (`REPORTED_FIELDS`), with `tests/test_requirement_change.py`
      pinning it — including a test that every reported field is watched, which
      is what would have caught both this and the earlier `product_value` bug.
- [x] **`confirm_clause` never republished.** `_publish_graph_changed` ran on
      the `None` branch, which was the *failure* path, so accepting a clause in
      the review queue promoted it and then did not re-evaluate anything. Both
      confirm and dismiss now return explicit outcomes, and a missing clause is
      a 404 instead of a cheerful 200.
- [x] **Alerts outlived their product.** `GET /alerts` filtered nothing, so a
      deleted product left an alert linking to a 404. Events stay in the audit
      trail; they are no longer presented as needing attention.

### Plain-language pass (28 Aug)

A walk through every page as somebody who does not work here. Nine things were
confusing enough to stop a reader; all fixed, all rechecked in the browser at
phone width in both themes.

- [x] **"Where this came from" showed a bare `clause_2da66be9e735`** on four
      pages — the one thing a reader cannot use, shown exactly when they are
      deciding whether to trust the number above it. One `_ui/Provenance.tsx`
      now names the document, the country, and links to it; the id survives one
      line down, labelled as a reference for quoting to us.
- [x] **The review queue never said why anything was waiting.** The UI read
      `review_reasons` (a list the extractor writes) while the guardrail writes
      a single `review_reason`, so every card showed an empty bullet list. Both
      are read now, `low_confidence_or_flagged` has words, and each card says
      what it was read from and how sure we are.
- [x] **Answers quoted clause ids inline.** That is the grounding contract — the
      model must cite `[clause_id]` and an uncited answer is refused — but it
      reads as noise. Ids are renumbered against the citation cards, so the
      grounding is unchanged and the sentence is readable. "answered in 19 ms"
      became "answered straight away".
- [x] **404 was the Next.js default** with no way back. Now says what happened,
      says the data is fine, and offers two doors.
- [x] **The document page was titled "Reading your document" over a raw id**,
      even long after it finished. Titled with the document's own name now, and
      the copy changes once reading is done.
- [x] **A document could say "Finished" over a rule nobody had accepted.** Each
      rule found now carries its standing (in use / waiting for you / replaced /
      ignored), and the finished panel says how many still need a person, with
      a link to the queue.
- [x] **History was unreadable**: no dates, a raw trace-id fragment on every
      row, and rows reading "No rules added yet → No rules added yet" (a real
      `null → unknown` difference in the data, the identical sentence on
      screen). Filtered on the rendered label, timestamps in plain words, trace
      fragment gone.
- [x] **Server validation spoke schema.** "Input should be 'percent_w_w',
      'mg_per_kg' or 'ppm'" became "Pick one of these for the unit on row 2:
      % of weight, mg per kg, ppm" (`humanizeValidation`).
- [x] **Smaller ones:** requirement rows sorted worst-first (a labelling note
      sat above the ingredient that actually failed); a waiting rule on `/rules`
      now has a button to act on it; generated `doc_x.txt` filenames read as
      "pasted text".
- [x] The local canned answer picked whichever clause came back first, so
      "why does this break the rules in Germany?" was answered with Indonesia's
      limit. `_fake_pick` now matches the country in the question, then any
      failing rule. Two tests pin it. FAKE_LLM never runs in production, but it
      is the whole of what anyone evaluating the local stack reads.

### Second recheck (28 Aug)

A sweep of every route for machine vocabulary — a script reading each rendered
page for ids, `snake_case`, `null`, and millisecond readouts. What it found:

- [x] **A document with no usable rules never finished.** `completedStages`
      read an empty clause list as "not settled yet", so the stepper span on
      stage three of four forever for anyone who uploaded something that turned
      out not to be a regulation. That is an ordinary mistake, not a failure,
      and the page now says so — and stops printing "Rules found" and
      "Everything we found is listed below" over an empty list.
- [x] `dismissed`, `pending_reconciliation` and the three evaluation reasons
      added to the one vocabulary map, so nothing falls through to
      `snake case with the underscores swapped for spaces`.
- [x] Sweep now comes back clean: the only ids left on any page are the ones
      inside a collapsed "Where this came from", labelled as the reference to
      quote to us.

### The upload form stops interrogating people (28 Aug)

Step two of the checklist read "Add the rules that apply" and then asked, before
it would accept anything: what authority tier is this, whose jurisdiction is it,
who published it, when does it take effect. Four questions a person with a PDF
cannot answer without knowing our data model. The document itself answers all
four. Local stack only; **Cloud Run redeploy still pending**.

- [x] `app/core/detection.py` — deterministic reading of jurisdiction, source
      type, publisher/title and effective date from the document's own words.
      Keyword weights and date patterns, no model call: upload stays fast, and a
      wrong guess here would change what a clause is allowed to do. Each answer
      carries a confidence **and the phrase it was read from**.
- [x] Uncertainty is a first-class answer. Scores are separated, not summed:
      a document naming both regulators comes back unsure rather than
      confidently wrong. On a tie the *lower* authority wins, so a forwarded
      screenshot quoting BPOM reads as a chat message, not as the regulation.
- [x] A date is only claimed when the document ties it to taking effect
      ("shall apply from", "mulai berlaku"). Adoption and signature dates are
      left alone — picking one would be a confident lie.
- [x] `POST /documents/detect` — reads a file or pasted text and stores nothing.
      A user who changes their mind after seeing what we read leaves no document
      and no file behind.
- [x] `POST /documents` metadata is now optional; whatever the caller omits is
      read from the document. Only an unreadable jurisdiction or source type is
      refused, in words that say what to do about it. The existing verify script,
      which still sends every field, is unaffected.
- [x] The document record keeps the detection and a `declared_fields` list, so
      "who said this was EU" has an answer on the record. The document page says
      "You did not have to tell us the country: the document says «…»" when
      nobody typed it in.
- [x] Upload form rewritten: the document comes first, we read it on file-select
      or on a pause in typing, and we show what we read with the quote it came
      from. The five-way authority picker and the three fields only appear when
      we could not read them, or when the user presses "Something is wrong".
- [x] `tests/test_detection.py` (16) and `tests/test_detect_endpoint.py` (3) —
      both bundled samples, a forwarded chat message, a news report, a circular,
      dates in two languages and three formats, a date with no effect wording, an
      unattributed limit, and a document pulling both ways.
- [x] Rechecked against the corpus on the local stack: both excerpts and the
      1333/2008 PDF read correctly with no input; a metadata-free upload of the
      EU excerpt went through the pipeline to `extracted`.
- [x] Redeploy api + web to Cloud Run — done 29 Aug, revision `e2e-014324`.

### The app stops asking for a regulation it already has (28 Aug)

"Why do I have to add a regulation?" — because we shipped an empty rulebook and
sent the user to find a PDF, which is the job they came here to avoid. Two real
regulations are in the repo; now the app offers them. Local stack only; **Cloud
Run redeploy still pending**.

- [x] `scripts/build_library.py` slices the corpus into 28 verbatim excerpts —
      12 EU Annex II food categories and 16 BPOM additive sections — each with
      its citation, in `app/core/library_data.json`. Nothing is paraphrased,
      summarised or re-numbered.
- [x] The EU side is built from the **EUR-Lex HTML** of the consolidated
      1333/2008 (fetched 28 Aug, kept in `data/regulations/eu/*.eurlex.md`),
      not the PDF: a text dump of the PDF unaligns the table columns, and an
      unaligned row pairs a category with the wrong number. The BPOM side uses
      `pdfplumber`, which keeps each annex row on one line — which resolves the
      row-alignment caveat standing in `SOURCES.md` since 19 Aug.
- [x] `GET /library` and `POST /library/load` — load the starter set (8 rules,
      both markets, drinks/powders/supplements) or any subset. Ingestion goes
      through the ordinary upload path: same hash, same Pub/Sub message, same
      extraction, same guardrail. No back door writes clauses.
- [x] "Load the starter rules" on the home checklist, on the product page's
      empty state, and on the add-rules page, which now leads with the rulebook
      and offers "read your own document" underneath. The old two-sample filler
      is gone — the library covers it and does not ask the user to paste.
- [x] **A real defect this exposed: rules bound to products they do not cover.**
      `materialize_for_product` matched on jurisdiction and substance only, so
      once the library was loaded a drink powder was failed against the benzoate
      limit for *dairy desserts*. Numeric limits now bind only when the clause's
      product type is comparable with the product's — same type, or the
      documented powder/liquid family, or an unstated one. Without this, more
      data made the app confidently wrong.
- [x] The substance dictionary grew from 21 to 45 entries (sweeteners, colours,
      antioxidants, nitrites, sulphites), each checked against the E number in
      the EU row and the INS number in the BPOM heading. A limit for a substance
      the dictionary cannot match is a limit nobody is compared against — which
      on screen looks exactly like passing.
- [x] `FAKE_LLM` reads the excerpt's own table instead of answering every
      document with the same canned pair. Twenty-eight rules that all said 150
      and 400 would have disagreed with themselves on the local stack.
- [x] Documents record their `origin` (upload / library / demo), so a rulebook
      entry reads "from the built-in rules" instead of "pasted text".
- [x] 45 new tests (`tests/test_library.py`, plus guardrail and sample updates):
      every entry ingestable and cited, the starter set covering the demo
      product, the EU/BPOM benzoate divergence still real, and a rule for one
      kind of food refusing to bind another.
- [x] Verified on a wiped local stack: seed + load starter set → 9 documents,
      200 clauses, 8 conflicts, Germany `non_compliant` (150 mg/kg) and
      Indonesia `compliant` (400 mg/kg) for the same product. `verify_local.sh`
      still passes end to end.
- [x] Redeploy api + web to Cloud Run — done 29 Aug, revision `e2e-014324`.
- [ ] Watch the first live extraction of a library entry: 28 entries is 28 real
      Gemini runs if someone loads everything one at a time.

### Citations you can check, and names we understand (29 Aug)

Three things the rulebook made necessary. Local stack only; **Cloud Run redeploy
still pending**.

- [x] **"Where this came from" now shows the passage.** `POST /documents/{id}/text`
      returns the document's own words with every clause located inside them,
      and the document page renders it with each cited passage highlighted.
      A rule links to `?cite=<clause_id>`, which opens the reader scrolled to
      its sentence. `core/citations.py` reports `exact`, `approximate` or
      `not_found` — a clause we cannot locate is listed as unlocated rather
      than pointed at the nearest paragraph, because a citation is only worth
      something if the reader can trust where it points.
- [x] Extracted PDF text is now persisted (capped at 200k characters, the cut
      recorded) so the reader has something to show. Documents read before this
      say so instead of showing a 500-character stump as if it were the whole.
- [x] The offline reader quotes the document verbatim again — it had been
      prefixing the substance onto the row, which made its own clauses
      unfindable in their own document. 328 of 328 citations across the loaded
      rulebook now resolve `exact`.
- [x] **A market shows one card per ingredient, not six.** With the rulebook
      loaded, a market holds several limits for the same substance — the
      flavoured-drink row, the juice row, the concentrate row. The strictest (or
      the failing one) leads and names its rule ("From EU Annex II — 14.1.4
      Flavoured drinks"); the rest collapse into "N more limits for this
      ingredient here", each linking to its own passage. Nothing is hidden.
- [x] **A real defect in the remediation line:** it compared a market against
      itself, so a German rule could read "Germany is stricter still at 150".
      The target is now the strictest limit *in this market* — meeting the one
      on screen could still leave you failing another — and only other markets
      can be "stricter still".
- [x] **`GET /substances/resolve` — what a user meant by an ingredient name.**
      The strict matcher is right to refuse to guess, but the cost of that is a
      row matching nothing, which reads exactly like a pass. The resolver
      answers the "no" cases: a misspelling offers the name back ("sodium
      benzoat" → sodium benzoate), an E or INS number in any spelling resolves,
      a food says it is a food ("meat", "daging ayam" — normal, and *not* a
      pass), a function word asks for the substance ("preservative" says which
      one), and a genuinely unknown name says plainly that nothing will be
      checked against it. Foods the dictionary already knew (ginger, turmeric,
      sucrose) are labelled foods too — telling someone their ginger "will be
      checked" invents a rule that does not exist.
- [x] Every ingredient row runs it on a pause in typing and says what it made of
      the name; suggestions are offered as buttons and never applied on their
      own.
- [x] 29 new tests (`test_citations.py`, `test_substances.py`), 252 green.
      Verified live: 328/328 exact citations, the deep link opening the reader
      on the right row, and paste → "meat" / "sodium benzoat" / "preservative"
      each answered correctly with one click to fix the misspelling.
- [x] Redeploy api + web to Cloud Run — done 29 Aug, revision `e2e-014324`.

### Deployed end-to-end run (29 Aug)

Everything above was local until now. Deployed on the real stack — Cloud Build →
Cloud Run, `FAKE_LLM=false`, real Gemini — and exercised live. Revision
`e2e-014324`.

- [x] Cloud Build green end to end: lint, 257 tests, image, api + worker + job +
      web deployed. Four builds: the first failed on lint (a stray duplicate of
      the library builder inside `api/`, now removed), the rest on purpose.
- [x] Detection on a real PDF through the deployed API: EU, official regulation,
      title read off the masthead, `needs_confirmation` false.
- [x] Upload with **no metadata at all** → 202, auto-detected EU, extracted with
      real Gemini: 6 pages, 34 clauses, full text persisted.
- [x] Library load through the deployed API: 28 entries listed, three loaded,
      real Gemini returned 59 / 45 / 15 clauses with units read from the table
      headers and product types per category.
- [x] Citations against real model output: 149 of 151 clauses located on every
      document ingested since the text started being stored (98.7%). The one
      document at 0% predates that change and says so in the UI rather than
      showing a stump.
- [x] Grounded Ask, live: an answer that names the failing limit and cites the
      clause it came from, `refusal: false`, confidence 0.9997, ~4 s.
- [x] Upload cache: identical bytes → 200, same document id, no re-extraction.
- [x] Redelivery: republished `document.uploaded` for an extracted document →
      clause count unchanged (34 → 34).
- [x] Web on Cloud Run: every route 200, the rulebook renders, the citation
      reader highlights 45 passages and opens on the one the link asked for, and
      the ingredient checker answers "meat" and "sodium benzoat" correctly.
- [x] CORS fixed: Cloud Run answers on two hostnames and only one was allowed,
      so the site was dead for anyone who opened the other link.

Three real defects the deployed run exposed, all fixed:

- [x] **The `gemini-api-key` secret held the literal placeholder `YOUR_KEY_HERE`.**
      Any non-empty value flipped every call to the Gemini Developer API, which
      answered "API key not valid" — and the damage was quiet: embeddings failed
      one clause at a time, similarity search degraded to nothing, and Ask
      answered "no regulation covers this" while holding the regulation. A
      placeholder now counts as no key, so the stack falls back to Vertex and
      the misconfiguration costs money instead of correctness. **Put a real key
      in the secret to switch back to the free tier, then re-embed.**
- [x] **151 clauses had no embedding** from that window. `scripts/reembed.py`
      backfilled them against the deployed Firestore (151 re-embedded, 51
      already current, 0 failed) and Ask started answering.
- [x] **`mg/kg or mg/l` was rejected as an unusable unit** while `mg/l or mg/kg`
      was accepted — the same header written the other way round, sending real
      limits to review. Also stopped flagging a units problem on rows that carry
      no number at all ("quantum satis"): the clause still needs review, but for
      a reason that is true.

Known and not defects:

- 110 clauses sit in review as `substance_not_recognized`. The annexes name far
  more additives than the 45-entry dictionary knows, and an unmatched substance
  is deliberately parked rather than guessed at. Growing the dictionary from the
  corpus is the obvious next step.
- One clause has been stuck in `pending_reconciliation` since 23 Aug — a message
  lost before this session. It predates every change here.

### Failure survival
- [ ] Every async stage has a timeout and a visible failure state in the stepper.
- [ ] Confirm the five alerts from `../04-observability.md` are firing correctly by
      triggering each one deliberately. An alert you have never seen fire is not an
      alert.
- [ ] Confirm the Cloud Build rollback command works — practise it once.
- [ ] Retry button on failed documents, tested by forcing a failure.
- [ ] If Vertex AI is unreachable, the API returns a clear error and the UI says so
      — no infinite spinner, no silent empty state.
- [ ] Pre-warm endpoint or a scheduled ping so the demo never hits a cold start.
- [ ] Extraction cache verified: re-uploading the demo PDF during rehearsal must
      not re-bill or change results.

### Honesty pass
- [ ] Audit every screen for implied capability the system does not have:
      no fake percentages, no invented regulation text, no "monitoring" language for
      things that only run on upload.
- [ ] Any synthetic fixture document is labelled synthetic in the UI.
- [ ] `needs_review` states are visibly distinct from `pass` — this is a feature to
      show off, not a blemish to hide.

### Presentation polish (time-boxed, half a day maximum)
- [ ] Consistent status colour language across readiness, alerts, and timeline.
- [ ] The impact chain visual and the before/after diff get the most attention —
      they carry the pitch.
- [ ] Loading states everywhere something takes over 300ms.
- [ ] Mobile is *not* a goal; make sure it does not crash, then stop.

### Recording and fallback
- [ ] Full demo recorded end to end, unedited, as a fallback for live failure
      (footage captured in phase 6).
- [ ] Screenshots of the six key screens for the submission.
- [ ] Demo run timed; confirm the < 90s propagation target from the PRD.

### Submission package (see `../03-hackathon-compliance.md`)
- [ ] **README with reproducible spin-up instructions** — explicitly required by the
      rules. Prerequisites, env vars, `gcloud` setup, one command local, one command
      deploy. Have someone else follow it cold.
- [ ] **Architecture diagram as an image** — required. Render the topology from
      `01-architecture.md`. ASCII in a README does not satisfy this.
- [ ] **~4-minute demo video that proves the backend runs on Google Cloud.** Not
      only the UI. Budget ~40 seconds to show the Cloud Run services, a Pub/Sub
      subscription delivering, and Firestore documents changing live. Compress
      `../99-demo-script.md` from 3m30s to ~3m10s to make room.
- [ ] Text description: features, technologies, **data sources** (name the actual
      regulations used), and learnings.
- [ ] Hosted URL live and verified from a browser that has never seen it.
- [ ] Repo pushed; if private, confirm judge access.
- [ ] Devpost submission form completed and **submitted at least 12 hours early**.
      Upload failures at a deadline are ordinary, not unlucky.
- [ ] Optional bonus: short blog or social post on the "deterministic code gates the
      model" principle. Write it while a build or render is running.

### Documentation
- [ ] Root `README.md` also carries an explicit **Limitations** section listing what
      is out of scope. Stating limits raises credibility rather than lowering it.
- [ ] Include the "what we did not build" table from `01-architecture.md` — under a
      30%-weighted Architectural Discipline criterion, documented restraint is
      scoreable work, not an apology.

## Exit criteria

- [ ] `seed` Job → run the full demo → `seed` again → identical starting state.
- [ ] The demo has been performed end to end, live, three times without intervention.
- [ ] The 4-minute video is recorded, includes the Google Cloud proof segment, and is
      uploaded.
- [ ] Architecture diagram image exists and matches what was actually built.
- [ ] A third party can follow the README spin-up instructions successfully.
- [ ] Every row in `../03-hackathon-compliance.md` is checked off.
      The phase-6 suite is still green against the final deployed build.
- [ ] Devpost submission is complete, ≥ 12 hours before 31 Aug 5:00pm PDT.
- [ ] Budget/quota headroom confirmed.

## Out of scope

Load testing, monitoring dashboards, error tracking integration, analytics,
marketing site. *Onboarding flows were out of scope until 26 Aug; see "First-run
self-service" above for why the minimal case came back in.*

## Risk notes

- Do not start new features in this phase. The most common phase-6 failure is
  "just one more thing" breaking a working demo the night before.
- Rehearse on the deployed environment, not locally. Local success proves nothing
  about the URL a judge will open.
- The video is the artifact most teams underestimate. A 4-minute video takes far
  longer than 4 minutes to produce. **Record the raw footage during phase 6** while
  the E2E runs are green; Aug 31 is for editing, not for discovering a broken take.
- This phase has **zero schedule slack** (see `../README.md`). If phase 5 overruns,
  cut phase 5 scope, not phase 6 — an unsubmitted project scores nothing.
