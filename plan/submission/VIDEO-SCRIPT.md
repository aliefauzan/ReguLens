# ReguLens — submission video script

**Target: 4:05.** Rules require ~4 minutes and require the video to prove the
backend runs on Google Cloud, so beat 9 is non-negotiable and gets 35 seconds.

Supersedes the numbers in `../99-demo-script.md`, which still carries the old
0.10% / 0.05% / 0.08% figures from before the corpus was cut into the library.
**The real numbers are mg/kg**, and they are what the deployed app shows:

| | Value | Source |
|---|---|---|
| Product: *Herbal Drink Powder*, sodium benzoate | **300 mg/kg** | `api/app/core/samples.py` |
| BPOM 14.1.4.1 natrium benzoat | **400 mg/kg** | Perka BPOM 11/2019 |
| EU Annex II 14.1.4, E 210–213 | **150 mg/kg** | Reg. (EU) 1129/2011 |

300 is under 400 and over 150. That is the whole demo.

## Before you hit record

- [ ] Run the `seed` Job (or **Try it with sample data**) so the workspace is the
      baseline: product created, BPOM rule ingested and active, Indonesia
      `compliant`, Germany `unknown`.
- [ ] **The EU rule must be un-ingested.** It is the inflection point; if it is
      already in, there is nothing to watch.
- [ ] Browser at 1920×1080, zoom 100%, bookmarks bar hidden, one tab.
- [ ] Second tab pre-opened on the Cloud Run console, signed in, for beat 9 —
      do not record a login.
- [ ] `min-instances=1` is set on api and web, so no cold start on camera.
- [ ] Do one silent dry run end to end. Extraction of the pasted EU excerpt took
      **25.5s** on the deployed stack when last measured. Know that before you
      are live with a microphone on.

Record straight through. Cut, do not re-shoot.

---

## 0 · The problem — 0:00–0:20 (20s)

**On screen:** the two regulation PDFs side by side, EU Annex II row and the BPOM
annex row, both scrolled to the benzoate line.

> "This is a drink powder sold into Germany and Indonesia. Indonesia allows sodium
> benzoate up to 400 milligrams per kilo. The EU allows 150. The product is at 300 —
> legal in one market, illegal in the other. And nobody emails you when either
> number moves."

## 1 · The twin — 0:20–0:40 (20s)

**On screen:** the product page. Ingredients with real amounts, packaging, origin,
both target markets. Indonesia `compliant`, Germany `unknown`.

> "ReguLens keeps a structured model of the actual product, not a document it read.
> Indonesia is compliant — we've ingested the BPOM rule. Germany says unknown,
> because nothing about the EU has entered the graph yet. It says unknown rather
> than guessing."

## 2 · The upload — 0:40–0:55 (15s)

**On screen:** Add rules → paste the EU Annex II 14.1.4 excerpt. Point at the
source-type selector; leave it on **Official Regulation**.

> "How authoritative a source is changes what the system will do with it. An
> official regulation can rewrite state. A forwarded message cannot — it gets
> capped and routed to review."

## 3 · The pipeline, live — 0:55–1:20 (25s)

**On screen:** the stepper advancing Extracting → Extracted → Reconciling. Open the
extracted clause: substance, limit 150, unit mg/kg, jurisdiction, effective date,
confidence. Hover the confidence to show the breakdown.

> "The clause comes out verbatim, with its citation. That confidence isn't the
> model's opinion of itself — it's parse quality, agreement across two independent
> extractions, and the authority tier of the source, in fixed weights."

## 4 · The guardrail — 1:20–1:45 (25s)

**On screen:** the reconciliation panel. The cross-jurisdiction conflict against the
BPOM clause, and the rejected comparisons with the guardrail's stated reason.

> "Before any model sees a pair of clauses, ordinary typed code decides whether
> they may even be compared — same substance, same food category, comparable units.
> These were rejected and it says why. The model is only called on pairs that pass,
> and the model never writes to the database."

## 5 · The flip — 1:45–2:15 (30s)

**On screen:** navigate back to the dashboard. Do not refresh anything by hand. The
alert is already there.

```
⚠  Herbal Drink Powder — Germany
    compliant  →  NON-COMPLIANT
    sodium benzoate 300 mg/kg exceeds EU limit 150 mg/kg
```

Then open the impact chain: regulation → clause → requirement → product → Germany.

> "Nobody queried it. A document arrived, the graph changed, and the system worked
> out on its own which product that broke and in which market. That's the whole
> claim — it acts without being asked."

**This is the money beat. If you fluff a line anywhere, fluff it somewhere else.**

## 6 · The audit trail — 2:15–2:30 (15s)

**On screen:** the timeline, scrolled to the transition event.

> "Every state change is an immutable event written in the same batch as the change
> itself. You can show a regulator exactly when your status moved and which document
> moved it."

## 7 · The question — 2:30–2:50 (20s)

**On screen:** ask *"Why is my product at risk in Germany?"* Let the evidence panel
render; both cited clauses with their source documents.

> "Every clause id in that answer is checked in code against what retrieval actually
> served. An invented citation cites nothing and never reaches the screen. Ask about
> a market it has no data for and it tells you it has no data."

## 8 · It watches on its own — 2:50–3:15 (25s)

**On screen:** the `/sources` page. Four watched addresses, their kinds, their last
check, and the error state on any source that failed.

> "And nothing here required a person. A scheduled sweep re-reads four regulator
> addresses daily — the EU Publications Office catalogue, the Commission's food
> safety feed, BPOM's legal portal. A change means the wording changed, not the
> bytes, so a session id in a response doesn't bill us for a model run. When a
> source finds something new, it enters through exactly the same path that upload
> just took. A source that can't be read says so, in red."

## 9 · Google Cloud proof — 3:15–3:50 (35s)

**Required by the rules. Screen capture, no UI.** Move fast, four windows.

1. **Cloud Run** — `regulens-api`, `regulens-worker`, `regulens-web` all healthy,
   request counts moving from the run you just recorded. Show the `seed` Job listed.
2. **Pub/Sub** — the `document.uploaded` subscription showing delivery, and the
   dead-letter topic sitting empty.
3. **Firestore** — the new clause document, and the requirement's `limit_value`
   showing 150.
4. **Cloud Build** — the green build, SHA-tagged.

> "None of it is mocked. Gemini 3.5 Flash through Vertex AI, four ADK agents, a
> Pub/Sub-driven pipeline across two Cloud Run services with dead-lettering, and
> every state change you just saw is a Firestore document written by a worker.
> One image, deployed by Cloud Build."

## 10 · Close — 3:50–4:05 (15s)

**On screen:** back to the dashboard, alert visible.

> "ReguLens watches the regulators, reconciles what changes against what it already
> knew, and tells an exporter what broke, why, and with what evidence.
> Deterministic code owns every mutation. The model reasons — it never decides."

---

## If something fails mid-take

- **Extraction stalls:** say "we've already run this one — here's the cached
  result" and continue from beat 4. The content-hash cache is real, not a trick.
- **Query is slow:** keep talking over the evidence panel; it renders before the prose.
- **Anything hard-fails:** stop, reseed, start over. A 4-minute take is cheap.

## Do not say

- "Real-time" or "continuous". It is a **daily scheduled re-read**; the floor on
  noticing a change is the check interval. The README says so and a judge may read it.
- Any readiness percentage. There is no denominator.
- "Knowledge graph" without qualification — it is an entity-and-event store in
  Firestore with explicit relations.
- That it evaluates labelling or certification clauses. It extracts them and marks
  them `needs_review`. Numeric limits only.
