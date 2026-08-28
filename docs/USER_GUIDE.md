# Using the ReguLens Web App

You do not need to know anything about cloud computing, regulations, or code to
follow this guide. Every screen is written in plain language, and every step
below takes a few minutes.

| Where to run it | URL |
|---|---|
| On your own machine (free, no account) | http://localhost:3000 — see [Running it on your machine](#running-it-on-your-machine) |
| Deployed environment | https://regulens-web-babuvy7w3a-as.a.run.app |

There is no login. This version has a single shared workspace by design.

## What this app is for

You make a product. You want to sell it in more than one country. Every country
has its own rules about what can go into it and how much. ReguLens keeps a copy
of your product's recipe, reads the rules you give it, and tells you — for each
country — whether you are allowed to sell it. When a new rule arrives later, it
re-checks your product on its own and tells you what changed.

## Running it on your machine

You need Docker Desktop running. Nothing else — no Google account, no payment.

```bash
docker compose up -d firestore pubsub api worker web
docker compose up pubsub-init
curl -X POST http://localhost:8080/markets/seed
docker compose run --rm api python -m app.job
```

Then open http://localhost:3000.

The last command loads a demo product and the Indonesian rules that apply to it,
so you land in the middle of the story instead of on an empty screen. To wipe
everything and start over: `docker compose down -v`, then repeat the commands
above.

On your machine, the reading of documents is *simulated* — it returns a fixed,
correct-shaped answer instead of calling Google's model. Everything else is
real: the same code, the same queue, the same database behaviour. See the
README for exactly what local mode does and does not prove.

## The walkthrough

### 1. Add your product

Click **Add a product**. The form asks four things in plain words:

- **What is it called?** — `Herbal Drink Powder`
- **What kind of product is it?** — `Drink powder`
- **Where is it made?** — `Indonesia`
- **Where do you want to sell it?** — tick **Germany** and **Indonesia**
- **What is inside it?** — the fastest way is **Paste the list**: copy the
  ingredients straight off your packaging and press **Read this list**. For the
  demo product, paste:

  ```
  ginger, turmeric, honey powder, sodium benzoate (0.08%)
  ```

  ReguLens splits that into rows and fills in an amount only where the text was
  unambiguous. Everything it read lands in an editable table so you can correct
  it before anything is saved. If you would rather type them yourself, switch to
  **Enter one by one** — the ingredient box suggests the names ReguLens already
  knows, including E-numbers.

Only preservatives and additives need an amount — that is the number compared
against the legal limit. If you do not know an amount, leave it blank: the app
will say the ingredient was not checked rather than guess. An amount without a
unit is refused, because a bare number cannot be compared with a legal limit.

Click **Save product**.

### 2. Read the first answer

The product page opens on the question that matters: **Can you sell it?** Each
country gets its own card, and each broken rule shows the two numbers the
verdict turns on — what your product contains against what the law allows. If
you entered a percentage and the law is written in mg/kg, the line underneath
shows both sides converted into the same unit, so you can check the comparison
rather than take it on trust.

Each country gets its own card:

- **Indonesia (BPOM): Meets the rules** — the demo seed already loaded the
  Indonesian regulation, which allows up to 400 mg per kg. Your 300 is under it.
- **Germany (European Union): No rules added yet** — nothing has been read for
  the EU, so the app refuses to guess.

That second card is deliberate. An empty answer and a passing answer must never
look the same.

### 3. Add the European rules

Click **Add rules** in the navigation. The form asks where the document came
from, and this is the most important choice on the page:

| You picked | What ReguLens is allowed to do with it |
|---|---|
| An official regulation | Change your product's verdict on its own |
| Official guidance | Trusted, but checked more carefully |
| An industry association | Usually needs your confirmation |
| A news article | Flagged for you to check |
| A message or social post | Never changes anything by itself |

Pick **An official regulation**, publisher `European Commission`, country
**European Union**. Then upload the file
`data/regulations/excerpts/EU-annex-II-14.1.4-flavoured-drinks-excerpt.pdf` from
this repository — a real four-page excerpt of Commission Regulation (EU)
1129/2011.

Click **Read this document**.

### 4. Watch it work

The next page updates itself. You will see five steps tick over:

`Received → Reading → Rules found → Comparing → Products updated`

Underneath, each rule it found is listed with the substance, the maximum
allowed, and a **How sure are we?** line you can open to see why.

You can close this page. The work continues without you.

### 5. The moment the answer changes by itself

Go back to **Products**. The card at the top always names the single most useful
thing to do next, worked out from the actual state of your data — add rules for
a market that has none, check something that was not confident enough, or look
at a product that now breaks a rule. Underneath it, **What changed on its own**
lists every verdict that moved without you asking.

Within a minute or two, without you asking anything:

- A red banner appears: **Germany (European Union): breaks a rule**
- The Germany card on your product now reads **Breaks a rule**, and says
  `Your product has 300 mg per kg — over the limit` against the EU limit of 150.

Nobody ran a check. A document arrived, and the system worked out on its own
which product it broke, in which country, and why.

### 6. See why the two countries disagree

Click **Disagreements**. You get both rules side by side — the EU at 150 mg per
kg and Indonesia at 400 mg per kg — each quoted in its own words, with the
stricter one marked. At the bottom: *stay at or below 150 mg per kg and the
product is acceptable in both places.*

Neither rule is wrong. They apply in different places.

### 7. Ask a question

On the product page, use **Ask a question**. Type in plain English, or use a
suggestion:

- *Why is my product at risk?* — quotes the exact rule it used
- *Can I sell this in Germany?* — answers from your data only
- Ask about a country you have added no rules for — it **refuses** and says so,
  instead of inventing an answer

Every answer lists the rules it is based on. If nothing in your data answers
the question, you get a refusal, never a guess.

### 8. Things waiting for you

Click **To check**. Anything ReguLens was not confident enough to apply lands
here, with the reason in plain words — *we are not sure we read this correctly*,
*the source is not official enough*, *this rule has no number in it*.

Try it: add a rule again, but choose **A message or social post** as the source
and paste a made-up announcement. Its rule appears in this list and **nothing
about your product changes**. That is the point. Accepting a row here is what
puts it to work.

## When something goes wrong

| What you see | What it means |
|---|---|
| **Service unavailable** | The API is not running. Locally: `docker compose ps` and check `api` is up. |
| **We could not read this document** | Usually a scanned PDF with no real text in it. Paste the text instead. |
| **not recognised** next to an ingredient | The name is not in the substance dictionary, so no rule can match it. Try the common name or the E-number (`E211`). |
| **amount not given** | You left the amount blank, so nothing could be compared. |

## Starting the demo over

```bash
docker compose down -v          # erase everything local
```

Then re-run the four commands from [Running it on your machine](#running-it-on-your-machine).

Against the deployed environment, the same reset is:

```bash
gcloud run jobs execute regulens-job --region "$REGION" --project "$PROJECT_ID" --wait
```

Both are idempotent — running them twice leaves the same state, and re-uploading
an identical document never re-reads it.

## For the curious

`GET /debug/documents/{id}` shows the machinery behind a single document: stage
timings, candidates that were rejected and why, each pairwise comparison
decision, and the three components behind every confidence number. It is enabled
locally by default.
