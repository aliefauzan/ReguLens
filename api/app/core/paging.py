"""How much of a collection one read may see, and what it owes the reader when
there is more.

Every Firestore read in this app carried a bare `.limit(N)`. A limit with no
order and no count is the quietest bug there is: the query returns N arbitrary
documents, the arithmetic downstream is perfectly correct about them, and the
screen shows a verdict computed against a fraction of the rulebook. A product
reads `pass` because the rule that fails it happened to be document 201. The
starter library alone is around 406 rule rows, so the old cap of 200 was not a
theoretical ceiling — one button press went through it.

Two rules govern this module, and both are the working agreement's rather than
new inventions:

  * **Refuse, never truncate.** A read that reached its cap did not answer the
    question it was asked. It says so, and the caller must not present what came
    back as a complete answer.
  * **A filter that hides something must say how much and why.** The shortfall is
    recorded where the request handler can find it, so the page can print it
    instead of a green tick.

The cap is deliberately far above any real workspace. It is a backstop against a
runaway read, not a paging strategy — reaching it is an alarm, not a routine
state, and nothing here quietly pages past it.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

from app.observability import log

logger = logging.getLogger(__name__)

# Far above any rulebook this product is built for; low enough that a runaway
# query cannot stream a collection into memory unbounded.
SCAN_CAP = 5000

# What the current request could not see. A contextvar for the same reason
# `trace_id` is one: the route that assembles the response is several calls away
# from the read that hit the ceiling, and threading a flag through every
# signature in between would be changing eight callers to carry one fact.
_overflows: contextvars.ContextVar[tuple[dict[str, Any], ...]] = contextvars.ContextVar(
    "read_overflows", default=()
)


def reset_overflows() -> None:
    """Start a request with nothing hidden. Called per request, not per read."""
    _overflows.set(())


def overflows() -> list[dict[str, Any]]:
    """Every read in this request that hit its cap, in the order they happened.

    Empty is the answer that means "you are seeing everything", and it is the
    only thing a caller may treat as permission to state a verdict plainly.
    """
    return list(_overflows.get())


def record_overflow(what: str, *, cap: int, seen: int) -> None:
    """Note that `what` had more rows than one read is allowed to see."""
    entry = {"what": what, "cap": cap, "seen": seen}
    _overflows.set(_overflows.get() + (entry,))
    log(logger, logging.ERROR, "read hit its cap", **entry)


def read_capped(query: Any, *, what: str, cap: int = SCAN_CAP) -> list[dict[str, Any]]:
    """Stream `query` into dicts, and report rather than hide an overflow.

    `cap + 1` rows are asked for on purpose. Asking for exactly `cap` cannot tell
    a collection of precisely `cap` rows from one of ten thousand, which is the
    whole reason the old reads could not admit what they were missing.
    """
    rows = [
        snapshot.to_dict() | {"id": snapshot.id}
        for snapshot in query.limit(cap + 1).stream()
    ]
    if len(rows) > cap:
        record_overflow(what, cap=cap, seen=len(rows))
        return rows[:cap]
    return rows
