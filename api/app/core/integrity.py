"""Audit-integrity walker: every mutation has a matching graph_events record."""

from __future__ import annotations

import sys

from app.db import get_db


def walk() -> tuple[bool, list[str]]:
    """Every non-pending clause must carry its decision event(s)."""
    db = get_db()
    events = [e.to_dict() for e in db.collection("graph_events").limit(2000).stream()]
    by_entity: dict[str, set[str]] = {}
    for e in events:
        by_entity.setdefault(e.get("entity_id"), set()).add(e.get("event_type"))

    invariants = {
        "active": {"clause_created"},
        "superseded": {"clause_superseded"},
        "conflicted": {"conflict_opened"},
        "needs_review": {"clause_flagged_review"},
    }
    # conflict_opened keys on the conflict record; map it back to its clauses.
    opened_clause_ids = set()
    for e in events:
        if e.get("event_type") != "conflict_opened":
            continue
        after = e.get("after") or {}
        opened_clause_ids.update({after.get("clause_a"), after.get("clause_b")} - {None})
        cause = e.get("cause") or {}
        opened_clause_ids.update({cause.get("clause_id"), cause.get("other")} - {None})

    problems = []
    for d in db.collection("clauses").limit(500).stream():
        c = d.to_dict() or {}
        status = c.get("status")
        wanted = invariants.get(status)
        if not wanted:
            continue
        have = by_entity.get(d.id, set())
        if status == "conflicted" and d.id in opened_clause_ids:
            have = have | {"conflict_opened"}
        missing = wanted - have
        if missing:
            problems.append(f"clause {d.id} ({status}): missing {sorted(missing)}")
    return (not problems), problems


if __name__ == "__main__":
    ok, problems = walk()
    for p in problems:
        print("PROBLEM:", p)
    print("integrity:", "OK" if ok else f"{len(problems)} VIOLATIONS")
    sys.exit(0 if ok else 1)
