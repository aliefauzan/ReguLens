"""Reconciliation: embed, find similar, guardrail, judge, apply verdict.

The pipeline the plan mandates:
  find_similar → guardrail → (only if comparable + ambiguous) judge →
  transactional state mutation with one decision event per clause.

Deterministic code owns every mutation. The judge proposes; this module decides.
"""

from __future__ import annotations

import json
import logging

from google.cloud import firestore

from app.core.guardrail import (
    IncomparablePair,
    comparability,
    relationship_class,
)
from app.core.repository import new_id
from app.db import get_db
from app.models import (
    WORKSPACE_ID,
    ClauseStatus,
    EventType,
)
from app.observability import get_trace_id, log
from app.settings import get_settings

logger = logging.getLogger(__name__)

RECONCILED_STATUSES = {
    ClauseStatus.ACTIVE,
    ClauseStatus.SUPERSEDED,
    ClauseStatus.CONFLICTED,
    ClauseStatus.NEEDS_REVIEW,
}


# ---------------------------------------------------------------------------
# Embeddings + retrieval


def embed_text(text: str) -> list[float]:
    """Vertex text-embedding for one clause text. FAKE_LLM returns a
    deterministic pseudo-vector so tests stay free and stable."""
    settings = get_settings()
    if settings.fake_llm:
        import hashlib

        digest = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in digest[:32]]

    from google import genai

    client = genai.Client(vertexai=True, project=settings.project_id, location=settings.embed_location)
    result = client.models.embed_content(
        model=settings.embed_model,
        contents=text[:5000],
    )
    vectors = getattr(result, "embeddings", None)
    if not vectors:
        raise RuntimeError("embedding call returned no vectors")
    return list(vectors[0].values)


def find_similar(clause: dict, k: int = 10) -> list[dict]:
    """Active clauses sharing substance_normalized OR jurisdiction, cosine-ranked.

    In-process cosine over Firestore-stored vectors — the plan's deliberate
    no-vector-database decision. Signature stays stable so a managed index can
    replace the body later.
    """
    db = get_db()
    substance = clause.get("substance_normalized")
    base = db.collection("clauses").where(
        filter=firestore.FieldFilter("status", "in", ["active", "conflicted"])
    )
    if substance:
        from app.core.guardrail import _SUBSTANCE_FAMILIES

        family = next(
            (f for f in _SUBSTANCE_FAMILIES.values() if substance in f), [substance]
        )
        base = base.where(filter=firestore.FieldFilter("substance_normalized", "in", family))
    by_substance = [d.to_dict() | {"id": d.id} for d in base.limit(k * 4).stream()]
    results: list[dict] = []
    seen = {clause.get("id")}
    for other in by_substance:
        if other["id"] in seen:
            continue
        seen.add(other["id"])
        results.append(other)
    return _ranked(results, clause, k)


def _ranked(candidates: list[dict], clause: dict, k: int) -> list[dict]:
    """Cosine rank in process. Missing vectors sort last, deterministically."""
    import math

    target = clause.get("embedding") or []

    def cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return -1.0
        num = sum(x * y for x, y in zip(a, b, strict=False))
        den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
        return num / den if den else -1.0

    scored = [(cosine(target, c.get("embedding") or []), c) for c in candidates]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:k]]


# ---------------------------------------------------------------------------
# Judge


