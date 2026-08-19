# ReguLens — Working Agreement

Hackathon project. Deadline **31 Aug 2026, 5:00pm PDT**. Plan lives in `plan/`.

## Before doing anything

1. Read **`plan/PROGRESS.md`** first. It is the single source of truth for what is
   already built.
2. Do not rebuild a phase marked `COMPLETE`. Read its phase file to learn what
   exists.
3. If a phase is `IN PROGRESS`, the unticked boxes in that phase file are the
   remaining work. Start there.
4. Check `todo.md` for inputs still blocked on the user before assuming something is
   missing because of a bug.

## While working

- Work the current phase only. If you find something belonging to a later phase,
  note it in that phase's file rather than building it now.
- Every phase file has a **Status** block and checkboxes. They are the record.

## After every meaningful change — not optional

Update the plan in the same commit as the code. A checkbox that lags the repo is
worse than no checkbox, because the next session trusts it.

- [ ] Tick the boxes in the relevant `plan/phases/phase-N-*.md` for what actually
      landed.
- [ ] Update that file's **Status** block (`NOT STARTED` → `IN PROGRESS` →
      `COMPLETE`) and its dates.
- [ ] Update the phase row and any cross-cutting boxes in `plan/PROGRESS.md`.
- [ ] Append one line to the **Session log** in `plan/PROGRESS.md`.
- [ ] If a decision got made, record it under **Decisions taken** so it is not
      reopened.

## Checkbox semantics

| Marker | Meaning |
|---|---|
| `- [ ]` | Not done |
| `- [x]` | Done, in the repo, **and deployed** |
| `- [~]` | Deliberately skipped. Append ` — SKIPPED: <reason>` on the same line |

Tick a box only when the thing is real and verified. Not "written down", not
"works locally". If you skip something on purpose, mark it `[~]` with a reason so
nobody re-litigates it at 2am on the 30th.

## Standing rules from the plan

- **Deterministic code owns every mutation.** ADK agents propose; typed code
  decides. Never write a model response into `clauses`, `requirements`, or
  `conflicts` without a Pydantic validator and the guardrail.
- **Every Pub/Sub handler is idempotent.** Delivery is at-least-once and will
  redeliver.
- **ADK tools wrap plain functions** that are importable and testable without ADK.
- **Structured JSON logs with `trace_id` on every line.** No `print`.
- **Add `data-testid` as you build UI.** Phase 6 depends on it.
- **Claim only what is verified.** No fabricated readiness percentages, no invented
  regulation text, no "monitoring" language for behaviour that only runs on upload.
