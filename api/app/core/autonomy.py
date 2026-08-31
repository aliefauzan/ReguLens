"""What ReguLens did without being asked.

The product's claim is that it acts on its own. Until now that claim lived in a
README and in a scheduler job nobody can see from the app — the only visible
evidence was a document list where a self-found regulation looked exactly like
an upload. A claim about autonomy that a reader cannot check is a slogan.

So this counts it, from stored records only:

- how many regulations arrived with `origin="watched_source"` — nobody uploaded
  them, nobody pasted them, nobody pressed a button;
- how many clauses were read out of those;
- how many product verdicts moved as a direct result;
- when the last sweep ran, and what it found.

Two rules keep the number honest. **Nothing here is derived from a log line or a
counter that could drift** — every figure is a query over the same collections
that serve the rest of the app, so a number shown here can be clicked through
to the thing it counts. And **a zero is reported as a zero.** A quiet week is
the ordinary case for a regulatory monitor, and inflating it would be the
easiest lie in the codebase to tell.
"""

from __future__ import annotations

import logging
from typing import Any

from google.cloud import firestore

from app.core.alerts import UNPROMPTED_ORIGINS, cause_document_id, worsened
from app.db import get_db
from app.observability import log

logger = logging.getLogger(__name__)


def _unprompted_document_ids() -> set[str]:
    """Documents that reached the graph without a person putting them there."""
    found: set[str] = set()
    for origin in sorted(UNPROMPTED_ORIGINS):
        snapshots = (
            get_db()
            .collection("documents")
            .where(filter=firestore.FieldFilter("origin", "==", origin))
            .limit(500)
            .stream()
        )
        found.update(snapshot.id for snapshot in snapshots)
    return found


def _clause_count(document_ids: set[str]) -> int:
    """Clauses read out of those documents.

    Firestore's `in` filter takes thirty values, so this walks the ids in
    chunks rather than pretending one query will do.
    """
    if not document_ids:
        return 0
    ids = sorted(document_ids)
    total = 0
    for start in range(0, len(ids), 30):
        chunk = ids[start : start + 30]
        total += sum(
            1
            for _ in get_db()
            .collection("clauses")
            .where(filter=firestore.FieldFilter("document_id", "in", chunk))
            .limit(500)
            .stream()
        )
    return total


def summary() -> dict[str, Any]:
    """The autonomy figures, each one a query rather than a counter."""
    from app.core import sources as sources_core

    document_ids = _unprompted_document_ids()

    # Verdict changes caused by one of those documents. Read from the same
    # `graph_events` the timeline renders, so the count and the audit trail can
    # never disagree.
    verdict_changes = 0
    events = (
        get_db()
        .collection("graph_events")
        .where(filter=firestore.FieldFilter("event_type", "==", "product_status_changed"))
        .limit(200)
        .stream()
    )
    for snapshot in events:
        event = snapshot.to_dict() or {}
        # Through the same resolver the alert list uses, and for the same
        # reason: an event written from reconciliation names the clause that
        # moved and leaves the document null, so reading the field directly
        # counts a regulation nobody uploaded as zero.
        cause_document = cause_document_id(event)
        if cause_document in document_ids and worsened(event | {"id": snapshot.id}):
            verdict_changes += 1

    watched = sources_core.list_sources()
    checks = sum(source.checks for source in watched)
    last_checked = max(
        (source.last_checked_at for source in watched if source.last_checked_at),
        default=None,
    )

    result = {
        "watched_sources": len(watched),
        "enabled_sources": sum(1 for source in watched if source.enabled),
        # A source stuck on `error` is not being watched, and a page claiming
        # autonomy has to say so in the same breath as the good numbers.
        "failing_sources": sum(1 for source in watched if str(source.last_status) == "error"),
        "checks_run": checks,
        "last_checked_at": last_checked,
        "regulations_found": len(document_ids),
        "clauses_read": _clause_count(document_ids),
        "verdicts_changed": verdict_changes,
        "documents": sorted(document_ids),
    }
    log(logger, logging.INFO, "autonomy summary", **{
        k: v for k, v in result.items() if k not in {"documents", "last_checked_at"}
    })
    return result
