# TODO — Inputs Needed Before Coding Starts

**Tick these off in place as you supply them.** `plan/PROGRESS.md` §Blocked on the
user mirrors the critical ones — update both.

Things only you can provide or decide. Everything is grouped by when it blocks.
Anything marked **BLOCKING** stops work at the phase named.

---

## 0 · Do first — could invalidate the whole project

- [ ] **BLOCKING (everything): Confirm eligibility.** Read the official Devpost
      rules and check Indonesia is not on the excluded countries/territories list.
      Also confirm the age-of-majority requirement and whether you are entering as
      an individual or a team. If this fails, stop — nothing else matters.
- [ ] **BLOCKING (submission): Register on Devpost** and join the hackathon.
      Check whether registration closes before the 31 Aug submission deadline.
- [ ] **Confirm you can commit the time.** The plan is 13 working days in a 13-day
      window with zero float. If you have other commitments between 19–31 Aug, say
      so now and we cut scope up front instead of at 2am on the 30th.

---

## 1 · Google Cloud — blocks Phase 0 (Aug 19)

- [ ] **BLOCKING: GCP project created with billing enabled.** Give me the project
      ID. Two projects is ideal (`regulens-dev`, `regulens-demo`); one is
      acceptable if billing is tight.
- [ ] **BLOCKING: Confirm you have Owner or equivalent** on the project — the setup
      script creates service accounts, IAM bindings, Pub/Sub topics, and Cloud Run
      services. Editor is not enough for the IAM parts.
- [ ] **BLOCKING: Region choice.** Recommend `asia-southeast1` (Singapore) for
      latency from Indonesia — but **verify Gemini 3.5+ and Vertex embeddings are
      available there**. If not, `us-central1` has the widest model availability.
      This decision is hard to reverse later.
- [ ] **BLOCKING: The exact Gemini 3.5+ model identifier** available to your project
      in that region. Check the Vertex AI console — do not guess a model string.
      The rules require 3.5 or newer.
- [ ] **Budget cap.** How much are you willing to spend on Vertex AI across 13 days?
      Rough estimate for this plan: **$30–80** with the two-sample extraction and
      repeated demo rehearsals. Tell me the number and I set the alert thresholds.
- [ ] Confirm Vertex AI quota is not zero on a fresh project — new projects
      sometimes need a quota request, which takes days.
- [ ] Billing account has a payment method that will not fail mid-hackathon.

---

## 2 · Accounts & access — blocks Phase 0

- [ ] **GitHub repository** — create it, tell me public or private. If private,
      confirm how judges will be granted access.
- [ ] **Vercel account** connected to that repo.
- [ ] `gcloud` CLI installed and authenticated locally (`gcloud auth login`,
      `gcloud auth application-default login`).
- [ ] Docker Desktop installed and running (the local stack is Compose-based).
- [ ] Node 20+ and Python 3.12 locally.
- [ ] **Where should alerts go?** Email address, or a Slack/Discord webhook.
      Five alerts are configured in phase 0 and you need to actually see them.

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
