# TODO — Inputs Needed Before Coding Starts

**Tick these off in place as you supply them.** `plan/PROGRESS.md` §Blocked on the
user mirrors the critical ones — update both.

Things only you can provide or decide. Everything is grouped by when it blocks.
Anything marked **BLOCKING** stops work at the phase named.

## How to answer

Answer **in place, on the line itself.** Do not start a separate answers file —
one list, one place to look.

- Tick the box and append your answer after an em dash:
  `- [x] **Region choice.** ... — asia-southeast1, Gemini available, verified in console`
- Not decided yet? Leave the box unticked and append `— TODO: <what you still need>`
  so I can tell "unanswered" from "answered no".
- Declining something on purpose? Use `[~]` and append `— SKIPPED: <reason>`.
- A long answer (demo script, product formulation) goes in its own file under
  `plan/inputs/`, and the todo line links to it.

**Never put a secret in this file.** It is committed. For anything secret —
service account keys, API tokens, billing details — put it in `.env.local`
(gitignored) or Secret Manager, and on the todo line write only the *name*, e.g.
`— stored as Secret Manager secret \`regulens-vertex-sa\``.

Anything you cannot answer, say so in chat and I will either find it myself or
tell you what it costs to leave open.

---

## 0 · Do first — could invalidate the whole project

- [x] **BLOCKING (everything): Confirm eligibility.** — confirmed by you on 19 Aug.
      Indonesia not excluded, age requirement met. Unblocks everything.
- [ ] **BLOCKING (submission): Register on Devpost** and join the hackathon.
      Check whether registration closes before the 31 Aug submission deadline.
- [ ] **Confirm you can commit the time.** The plan is 13 working days in a 13-day
      window with zero float. If you have other commitments between 19–31 Aug, say
      so now and we cut scope up front instead of at 2am on the 30th.

---

## 1 · Google Cloud — blocks Phase 0 (Aug 19)

- [x] **BLOCKING: GCP project created with billing enabled.** — project
      `regulens-506014` ("ReguLens"), ACTIVE, **billing enabled** and linked to
      account `01B951-232B54-4E1D9A`. Verified 19 Aug. One project, not two.
- [x] **BLOCKING: Confirm you have Owner or equivalent** on the project — verified
      myself 19 Aug: `afindo.mi01@gmail.com` holds `roles/owner` on
      `regulens-506014`. Enough for service accounts, IAM bindings, Pub/Sub and
      Cloud Run.
- [x] **BLOCKING: Region choice.** — Checked the live publisher-model list on
      19 Aug, and the plan's recommendation does not survive it:

      | Location | Gemini models | Verdict |
      |---|---|---|
      | `asia-southeast1` | **only `gemini-2.5-flash`** | fails the 3.5+ rule |
      | `asia-southeast2` | region not usable on this project (403) | out |
      | `us-central1` | 3.5-flash, 3.6-flash, 3.7-flash, 3.1-pro-preview, … | full |
      | `global` | 3.5-flash, 3.6-flash, 3.7-flash, 3.1-pro-preview, … | full |

      **Chosen split, all three legs smoke-tested:**
      - Infra (Cloud Run, Pub/Sub, Firestore, GCS): **`asia-southeast1`** — keeps
        demo latency low from Indonesia.
      - Gemini: the **`global`** Vertex endpoint. Model calls are remote either way,
        so the region of the compute does not have to match.
      - Embeddings: **`text-multilingual-embedding-002` in `asia-southeast1`** —
        available locally, 768 dims, handles Indonesian. Verified with a real call
        on Indonesian text.
- [x] **BLOCKING: The exact Gemini 3.5+ model identifier** — **`gemini-3.5-flash`**,
      called at
      `projects/regulens-506014/locations/global/publishers/google/models/gemini-3.5-flash`.
      Not guessed: a real `generateContent` call returned `modelVersion:
      gemini-3.5-flash` on 19 Aug. `gemini-3.6-flash` and `gemini-3.7-flash` are
      also available on the same endpoint if we want to trade cost for quality
      later. `aiplatform.googleapis.com` enabled on the project.
