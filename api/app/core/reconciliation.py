"""Reconciliation: embed, find similar, guardrail, judge, apply verdict.

The pipeline the plan mandates:
  find_similar → guardrail → (only if comparable + ambiguous) judge →
  transactional state mutation with one decision event per clause.

Deterministic code owns every mutation. The judge proposes; this module decides.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

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

# The authority gate's floor, named because two places have to agree on it: the
# gate that parks a clause under it, and the recheck that must never release
# one from under it.
CONFIDENCE_FLOOR = 0.5

RECONCILED_STATUSES = {
    ClauseStatus.ACTIVE,
    ClauseStatus.SUPERSEDED,
    ClauseStatus.CONFLICTED,
    ClauseStatus.NEEDS_REVIEW,
}


# ---------------------------------------------------------------------------
# Embeddings + retrieval


@lru_cache
def _embed_client():
    """One embedding client per process. Building a fresh `genai.Client` per
    clause meant a TLS handshake per clause; the generation path has shared one
    since 23 Aug and this is the same fix on the embedding side."""
    from google import genai

    from app.core.extraction.llm import _http_options

    settings = get_settings()
    # The same owned transport as the generation client, for the same reason:
    # the SDK closes a transport it created when the object holding it is
    # collected, and leaves alone one it was handed.
    if settings.use_gemini_api:
        return genai.Client(
            vertexai=False, api_key=settings.gemini_api_key, http_options=_http_options()
        )
    return genai.Client(
        vertexai=True,
        project=settings.project_id,
        location=settings.embed_location,
        http_options=_http_options(),
    )


# Both backends take a list of texts in one request. The cap keeps a 200-clause
# annex under the per-request instance limit and bounds the payload size.
EMBED_BATCH = 32


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed many clause texts in as few requests as possible.

    One document's clauses were embedded one HTTP call at a time, serially,
    inside reconciliation — the single largest term in the measured 183s
    upload-to-flip. Batching keeps the same vectors and the same model.

    Vectors are model-specific: switching between the Vertex and Gemini API
    paths invalidates everything already stored. find_similar scores a
    length mismatch as -1.0 rather than crashing, so a half-migrated corpus
    degrades to bad matches instead of errors — run scripts/reembed.py."""
    if not texts:
        return []
    settings = get_settings()
    if settings.fake_llm:
        import hashlib

        return [
            [b / 255.0 for b in hashlib.sha256(t.encode()).digest()[:32]] for t in texts
        ]

    from google.genai import types

    client = _embed_client()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        chunk = [t[:5000] for t in texts[start : start + EMBED_BATCH]]
        if settings.use_gemini_api:
            result = client.models.embed_content(
                model=settings.gemini_embed_model,
                contents=chunk,
                config=types.EmbedContentConfig(
                    output_dimensionality=settings.embed_dimensions
                ),
            )
        else:
            result = client.models.embed_content(
                model=settings.embed_model,
                contents=chunk,
            )
        returned = getattr(result, "embeddings", None)
        if not returned or len(returned) != len(chunk):
            raise RuntimeError(
                f"embedding call returned {len(returned or [])} vectors for {len(chunk)} texts"
            )
        vectors.extend(list(v.values) for v in returned)
    return vectors


def embed_text(text: str) -> list[float]:
    """Embed one clause text. Kept for the single-clause paths (reconciliation
    fallback, scripts/reembed.py)."""
    return embed_texts([text])[0]


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