def judge_pair(a: dict, b: dict) -> dict:
    """Constrained-enum verdict for a comparable pair the deterministic
    classification could not settle. Unparsable output becomes `ambiguous` —
    never `conflict`."""

    settings = get_settings()
    if settings.fake_llm:
        return {"verdict": "distinct_scope", "rationale": "fake judge: distinct scope"}

    from google.genai import types

    from app.core.extraction.llm import _client

    prompt = f"""Two comparable regulatory clauses. Decide the relationship.

Clause A: {a.get("text")}
(A fields: substance={a.get("substance")}, limit={a.get("limit_value")} {a.get("unit")},
jurisdiction={a.get("jurisdiction")}, effective={a.get("effective_date")}, doc={a.get("document_id")})

Clause B: {b.get("text")}
(B fields: substance={b.get("substance")}, limit={b.get("limit_value")} {b.get("unit")},
jurisdiction={b.get("jurisdiction")}, effective={b.get("effective_date")}, doc={b.get("document_id")})

Answer as JSON with keys verdict and rationale. verdict is one of:
supersedes, conflicts, distinct_scope, ambiguous."""
    try:
        response = _client().models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "verdict": {
                            "type": "string",
                            "enum": ["supersedes", "conflicts", "distinct_scope", "ambiguous"],
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": ["verdict", "rationale"],
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001 - judge failure must never become a conflict
        log(logger, logging.WARNING, "judge_call_failed", error=str(exc)[:300])
        return {"verdict": "ambiguous", "rationale": f"judge unavailable: {str(exc)[:120]}"}
    try:
        payload = json.loads(response.text or "{}")
        verdict = payload.get("verdict")
        if verdict not in ("supersedes", "conflicts", "distinct_scope", "ambiguous"):
            raise ValueError(f"invalid verdict {verdict!r}")
        return {"verdict": verdict, "rationale": str(payload.get("rationale", ""))[:300]}
    except Exception as exc:  # noqa: BLE001
        log(logger, logging.WARNING, "judge_unparsable", error=str(exc)[:200])
        return {"verdict": "ambiguous", "rationale": "judge output unparsable"}


# ---------------------------------------------------------------------------
# Verdict application — every mutation inside a Firestore transaction


def reconcile_clause(clause_id: str) -> dict:
    """One clause through the full reconciliation pipeline. Idempotent: a
    clause already past `pending_reconciliation` is a no-op.

    Returns a summary dict for the handler response.
    """
    db = get_db()
    snapshot = db.collection("clauses").document(clause_id).get()
    if not snapshot.exists:
        raise PermanentReconcileError(f"clause {clause_id} does not exist")
    clause = snapshot.to_dict() | {"id": snapshot.id}
    if clause.get("status") in {s.value for s in RECONCILED_STATUSES}:
        log(logger, logging.INFO, "idempotent_skip", stage="reconcile", clause_id=clause_id)
        return {"status": "skipped"}

    # Embedding is retrieval plumbing, not a decision: write it directly.
    if not clause.get("embedding"):
        try:
            vector = embed_text(clause.get("text") or "")
            db.collection("clauses").document(clause_id).set(
                {"embedding": vector}, merge=True
            )
            clause["embedding"] = vector
        except Exception as exc:  # noqa: BLE001 - retrieval degrades to filters
            log(logger, logging.WARNING, "embed_failed", clause_id=clause_id, error=str(exc)[:200])

    # Authority gate: low-confidence or review-flagged input never mutates state.
    if clause.get("confidence", 0) < 0.5 or clause.get("needs_review"):
        _apply_review(clause, reason="low_confidence_or_flagged")
        _publish_graph_changed(clause_id)
        return {"status": "needs_review"}

    candidates = find_similar(clause)
    decisions = []
    verdict_outcome: str | None = None
    for other in candidates:
        guard = comparability(clause, other)
        if isinstance(guard, IncomparablePair):
            decisions.append({"other": other["id"], "reason": guard.reason})
            log(
                logger, logging.INFO, "guardrail_rejected",
                clause_id=clause_id, other=other["id"], reason=guard.reason,
            )
            continue

        cls = relationship_class(
            {
                "jurisdiction": clause.get("jurisdiction"),
                "limit_value": clause.get("limit_value"),
                "unit": clause.get("unit"),
            },
            {
                "jurisdiction": other.get("jurisdiction"),
                "limit_value": other.get("limit_value"),
                "unit": other.get("unit"),
            },
            values=(guard.value_a, guard.value_b),
        )
        log(
            logger, logging.INFO, "pair_compared",
            clause_id=clause_id, other=other["id"], relationship=cls,
        )
        if cls == "equal_no_finding":
            outcome = "duplicate_no_finding"
        elif cls == "cross_jurisdiction_conflict":
            # Deterministic by design: different jurisdictions with different
            # limits means BOTH hold and the stricter binds. The judge is not
            # consulted. Only ACTIVE partners open a conflict: a needs_review
            # or already-conflicted counterpart must not gain state from this
            # comparison.
            if other.get("status") == "active":
                outcome = "conflicts"
            else:
                outcome = "no_finding_partner_inactive"
        elif _dates_decide(clause, other):
            outcome = "supersedes" if _is_newer(clause, other) else "superseded_by_existing"
        else:
            # Same jurisdiction, undecidable dates: the one genuinely ambiguous
            # case. This is the ONLY call the judge gets.
            verdict = judge_pair(clause, other)
            log(
                logger, logging.INFO, "judge_invoked",
                clause_id=clause_id, other=other["id"],
                verdict=verdict["verdict"], rationale=verdict["rationale"][:120],
            )
            mapping = {
                "supersedes": "supersedes",
                "conflicts": "conflicts",
                "distinct_scope": "distinct_scope_no_finding",
                "ambiguous": "needs_review_judge",
            }
            outcome = mapping.get(verdict["verdict"], "needs_review_judge")

        decisions.append({"other": other["id"], "relationship": cls, "outcome": outcome})
        verdict_outcome = _dominant(outcome, verdict_outcome)

    if verdict_outcome is None:
        _apply_active(clause)
        _publish_graph_changed(clause_id)
        return {"status": "active", "decisions": decisions, "document_id": clause.get("document_id")}

    if verdict_outcome == "conflicts":
        target = next((d for d in decisions if d.get("outcome") == "conflicts"), None)
        relationship = target.get("relationship") if target else None
        conflict_type = (
            "limit_conflict_ambiguous" if relationship == "supersede_question"
            else "cross_jurisdiction_limit_mismatch"
        )
        _apply_conflict(clause, target["other"] if target else None, conflict_type=conflict_type)
        # A newer same-jurisdiction clause may BOTH conflict across
        # jurisdictions AND replace its predecessors. Both findings are real:
        # the predecessors die even though the incoming clause ends conflicted.
        for d in decisions:
            if d.get("outcome") == "supersedes" and d.get("other"):
                _mark_superseded(d["other"], by_clause_id=clause_id)
        _publish_graph_changed(clause_id)
        return {"status": "conflicts", "decisions": decisions, "document_id": clause.get("document_id")}
    if verdict_outcome == "supersedes":
        # Every ACTIVE predecessor dies; the winner activates. Race safety
        # lives inside _mark_superseded / _apply_active.
        for d in decisions:
            if d.get("outcome") == "supersedes" and d.get("other"):
                _mark_superseded(d["other"], by_clause_id=clause_id)
        _apply_active(clause)
        _publish_graph_changed(clause_id)
        return {"status": "supersedes", "decisions": decisions, "document_id": clause.get("document_id")}
    if verdict_outcome == "superseded_by_existing":
        existing = next(
            (d for d in decisions if d.get("outcome") == "superseded_by_existing"), None
        )
        _apply_superseded(clause, existing["other"] if existing else None)
        _publish_graph_changed(clause_id)
        doc_id = clause.get("document_id")
        return {"status": "superseded_by_existing", "decisions": decisions, "document_id": doc_id}
    if verdict_outcome == "needs_review_judge":
        _apply_review(clause, reason="judge_ambiguous")
        _publish_graph_changed(clause_id)
        return {"status": "ambiguous_needs_review", "decisions": decisions}
    # Only no-finding outcomes remain: the clause stands on its own.
    _apply_active(clause)
    _publish_graph_changed(clause_id)
    return {"status": "active", "decisions": decisions, "document_id": clause.get("document_id")}


class PermanentReconcileError(Exception):
    """Acks; retrying cannot help."""


class TransientReconcileError(Exception):
    """Nacks; Pub/Sub redelivers."""


def _publish_graph_changed(clause_id: str) -> None:
    from app.messaging.publisher import publish

    publish(
        get_settings().topic_graph_changed,
        {"entity_type": "clause", "entity_id": clause_id, "clause_id": clause_id,
         "workspace_id": WORKSPACE_ID},
    )


def confirm_clause(clause_id: str) -> dict | None:
    """Human confirm on a needs_review clause: promote to active. One button,
    no workflow.

    Returns None when the clause does not exist. Every other path returns a
    status dict — the transaction says which of the three outcomes happened
    rather than leaving the caller to infer it from `None`, which previously
    made "no such clause" and "promoted" indistinguishable *and* inverted the
    republish, so a confirmed clause never re-ran impact.
    """
    db = get_db()

    @firestore.transactional
    def txn(transaction):
        ref = db.collection("clauses").document(clause_id)
        fresh = ref.get(transaction=transaction)
        if not fresh.exists:
            return {"status": "missing"}
        data = fresh.to_dict()
        if data.get("status") != "needs_review":
            return {"status": "unchanged"}
        event_id = new_id("evt")
        transaction.set(
            db.collection("graph_events").document(event_id),
            _event_payload(EventType.CLAUSE_CREATED, clause_id,
                           {"status": "needs_review"}, {"status": "active"},
                           {"confirmed_by": "human"}, "human", data.get("confidence")),
        )
        transaction.set(ref, {"status": "active", "review_reason": None}, merge=True)
        return {"status": "active"}

    result = txn(db.transaction())
    if result["status"] == "missing":
        return None
    if result["status"] == "active":
        # A clause only counts once it is active, so this is the moment every
        # affected product has to be re-evaluated.
        _publish_graph_changed(clause_id)
    return result


def dismiss_clause(clause_id: str) -> dict | None:
    """Human reject on a needs_review clause: park it, never delete it.

    The queue previously had one button. A clause the reader judged wrong could
    only be left sitting there, so the count never fell and the queue stopped
    meaning anything. `dismissed` is terminal and inert — nothing promotes it,
    nothing evaluates against it — but the record and its event survive, which
    is the point of an audit trail.
    """
    db = get_db()

    @firestore.transactional
    def txn(transaction):
        ref = db.collection("clauses").document(clause_id)
        fresh = ref.get(transaction=transaction)
        if not fresh.exists:
            return {"status": "missing"}
        data = fresh.to_dict()
        if data.get("status") != "needs_review":
            return {"status": "unchanged"}
        event_id = new_id("evt")
        transaction.set(
            db.collection("graph_events").document(event_id),
            _event_payload(EventType.CLAUSE_DISMISSED, clause_id,
                           {"status": "needs_review"}, {"status": "dismissed"},
                           {"dismissed_by": "human"}, "human", data.get("confidence")),
        )
        transaction.set(ref, {"status": "dismissed", "review_reason": None}, merge=True)
        return {"status": "dismissed"}

    result = txn(db.transaction())
    if result["status"] == "missing":
        return None
    if result["status"] == "dismissed":
        log(logger, logging.INFO, "clause dismissed", clause_id=clause_id)
    return result


# ---------------------------------------------------------------------------
# Transactional verdict application


def _is_newer(a: dict, b: dict) -> bool:
    """True when `a` should replace `b` (same jurisdiction): effective_date
    first, document recency second."""
    da = str(a.get("effective_date") or "")
    db_ = str(b.get("effective_date") or "")
    if da and db_ and da != db_:
        return da > db_
    return str(a.get("document_id") or "") > str(b.get("document_id")) or False


def _dates_decide(a: dict, b: dict) -> bool:
    """True when the supersede question can be settled by dates alone."""
    da = str(a.get("effective_date") or "")
    db_ = str(b.get("effective_date") or "")
    return bool(da and db_ and da != db_)


def _dominant(outcome: str, current: str | None) -> str | None:
    """Priority when one candidate clause meets several others: conflict beats
    supersede; needs_review never comes from here (handled earlier)."""
    order = {
        "conflicts": 4,
        "needs_review_judge": 3,
        "supersede": 2,
        "supersedes": 2,
        "superseded_by_existing": 1,
        "duplicate_no_finding": 0,
        "distinct_scope_no_finding": 0,
    }
    if current is None:
        return outcome
    return outcome if order.get(outcome, 0) > order.get(current, 0) else current


def _event_payload(
    event_type: EventType,
    entity_id: str,
    before: dict | None,
    after: dict | None,
    cause: dict | None,
    triggered_by: str,
    confidence: float | None = None,
) -> dict:
    from app.core.repository import _event_payload as repo_payload

    payload = repo_payload(event_type, "clause", entity_id, before, after, triggered_by, cause, confidence)
    return payload


def _apply_review(clause: dict, *, reason: str) -> None:
    """needs_review: the clause never mutates existing state. One event."""
    db = get_db()

    @firestore.transactional
    def txn(transaction):
        fresh = db.collection("clauses").document(clause["id"]).get(transaction=transaction)
        if not fresh.exists:
            raise TransientReconcileError(f"clause {clause['id']} vanished")
        current = fresh.to_dict() | {"id": fresh.id}
        if current.get("status") != "pending_reconciliation":
            return  # raced; already decided
        event_id = new_id("evt")
        transaction.set(
            db.collection("graph_events").document(event_id),
            _event_payload(EventType.CLAUSE_FLAGGED_REVIEW, clause["id"], None,
                           {"status": "needs_review"}, {"reason": reason}, "reconciliation_agent",
                           clause.get("confidence")),
        )
        transaction.set(
            db.collection("clauses").document(clause["id"]),
            {"status": "needs_review", "review_reason": reason},
            merge=True,
        )

    txn(db.transaction())


def _apply_active(clause: dict) -> None:
    """No comparable counterpart: new clause becomes active."""
    db = get_db()

    @firestore.transactional
    def txn(transaction):
        fresh = db.collection("clauses").document(clause["id"]).get(transaction=transaction)
        if not fresh.exists:
            raise TransientReconcileError(f"clause {clause['id']} vanished")
        if fresh.to_dict().get("status") != "pending_reconciliation":
            return  # raced; already decided
        event_id = new_id("evt")
        transaction.set(
            db.collection("graph_events").document(event_id),
            _event_payload(EventType.CLAUSE_CREATED, clause["id"], None,
                           {"status": "active", "limit_value": clause.get("limit_value")},
                           {"document_id": clause.get("document_id")}, "reconciliation_agent",
                           clause.get("confidence")),
        )
        transaction.set(
            db.collection("clauses").document(clause["id"]),
            {"status": "active"},
            merge=True,
        )

    txn(db.transaction())


def _apply_supersede(new_clause: dict, old_clause_id: str | None) -> None:
    """Same jurisdiction, newer effective date: new replaces old."""
    db = get_db()

    @firestore.transactional
    def txn(transaction):
        new_ref = db.collection("clauses").document(new_clause["id"])
        fresh_new = new_ref.get(transaction=transaction)
        if not fresh_new.exists:
            raise TransientReconcileError(f"clause {new_clause['id']} vanished")
        if fresh_new.to_dict().get("status") != "pending_reconciliation":
            return  # raced; already decided
        updates: dict = {"status": "active"}
        if old_clause_id:
            old_ref = db.collection("clauses").document(old_clause_id)
            fresh_old = old_ref.get(transaction=transaction)
            if fresh_old.exists and fresh_old.to_dict().get("status") == "active":
                supersede_event = new_id("evt")
                transaction.set(
                    old_ref,
                    {"status": "superseded", "superseded_by": new_clause["id"]},
                    merge=True,
                )
                transaction.set(
                    db.collection("graph_events").document(supersede_event),
                    _event_payload(
                        EventType.CLAUSE_SUPERSEDED, old_clause_id,
                        {"status": "active"}, {"status": "superseded"},
                        {"new_clause_id": new_clause["id"],
                         "document_id": new_clause.get("document_id")},
                        "reconciliation_agent", new_clause.get("confidence"),
                    ),
                )
                updates["supersedes"] = old_clause_id
        transaction.set(new_ref, updates, merge=True)
        created_event = new_id("evt")
        transaction.set(
            db.collection("graph_events").document(created_event),
            _event_payload(EventType.CLAUSE_CREATED, new_clause["id"], None,
                           {"status": "active"}, {"document_id": new_clause.get("document_id")},
                           "reconciliation_agent", new_clause.get("confidence")),
        )

    txn(db.transaction())


def _mark_superseded(clause_id: str, *, by_clause_id: str) -> None:
    """Mark one ACTIVE clause superseded by another. No-op when its status has
    moved (raced, already conflicted/superseded)."""
    db = get_db()

    @firestore.transactional
    def txn(transaction):
        ref = db.collection("clauses").document(clause_id)
        fresh = ref.get(transaction=transaction)
        if not fresh.exists or fresh.to_dict().get("status") != "active":
            return
        event_id = new_id("evt")
        transaction.set(
            db.collection("graph_events").document(event_id),
            _event_payload(
                EventType.CLAUSE_SUPERSEDED, clause_id,
                {"status": "active"}, {"status": "superseded"},
                {"new_clause_id": by_clause_id},
                "reconciliation_agent", None,
            ),
        )
        transaction.set(
            ref,
            {"status": "superseded", "superseded_by": by_clause_id},
            merge=True,
        )

    txn(db.transaction())


def _apply_superseded(clause: dict, existing_clause_id: str | None) -> None:
    """The existing clause is newer: this clause loses."""
    db = get_db()

    @firestore.transactional
    def txn(transaction):
        ref = db.collection("clauses").document(clause["id"])
        fresh = ref.get(transaction=transaction)
        if not fresh.exists:
            raise TransientReconcileError(f"clause {clause['id']} vanished")
        if fresh.to_dict().get("status") != "pending_reconciliation":
            return
        event_id = new_id("evt")
        transaction.set(
            db.collection("graph_events").document(event_id),
            _event_payload(
                EventType.CLAUSE_SUPERSEDED, clause["id"],
                {"status": "pending_reconciliation"}, {"status": "superseded"},
                {"existing_clause_id": existing_clause_id,
                 "document_id": clause.get("document_id")},
                "reconciliation_agent", clause.get("confidence"),
            ),
        )
        transaction.set(
            ref,
            {"status": "superseded", "superseded_by": existing_clause_id},
            merge=True,
        )

    txn(db.transaction())


def _apply_conflict(
    clause: dict,
    other_clause_id: str | None,
    *,
    conflict_type: str = "cross_jurisdiction_limit_mismatch",
) -> None:
    """Cross-jurisdiction mismatch: both clauses stay active, a conflict record
    opens. Neither supersedes the other — that is the whole point."""
    db = get_db()

    @firestore.transactional
    def txn(transaction):
        refs = {
            cid: db.collection("clauses").document(cid)
            for cid in {clause["id"], other_clause_id} if cid
        }
        for cid, ref in refs.items():
            fresh = ref.get(transaction=transaction)
            if not fresh.exists:
                raise TransientReconcileError(f"clause {cid} vanished")
        statuses = {
                cid: (ref.get(transaction=transaction).to_dict() or {}).get("status")
                for cid, ref in refs.items()
            }
        # Only unverified input must never gain state. A partner already in
        # an open conflict MAY enter another one: two clauses can genuinely be
        # in two disputes, each with its own record.
        if any(s == "needs_review" for s in statuses.values()):
            return
        other_data: dict = {}
        if other_clause_id and other_clause_id in refs:
            other_data = refs[other_clause_id].get(transaction=transaction).to_dict() or {}
        conflict_id = new_id("conf")
        transaction.set(
            db.collection("conflicts").document(conflict_id),
            {
                "workspace_id": WORKSPACE_ID,
                "clause_a": clause["id"],
                "clause_b": other_clause_id,
                "type": conflict_type,
                "detail": {
                    "a_limit": clause.get("limit_value"), "a_unit": clause.get("unit"),
                    "b_limit": other_data.get("limit_value"),
                    "b_unit": other_data.get("unit"),
                },
                "severity": "high",
                "status": "open",
                "detected_by": "reconciliation_agent",
                "trace_id": get_trace_id(),
            },
        )
        for cid in refs:
            transaction.set(refs[cid], {"status": "conflicted"}, merge=True)
        event_id = new_id("evt")
        transaction.set(
            db.collection("graph_events").document(event_id),
            _event_payload(EventType.CONFLICT_OPENED, conflict_id, None,
                           {"clause_a": clause["id"], "clause_b": other_clause_id,
                            "type": "cross_jurisdiction_limit_mismatch"},
                           {"document_id": clause.get("document_id")},
                           "reconciliation_agent", clause.get("confidence")),
        )

    txn(db.transaction())