- [x] **Budget cap.** How much are you willing to spend on Vertex AI across 13 days?
      Rough estimate for this plan: **$30–80** with the two-sample extraction and
      repeated demo rehearsals. Tell me the number and I set the alert thresholds.
      — **$30. Budget created and live** on 19 Aug: "ReguLens hackathon cap",
      scoped to project `regulens-506014` only, monthly, alerts at **50 / 90 /
      100%**.

      Note: your billing account is denominated in **IDR**, not USD — the API
      rejected a USD amount. The cap is set to **Rp 540,000**, which is $30 at the
      19 Aug rate of ~17,830 IDR/USD, with a little headroom so a rate move does not
      quietly shrink the cap below $30. If the rupiah swings hard, the dollar value
      of this cap drifts; say the word and I re-peg it.

      Heads up: you already had a budget named "budget" on the same billing account
      — **Rp 100,000/month (~$5.60), account-wide, no project filter**. It will start
      firing well before the ReguLens cap does, and it covers your other projects
      too. I left it alone. Raise it or scope it if the noise gets annoying.
      Neither budget blocks spend — budgets alert, they do not cap.
- [x] Confirm Vertex AI quota is not zero on a fresh project — not zero. A live
      `generateContent` call and a live embedding call both succeeded on 19 Aug
      (`trafficType: ON_DEMAND`). No quota request needed.
- [x] Billing account linked and has a working payment method — `01B951-232B54-4E1D9A`
      ("My Billing Account"), linked by you on 19 Aug and confirmed by
      `gcloud billing projects describe`. **Real charges land on this account**, so
      the budget alert below is worth setting.

---

## 2 · Accounts & access — blocks Phase 0

- [x] **GitHub repository** — `aliefauzan/ReguLens`, verified 19 Aug via the GitHub
      API: exists, **public**, default branch `master`. Judges can see it; no access
      grant needed.
- [ ] **Vercel account** connected to that repo. — TODO: you said later. Not needed
      until the frontend deploys in Phase 1; flag if it slips past Aug 21.
- [x] `gcloud` CLI installed and authenticated locally — verified 19 Aug: logged in
      as `afindo.mi01@gmail.com`, ADC file present. Note the active project is
      `tugasakhiraf`, not `regulens-506014`; scripts must pass `--project`
      explicitly rather than rely on the default.
- [ ] Docker Desktop installed and running (the local stack is Compose-based).
      — Docker 29.2.1 installed, daemon not running. **Deferred by you on 19 Aug**
      ("docker can do later"). Start Docker Desktop before the Phase 0 local-stack
      task; nothing before that needs it.
- [~] Node 20+ and Python 3.12 locally. — Node v24.14.0 ✓. Python is **3.14.3**.
      SKIPPED: you judged 3.14 fine on 19 Aug, so no local downgrade. I still pin
      the **containers** to Python 3.12 — that costs you nothing and keeps the
      deployed runtime on the version ADK and the GCP client libraries are tested
      against. If a dependency refuses to install locally on 3.14, that is the
      symptom to expect, and a 3.12 venv is the fix.
- [x] **Where should alerts go?** — `afindo.mi01@gmail.com`. Cloud Monitoring email
      notification channel created 19 Aug:
      `projects/regulens-506014/notificationChannels/7686068825666649291`
      (display name "af gmail"). Already wired to the budget; the five Phase 0
      alerts reuse the same channel. **Check your inbox for the Google verification
      mail and confirm it** — an unverified channel silently drops alerts.

---

## 3 · Content — BLOCKING Phase 2 (Aug 22). Start collecting now.

This is the item most likely to be late, and it cannot be faked without
undermining the whole submission.

- [x] **Real EU regulation document** covering sodium benzoate limits in food or
      beverage products. Downloaded from EUR-Lex to `data/regulations/eu/`:
      Regulation (EC) 1333/2008 (original + consolidated 2026-02-18 and
      2026-08-18) and Commission Regulation (EU) 1129/2011 (Annex II Union list).
      Text layers verified.
- [x] **Real Indonesian BPOM regulation** covering the same substance — Peraturan
      BPOM No. 11 Tahun 2019 tentang Bahan Tambahan Pangan, 1156 pages, from the
      official JDIH BPOM site. In `data/regulations/bpom/`. Text layer verified.
- [ ] **3–5 additional regulatory documents** for the extraction fixture set —
      variety matters more than volume (different layouts, one in Indonesian, one
      in English).
