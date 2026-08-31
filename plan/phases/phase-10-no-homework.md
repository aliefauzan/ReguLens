# Phase 10 — No Homework

**Status:** `IN PROGRESS`
**Started:** 31 Aug 2026
**Completed:** —

> The motto: *never make the user check for themselves.* This phase is the audit
> of where the product breaks that promise, and the fixes. Every finding below
> was reproduced before it was written down — the repro is named on the line.

A card that reads

> ⚠ acesulfame k — This rule has no number in it, so a person has to read it.

is the visible end of four separate defects. Chasing it found three more of the
same family. They share one shape: **the system quietly hands back a partial or
wrong answer, and only the user could ever discover that.**

## Findings

| # | Defect | Where | Verified by |
|---|---|---|---|
| F1 | A non-numeric clause binds every product in the jurisdiction — no substance gate, no food gate | `core/impact.py:97-110` | repro: a nectar footnote binds a drink powder |
| F2 | "This rule has no number in it" is printed over clauses that carry a number | `core/extraction/candidates.py:133-137` + `core/impact.py:625` | repro: `unit_raw="g/l"` gives `clause_type=other`, `limit_value=350.0`, reason `non_numeric_clause` |
| F3 | Two other reasons print "We do not know how much your product contains" and offer "Fill in the amount" — the amount is already filled | `web/app/products/[id]/page.tsx:285-296`, `core/remediation.py:57` | product units come from a three-value dropdown (`web/lib/api.ts:296`) that always converts (`core/guardrail.py:35-39`), so `unit_unconvertible` is never the user's data |
| F4 | A unit string over 32 characters destroys the whole clause | `models.py`, `unit_raw` `max_length=32` | repro: `"mg/l or mg/kg as appropriate (header)"` gives `validation_failed`; the clause is never stored |
| F5 | Verdicts are computed against an arbitrary 200 clauses | `core/impact.py:24-32` — no `order_by`, no count, no warning | the starter library alone is ~406 rule rows (187 EU table rows + 219 BPOM GSFA rows) |
| F6 | The same silent 200-cap on requirements decides rollup status, the compliance page, and the remediation target | `core/impact.py:286`, `main.py:495`, `core/remediation.py:109` | same query shape as F5 |
| F7 | Alerts can silently miss the newest one | `core/alerts.py:163-176` — an arbitrary 50 `graph_events` are fetched, *then* sorted by time | every mutation writes a `graph_event`, so 50 is reached quickly |

F5–F7 are the serious ones: a product can read **pass** because the rule that
fails it was outside the window, and nothing on the screen says so. That is the
exact failure the working agreement forbids — *"a filter that hides something
must say how much and why."*

## Rounds

Each round is: write the failing test, fix, run the suite, review, move on.

### Round 1 — stop the silent truncation (F5, F6, F7)

- [ ] `core/paging.py`: one documented scan cap, and `read_capped()` which fetches
      `cap + 1` so overflow is *detected* rather than assumed away
- [ ] `clauses_active()`, `_requirements_for()`, the compliance route, the
      remediation reader and `list_alerts()` all go through it
- [ ] Truncation is carried to the caller, logged, and rendered — a verdict
      computed on a partial rulebook says so instead of showing a green tick
- [ ] Tests: an over-cap collection reports `truncated`, and the alert list
      surfaces the newest alert rather than an arbitrary one

### Round 2 — stop attaching rules that do not apply (F1)

- [ ] A non-numeric clause that names a substance binds only a product that
      contains it, and only when the food matches — the same gates a numeric
      clause already passes
- [ ] Annex footnote rows (`(49): The maximum usable levels are derived …`) are
      recognised as basis notes: they modify other clauses and are never a
      requirement of their own
- [ ] A clause naming no substance still binds — those are the real
      document-level obligations, and hiding them would be the same sin

### Round 3 — say the true reason, offer the true action (F2, F3)

- [ ] `evaluate()` reports why the clause is not comparable, distinguishing
      "the row states no number" from "the row's unit was unreadable"
- [ ] The product page prints a sentence per reason, and the call to action
      matches it — no "fill in the amount" for an amount already filled
- [ ] `remediation.py` stops blaming the ingredient's unit for the rule's

### Round 4 — a long unit string must not destroy a limit (F4)

- [ ] An over-length `unit_raw` lands in review, not in the bin — the number
      survives, flagged, with the raw string kept for the reader

## Decisions

- **Raise the cap and report overflow, rather than paginate.** Real pagination
  needs `order_by("__name__") + start_after`, which the read-only test doubles do
  not implement and which buys nothing at this workspace size. A documented cap
  well above any real rulebook, plus an honest `truncated` flag, is the smaller
  change and the one that cannot lie.