def judge_ambiguous_pair(a: dict, b: dict) -> dict:
    """The verdict for one genuinely ambiguous pair, via the ADK agent.

    The agent has to walk its own tools — comparability, then classification,
    then the judge — so it cannot reach a verdict on a pair the guardrail would
    reject. On any failure this falls back to the direct `judge_pair` call, and
    an unusable verdict is `ambiguous`, never `conflict`: the cost of getting
    this wrong is a false conflict on a user's product.
    """
    settings = get_settings()
    if settings.fake_llm:
        return judge_pair(a, b)

    import asyncio

    from app.adk.reconciliation_agent import run_judge_agent

    try:
        verdict = asyncio.run(run_judge_agent(a, b))
    except Exception as exc:  # noqa: BLE001 - the direct judge is the net
        log(logger, logging.WARNING, "judge_agent_failed", error=str(exc)[:200])
        return judge_pair(a, b)
    if verdict is None:
        log(logger, logging.WARNING, "judge_agent_no_verdict")
        return judge_pair(a, b)
    return verdict


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
    if clause.get("confidence", 0) < CONFIDENCE_FLOOR or clause.get("needs_review"):
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
            # case. This is the ONLY call the judge gets, and the only place the
            # ADK Reconciliation Agent runs — it re-checks comparability and
            # classification with its own tools before it is allowed to judge,
            # so the guardrail is enforced by the tool graph and not by a
            # prompt. Wiring it here rather than around the whole loop is
            # deliberate: a 55-clause annex would otherwise be 55 agent runs on
            # the critical path, and the common case is decided by typed code
            # in microseconds.
            verdict = judge_ambiguous_pair(clause, other)
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
    """Announce that one clause moved.

    The document travels with it. Impact stamps this message's ids onto the
    `product_status_changed` event it writes, and every fact an alert reports
    about a cause hangs off the document: which regulation, which regulator,
    and whether anybody uploaded it. Publishing the clause alone recorded a
    null there, so a verdict moved by a regulation the scheduler found came
    back saying nobody found it.
    """
    from app.messaging.publisher import publish

    snapshot = get_db().collection("clauses").document(clause_id).get()
    document_id = (snapshot.to_dict() or {}).get("document_id") if snapshot.exists else None

    publish(
        get_settings().topic_graph_changed,
        {"entity_type": "clause", "entity_id": clause_id, "clause_id": clause_id,
         "document_id": document_id, "workspace_id": WORKSPACE_ID},
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


DISMISSABLE_STATUSES = frozenset({"needs_review", "active", "conflicted"})


def dismiss_clause(clause_id: str) -> dict | None:
    """Human reject on a clause: park it, never delete it.

    The queue previously had one button. A clause the reader judged wrong could
    only be left sitting there, so the count never fell and the queue stopped
    meaning anything. `dismissed` is terminal and inert — nothing promotes it,
    nothing evaluates against it — but the record and its event survive, which
    is the point of an audit trail.

    An **active** clause can be withdrawn too, and has to be. A rule that
    reached the graph before the code learned to refuse it could otherwise only
    be taken out by deleting the whole document it came from — which would take
    the eighty-seven correct rules of that annex with it. Seen in production:
    "Loss on drying — not more than 0,25 %", a laboratory method stored as a
    2 500 mg/kg ceiling and reported on a product page as the limit binding a
    cured sausage.

    Withdrawing an active clause carries the same duty a document delete does:
    the requirements it produced and the conflicts it opened go with it, and
    every product it touched is re-evaluated. A withdrawal that leaves a stale
    verdict on screen is worse than no withdrawal.
    """
    db = get_db()

    @firestore.transactional
    def txn(transaction):
        ref = db.collection("clauses").document(clause_id)
        fresh = ref.get(transaction=transaction)
        if not fresh.exists:
            return {"status": "missing"}
        data = fresh.to_dict()
        was = str(data.get("status") or "")
        if was not in DISMISSABLE_STATUSES:
            return {"status": "unchanged"}
        event_id = new_id("evt")
        transaction.set(
            db.collection("graph_events").document(event_id),
            _event_payload(EventType.CLAUSE_DISMISSED, clause_id,
                           {"status": was}, {"status": "dismissed"},
                           {"dismissed_by": "human"}, "human", data.get("confidence")),
        )
        transaction.set(ref, {"status": "dismissed", "review_reason": None}, merge=True)
        return {"status": "dismissed", "was": was}

    result = txn(db.transaction())
    if result["status"] == "missing":
        return None
    if result["status"] == "dismissed":
        log(logger, logging.INFO, "clause dismissed", clause_id=clause_id, was=result.get("was"))
        if result.get("was") != "needs_review":
            result |= _withdraw_derived_state(clause_id)
    return result


def _withdraw_derived_state(clause_id: str) -> dict:
    """Remove what an active clause produced, then re-evaluate what it touched.

    Same four kinds of derived state a document delete removes, scoped to one
    clause: the requirements it wrote on every product, and the conflicts it
    opened on either side of the pair. The clause record and its events stay —
    the audit trail is the one thing a withdrawal must not erase.
    """
    db = get_db()
    refs, product_ids = [], set()
    for snapshot in (
        db.collection("requirements")
        .where(filter=firestore.FieldFilter("clause_id", "==", clause_id))
        .stream()
    ):
        refs.append(snapshot.reference)
        product = (snapshot.to_dict() or {}).get("product_id")
        if product:
            product_ids.add(str(product))
    for field in ("clause_a", "clause_b"):
        for snapshot in (
            db.collection("conflicts")
            .where(filter=firestore.FieldFilter(field, "==", clause_id))
            .stream()
        ):
            refs.append(snapshot.reference)
    for ref in {r.path: r for r in refs}.values():
        ref.delete()

    for product_id in sorted(product_ids):
        try:
            from app.core.impact import run_impact_for_product

            run_impact_for_product(product_id)
        except Exception as exc:  # noqa: BLE001 - the withdrawal already happened
            log(
                logger, logging.WARNING, "reevaluate_after_dismiss_failed",
                product_id=product_id, error=str(exc)[:200],
            )
    summary = {"derived_removed": len(refs), "products_reevaluated": len(product_ids)}
    log(logger, logging.INFO, "clause_withdrawn", clause_id=clause_id, **summary)
    return summary


# ---------------------------------------------------------------------------
# Re-check: the queue answers itself where deterministic code now can


# A parked clause is only re-opened when the reason it was parked for is one
# that deterministic code can now settle. `judge_ambiguous` is exactly that: the
# model was asked because typed code had nothing to go on, and the guardrail has
# since been given something — the food category the row states. Low confidence
# and low authority are NOT here and must not be added: no amount of rechecking
# makes an unreadable number readable, and a person is the only thing that
# clears them.
AUTO_RECHECKABLE_REASONS = frozenset({"judge_ambiguous"})

# `substance_not_recognized` is the same shape of reason — typed code had
# nothing to go on — but it is not unconditionally recheckable, because the
# thing that was missing may still be missing. It is settled here only when
# re-running the *same* strict matcher over the substance the document stated
# now returns a name the dictionary knows. That happens for one reason: the
# dictionary learned the name. Commission Regulation (EU) 2023/2108 was read on
# 29 Aug, when nothing joined "E 249-250 Nitrites" to a recipe saying sodium
# nitrite, so 88 verbatim limits parked here; the curing-salt entries and their
# family landed two days later. Re-extracting to pick that up would spend a
# model run to re-derive text already stored verbatim.
#
# The gate matters more than the reason: when the matcher still refuses, the
# clause stays parked and a person still owns it. Nothing here relaxes the
# matcher, and nothing invents a mapping — a wrong normalization silently
# compares two different substances, which is the failure this whole module
# exists to prevent.
CONDITIONAL_RECHECK_REASON = "substance_not_recognized"


def _park_reasons(data: dict) -> set[str]:
    """Every reason one clause is parked for.

    Two fields carry them, because two things do the parking. Extraction writes
    the list (`review_reasons`) and can name several at once; reconciliation
    writes the single `review_reason` when it decides a clause needs a person.
    Reading only one of them is how a clause held for two reasons gets released
    for having settled one.
    """
    reasons = {str(r) for r in (data.get("review_reasons") or [])}
    single = data.get("review_reason")
    if single:
        reasons.add(str(single))
    return reasons


def _renormalized(data: dict) -> dict | None:
    """The corrected normalization for a clause parked as unrecognised, or None.

    None means the clause is not eligible, for either of two reasons: the strict
    matcher still does not know the name, or the name was never the only thing
    wrong with it. A clause whose unit is also unreadable stays with a person
    even once its substance resolves — settling one of two reasons settles
    nothing.

    `low_confidence_or_flagged` is the one reason allowed to sit alongside, and
    only when the clause's confidence is above the floor. It is two reasons
    wearing one name: the authority gate parks a clause when its confidence is
    too low **or** when extraction flagged it, and an unrecognised substance
    sets that flag. So a clause scoring 1.0 on every component, parked with this
    reason and no other, is not a clause anybody doubted — it is this same
    unrecognised name, seen a second time from the other side of the pipeline.
    A clause actually under the floor is refused here, because no recheck makes
    an unreadable number readable.
    """
    from app.core.extraction.candidates import _reads_as_specification
    from app.core.normalization import normalize_substance

    reasons = _park_reasons(data) - {"low_confidence_or_flagged"}
    if reasons != {CONDITIONAL_RECHECK_REASON}:
        return None
    if float(data.get("confidence") or 0) < CONFIDENCE_FLOOR:
        return None
    stated = data.get("substance")
    if not stated:
        return None
    normalized, unnormalized = normalize_substance(stated)
    if unnormalized:
        return None
    # Every gate the row would meet if it were read today, not only the one it
    # was parked for. A clause stored before `specification_not_food_limit`
    # existed carries no such reason, so releasing it on its substance alone
    # would let "Loss on drying — not more than 3 %" — a purity criterion for
    # the additive powder, with no food category and therefore comparable to
    # anything — into the graph as a food limit. A recheck must not be a way
    # into the graph that an upload today would refuse.
    if data.get("clause_type") == "numeric_limit" and _reads_as_specification(
        str(data.get("text") or "")
    ):
        return None
    # `needs_review` is cleared with the same write, and has to be: the
    # authority gate at the top of `reconcile_clause` reads that flag, so a
    # clause reopened without it would be parked again one line later, by the
    # reason it was just cleared of.
    return {
        "substance_normalized": normalized,
        "unnormalized_substance": False,
        "needs_review": False,
        "review_reasons": [],
    }


def recheck_clause(clause_id: str) -> dict:
    """Put one parked clause back through reconciliation.

    Returns `{"status": ...}` — `skipped` when the clause is not parked for a
    reason a recheck can settle, otherwise whatever reconciliation decided,
    which may be `needs_review` again. Landing back in the queue is a real
    outcome, not a failure: it means the question genuinely still needs a
    person.

    Idempotent. The reset is transactional and guarded on both the status and
    the reason, so a redelivered or double-clicked recheck reopens nothing that
    a previous pass already decided.
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
            return {"status": "skipped", "reason": "not_in_review"}
        reasons = _park_reasons(data)
        reason = data.get("review_reason") or (sorted(reasons)[0] if reasons else None)
        correction: dict = {}
        if reasons & {CONDITIONAL_RECHECK_REASON} and not (reasons & AUTO_RECHECKABLE_REASONS):
            renormalized = _renormalized(data)
            if renormalized is None:
                return {
                    "status": "skipped",
                    "reason": "still_unrecognized",
                    "review_reason": reason,
                }
            correction = renormalized
        elif not (reasons & AUTO_RECHECKABLE_REASONS):
            return {"status": "skipped", "reason": "needs_a_person", "review_reason": reason}
        event_id = new_id("evt")
        transaction.set(
            db.collection("graph_events").document(event_id),
            _event_payload(
                EventType.CLAUSE_RECHECKED, clause_id,
                {"status": "needs_review", "review_reason": reason},
                {"status": "pending_reconciliation"} | correction,
                {"rechecked_by": "guardrail"}, "recheck", data.get("confidence"),
            ),
        )
        transaction.set(
            ref,
            {"status": "pending_reconciliation", "review_reason": None} | correction,
            merge=True,
        )
        return {"status": "reopened", "review_reason": reason}

    reset = txn(db.transaction())
    if reset["status"] != "reopened":
        return reset
    outcome = reconcile_clause(clause_id)
    log(
        logger, logging.INFO, "clause_rechecked",
        clause_id=clause_id, was=reset.get("review_reason"), now=outcome.get("status"),
    )
    return outcome


def recheck_review_queue(limit: int = 500) -> dict:
    """Re-run every clause the queue is holding for a reason code can settle.

    This is the whole point of the guardrail change: thirty-six rows of one
    additive table were parked asking a person to confirm that a regulation
    does not contradict itself, and the category each row states answers that
    without a model and without a click.

    The return says what happened to all of them, including what it could not
    settle — a recheck that reported only its successes would be the same lie
    as a filter that hides its own count.
    """
    db = get_db()
    parked = [
        d.to_dict() | {"id": d.id}
        for d in db.collection("clauses")
        .where(filter=firestore.FieldFilter("status", "==", "needs_review"))
        .limit(limit)
        .stream()
    ]
    eligible = [c for c in parked if _eligible_for_recheck(c)]
    outcomes: dict[str, int] = {}
    resolved = 0
    for clause in eligible:
        result = recheck_clause(clause["id"])
        status = str(result.get("status"))
        outcomes[status] = outcomes.get(status, 0) + 1
        if status not in {"ambiguous_needs_review", "needs_review", "skipped", "missing"}:
            resolved += 1
    summary = {
        "examined": len(parked),
        "eligible": len(eligible),
        "resolved": resolved,
        "still_waiting": len(parked) - resolved,
        # Named, not just counted: a reason nothing can settle automatically is
        # the reader's next piece of work, and hiding it behind a total makes
        # the queue look shorter than it is.
        "needs_a_person": _reason_counts(c for c in parked if not _eligible_for_recheck(c)),
        "outcomes": outcomes,
    }
    log(logger, logging.INFO, "review_queue_rechecked", **{
        k: v for k, v in summary.items() if isinstance(v, int)
    })
    return summary


def _eligible_for_recheck(clause: dict) -> bool:
    """Whether a sweep should even try this clause.

    Asked with the same test `recheck_clause` applies inside its transaction,
    so the summary and the work agree: a clause counted as eligible is one that
    was actually reopened, and one counted under `needs_a_person` is one the
    dictionary still cannot read.
    """
    reasons = _park_reasons(clause)
    if reasons & AUTO_RECHECKABLE_REASONS:
        return True
    if CONDITIONAL_RECHECK_REASON in reasons:
        return _renormalized(clause) is not None
    return False


def _reason_counts(clauses) -> dict[str, int]:
    counts: dict[str, int] = {}
    for clause in clauses:
        # Both fields, for the reason `_park_reasons` exists: a clause parked by
        # extraction carries its reasons in the list and would otherwise be
        # counted as "unstated" — a queue that cannot name what it is waiting
        # for is the same silence the filter rule forbids.
        for key in sorted(_park_reasons(clause)) or ["unstated"]:
            counts[key] = counts.get(key, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Transactional verdict application


def _ends_where_the_other_starts(a: dict, b: dict) -> bool:
    """True when `a` starts on the day `b` stops — `a` is `b`'s replacement.

    The two halves of an amendment, as Annex II writes them: the replaced text
    carries "Period of application: until 9 October 2025" and the replacing
    text "from 9 October 2025". Only the `from` date is an effective date, so
    the replaced row arrives dated None and the pair looks undecidable — which
    sent one amended limit to the model as a question about which of two
    numbers is current, when the rows say so themselves.

    Read from the text, never stored, for the same reason the scope is.
    """
    from app.core.scope import applies_until

    start = str(a.get("effective_date") or "")
    ends = applies_until(b.get("text"))
    return bool(start and ends and start >= ends)


def _is_newer(a: dict, b: dict) -> bool:
    """True when `a` should replace `b` (same jurisdiction): effective_date
    first, the stated end of the other's period next, document recency last."""
    da = str(a.get("effective_date") or "")
    db_ = str(b.get("effective_date") or "")
    if da and db_ and da != db_:
        return da > db_
    if _ends_where_the_other_starts(a, b):
        return True
    if _ends_where_the_other_starts(b, a):
        return False
    return str(a.get("document_id") or "") > str(b.get("document_id")) or False


def _dates_decide(a: dict, b: dict) -> bool:
    """True when the supersede question can be settled by dates alone."""
    da = str(a.get("effective_date") or "")
    db_ = str(b.get("effective_date") or "")
    if da and db_ and da != db_:
        return True
    return _ends_where_the_other_starts(a, b) or _ends_where_the_other_starts(b, a)


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