- [x] **Confirm the limits are actually different** — they are. Flavoured drinks:
      EU Annex II 14.1.4 sets E 210-213 at **150 mg/kg**; BPOM 14.1.4.x sets
      **400–900 mg/kg** as benzoic acid. Still to do: confirm the exact BPOM
      row-to-limit pairing against the rendered table, not the text dump.
- [ ] **A realistic "messy source" text** — a paragraph in the style of a forwarded
      WhatsApp announcement or an association post. This one may be synthetic, and
      the UI will label it as such.
- [ ] **Decide the demo product.** The plan assumes Herbal Drink Powder with ginger,
      turmeric, honey powder, sodium benzoate 0.08%. Confirm or replace — and if you
      replace it, the ingredient must be one with a real regulatory divergence.

> If real documents are hard to obtain, tell me early. The fallback is clearly
> labelled synthetic documents, which costs credibility with judges but is far
> better than presenting invented numbers as real.

---

## 4 · Product decisions — needed by Phase 1 (Aug 21)

- [ ] **Markets:** plan assumes Germany (EU) and Indonesia (BPOM). Confirm, or name
      different ones. Two markets is the MVP ceiling.
- [ ] **Readiness display:** the plan recommends issue counts ("3 issues — 1
      critical") over a percentage, because we only truly evaluate numeric limits
      and a percentage implies coverage we do not have. Do you accept that, or do
      you want a percentage for the visual? *My recommendation: counts.*
- [ ] **Language of the UI** — English, Indonesian, or bilingual? Bilingual costs
      roughly half a day and there is no float for it. *My recommendation: English
      UI, Indonesian source documents — it shows multilingual extraction without
      the i18n work.*
- [ ] **Product name confirmed as "ReguLens"** and any logo/wordmark you want used.

---

## 5 · Design — needed by Phase 1, nice to have earlier

- [ ] Any brand colours, or do I pick a neutral palette? *Default if you say
      nothing: shadcn defaults with a single accent colour.*
- [ ] Any existing mockups, Figma file, or reference product you want the UI to
      resemble. If none, I build straight from the concept document's UI sketches.
- [ ] Confirm: desktop-only is acceptable. Mobile responsiveness is out of scope
      and the plan does not budget for it.

---

## 6 · Submission assets — needed by Phase 7 (Aug 31), prepare earlier

- [ ] **Screen recording tool** installed and tested (OBS, or macOS built-in).
- [ ] **Do you narrate the video yourself, or use captions?** Narration is stronger
      but needs a quiet room and a couple of takes. Decide before Aug 30.
- [ ] Devpost profile filled in — name, photo, bio.
- [ ] Decide whether you are writing the optional bonus blog post. ~1 hour, do it
      while builds run.

---

## 7 · Decisions I need from you before I start writing code

These are already recommended in the plan; I need a yes or a change.

| # | Decision | My recommendation |
|---|---|---|
| 1 | Cut **Gemma** now? | **Yes — cut it.** Optional bonus, nothing depends on it, buys ~0.5 day of the float the schedule does not have. Mention it as future work. |
| 2 | Cut **OCR fallback** now? | **Yes — cut it.** Requires text-layer PDFs, which you are choosing anyway. Buys ~0.25 day and removes the flakiest code path. |
| 3 | Readiness as counts or percentage? | **Counts.** |
| 4 | One GCP project or two? | **Two** if billing allows; one is workable. |
| 5 | Repo public or private? | **Public.** Judges see the code, and the architecture is a strength here. |
| 6 | UI language | **English.** |

---

## Not needed from you

For clarity, I do **not** need: API keys for Vertex (service account handles it),
a domain name (Vercel and Cloud Run URLs are fine), a database schema (defined in
`plan/02-data-model.md`), or any auth credentials (there is no auth in the MVP).

---

## Fastest path to unblocking me

If you only do three things tonight:

1. Confirm eligibility and register on Devpost.
2. Create the GCP project with billing, and tell me the project ID and region.
3. Start downloading the EU and BPOM regulation PDFs.

Those three unblock Phase 0 tomorrow morning and de-risk Phase 2. Everything else
in this list can arrive a day or two later without stalling the build.
