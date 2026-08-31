# An agent may not present an ungrounded answer as a grounded one

We wired an ADK agent into ReguLens's `/query` endpoint on 29 August. The
end-to-end suite, running against the deployed stack, caught it lying within
minutes.

Not lying in the interesting way. It did not invent a regulation. What it did
was worse, and much easier to miss.

## What happened

ReguLens ingests food-additive regulations, extracts the numeric limits as
clauses, and answers questions about a product against them. The query agent
has four retrieval tools and picks its own path through them. In a live run it
served between 79 and 113 clause ids to itself and cited five to eight.

Then the drill asked it about Japan — a country the workspace held no ingested
regulation for. The agent answered:

> there is no information available

and attached citations for the clauses it had looked at on the way to that
conclusion. The response came back with `refusal: false`. The UI rendered
citation cards underneath a sentence saying there was nothing to cite.

## Why that is dangerous, not merely ugly

A citation is a promise: *this sentence rests on that source.* The promise is
what makes a grounded system worth more than a chatbot, and it is the only
reason a compliance officer would act on an answer instead of reading the
regulation themselves.

A citation card beneath "there is no information available" breaks the promise
in the most corrosive possible way — not by pointing at a fake source, but by
teaching the reader that the cards are decoration. Once a user learns that
citations appear whether or not the answer is grounded, every *correct*
citation in the product loses its meaning too. One bad answer devalues the
good ones.

And the failure was invisible to every automated check we had, because every
individual component was behaving. Retrieval ran. The tools returned real
clauses. The citation validator confirmed each cited id was a clause this
process had genuinely read out of Firestore. Nothing was fabricated. The
system was internally consistent and externally dishonest.

## Why a prompt fix is not enough

The obvious repair is to tell the model to be clearer: *say plainly when you
don't know.* We had already done that. Its instruction said, in as many words,
that a clause about a different country is not evidence about this one.

The model complied. It said it did not know. It said so in prose — and prose
has to be interpreted by code that cannot interpret. There is no reliable
predicate for "is this sentence a refusal?" `"there is no information
available"`, `"I could not find a specific limit"`, `"the ingested regulations
do not appear to cover"` — a regex over these is a losing arms race against a
model that paraphrases freely, in a system where a false negative ships a
decorated non-answer to somebody making a compliance decision.

## The fix: one checkable token

The agent got a single word for emptiness:

```
If the tools return nothing that actually covers what was asked — a country we
hold no regulation for, a substance nobody has ingested a rule about — reply
with exactly:

INSUFFICIENT_EVIDENCE

and nothing else. No explanation, no citations, no near-misses.
```

And typed code, not the agent, decides what that means:

```python
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"

# ...
if INSUFFICIENT in answer:
    # The agent said it has nothing. Hand over to the single-call path,
    # which refuses in the words a user should read.
    log(logger, logging.INFO, "query_agent_insufficient")
    return ("", [])
```

An empty citation list is the whole contract. The endpoint's refusal flag is
one expression, and it is derived, never asserted by the model:

```python
"refusal": not cited,
```

**A single token can be verified. A sentence that explains itself cannot.**

Re-verified against the deployed stack: Japan now refuses, with zero citations
and no cards.

## The same rule, everywhere else

This is not a query-agent patch. It is the rule the whole system is built on:
**deterministic code owns every mutation; the model only proposes.**

The citation validator is the same shape — it admits an id only if this process
actually read that clause, and it says so when the model reaches for one it did
not:

```python
retrieved = {c["id"] for c in bundle["clauses"]} | (extra_ids or set())
found = set(re.findall(r"clause_[a-z0-9]+", answer))
missing = found - retrieved
if missing:
    log(logger, logging.WARNING, "ungrounded_citation_attempt", unknown=sorted(missing)[:5])
return sorted(found & retrieved)
```

So is the guardrail that decides whether two clauses may even be compared — no
model call at all, just units, substances and food-category scope. So is the
impact engine: pass or fail against a numeric limit is arithmetic, and
arithmetic does not need an opinion. The reconciliation agent is invoked at
exactly one decision, the genuinely ambiguous same-jurisdiction pair, and its
verdict passes through a Pydantic validator before it can touch anything
stored.

## What this cost, and what it bought

The bug lived for minutes, because the end-to-end drill runs against the real
deployed system rather than a mock. A mocked agent would have returned a
mocked answer and passed. The lesson we keep relearning on this project is
that a pipeline green stage by stage is not a pipeline that works — four other
defects only became findable after a verdict finally moved end to end.

If you are building on agents right now, the transferable part is small enough
to fit on one line: *never let the model be the thing that decides whether its
own output is trustworthy.* Give it a token. Check the token in code you wrote.

---

ReguLens is open source — Gemini 3.5 Flash, Gemma, Google ADK, Cloud Run,
Pub/Sub and Firestore.

- Code: https://github.com/aliefauzan/ReguLens
- Demo video: <!-- TODO: paste the YouTube URL from S3 before publishing -->
