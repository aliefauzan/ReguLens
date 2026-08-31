"""The Impact Engine.

clause changed → requirements referencing it → products → markets →
re-evaluate → status rollup → alert. Pure deterministic traversal; there is no
model call in this module and the submission says so plainly.
"""

from __future__ import annotations

import logging
from datetime import date

from google.cloud import firestore

from app.core.guardrail import product_types_comparable, substances_comparable, to_mg_per_kg
from app.core.repository import write_with_event
from app.db import get_db
from app.models import EventType
from app.observability import log

logger = logging.getLogger(__name__)


def clauses_active() -> list[dict]:
    docs = (
        get_db()
        .collection("clauses")
        .where(filter=firestore.FieldFilter("status", "in", ["active", "conflicted"]))
        .limit(200)
        .stream()
    )
    return [d.to_dict() | {"id": d.id} for d in docs]


def markets_all() -> list[dict]:
    return [
        d.to_dict() | {"id": d.id}
        for d in get_db().collection("markets").limit(20).stream()
    ]


def products_all() -> list[dict]:
    return [
        d.to_dict() | {"id": d.id}
        for d in get_db().collection("products").limit(50).stream()
    ]


# ---------------------------------------------------------------------------
# Materialization: this clause binds this product in this market


# Every field a reader is shown. The comparison decides the verdict, but these
# are what the screen quotes back, so a change in any of them is a real change.
#
# This set used to be only {limit_value, evaluation, severity, clause_id}, which
# made an edit invisible whenever it did not flip the verdict: correcting an
# ingredient from 300 to 100 mg/kg left "Your product has 300 mg per kg" on the
# page under a limit of 400, because the requirement still passed and so was
# never rewritten. A stale number presented as current is worse than no number.
REPORTED_FIELDS = frozenset(
    {
        "clause_id",
        "limit_value",
        "unit",
        "effective_date",
        "evaluation",
        "severity",
        "reason",
        "product_value",
        "product_unit",
        "comparable_value",
        "comparable_limit",
        "comparable_unit",
    }
)


def requirement_changed(before: dict, payload: dict) -> bool:
    """True when a stored requirement differs from a freshly evaluated one in
    any field the UI shows. Timestamps are excluded deliberately: they always
    differ, and writing on them would put a meaningless event in the audit
    trail on every re-run."""
    return any(before.get(field) != payload.get(field) for field in REPORTED_FIELDS)


def clause_binds(product: dict, clause: dict, market: dict) -> bool:
    """Does this rule apply to this product in this market?

    Named and shared rather than inlined, because the what-if simulator has to
    answer it exactly as the verdict engine does. A simulator that binds a
    different set of rules than the engine is not a preview of anything.
    """
    jurisdictions = {str(j).upper() for j in market.get("jurisdictions", [])}
    if str(clause.get("jurisdiction") or "").upper() not in jurisdictions:
        return False
    numeric = clause.get("clause_type") == "numeric_limit"
    # Family-aware bind: a clause limiting "benzoic acid — benzoates" binds a
    # product containing sodium benzoate (same documented basis).
    matches = any(
        substances_comparable(clause.get("substance_normalized"), i.get("normalized"))
        for i in product.get("ingredients", [])
    )
    if numeric and not matches:
        return False  # numeric limits bind only via a matching ingredient
    # ...and only when the rule was written for this kind of product. The
    # bundled library carries limits for every food category, so a benzoate
    # limit for dairy desserts would otherwise be applied to a drink powder and
    # fail it on a rule that does not cover it.
    if numeric and not product_types_comparable(
        clause.get("product_type"), product.get("product_type")
    ):
        return False
    return True


def materialize_for_product(product_id: str) -> list[dict]:
    """Create/update `requirements` for one product across its target markets.

    Requirements are keyed (product_id, market_id, clause_id) and updated in
    place — never duplicated.
    """
    db = get_db()
    product = next(
        (p for p in products_all() if p["id"] == product_id), None
    )
    if product is None:
        return []
    markets = [m for m in markets_all() if m["id"] in set(product.get("target_markets") or [])]
    active = clauses_active()
    requirements: list[dict] = []
    for market in markets:
        for clause in active:
            if not clause_binds(product, clause, market):
                continue
            key = f"{product_id}:{market['id']}:{clause['id']}"
            evaluation = evaluate(product, clause)
            existing = (
                db.collection("requirements")
                .where(filter=firestore.FieldFilter("requirement_key", "==", key))
                .limit(1)
                .stream()
            )
            existing_list = list(existing)
            req_ref = None
            before = None
            if existing_list:
                snap = existing_list[0]
                req_ref = db.collection("requirements").document(snap.id)
                before = snap.to_dict()
            payload = {
                "workspace_id": "ws_demo",
                "requirement_key": key,
                "product_id": product_id,
                "market_id": market["id"],
                "jurisdiction": clause.get("jurisdiction"),
                "clause_id": clause["id"],
                "document_id": clause.get("document_id"),
                "requirement_type": clause.get("clause_type"),
                "substance_normalized": clause.get("substance_normalized"),
                "limit_value": clause.get("limit_value"),
                "unit": clause.get("unit"),
                # The date the clause itself states. Read at rollup, not here: a
                # requirement that does not bind yet is still evaluated and
                # still shown, it is only counted into a different total.
                "effective_date": clause.get("effective_date"),
                "product_value": evaluation["product_value"],
                "product_unit": evaluation["product_unit"],
                "comparable_value": evaluation["comparable_value"],
                "comparable_limit": evaluation["comparable_limit"],
                "comparable_unit": evaluation["comparable_unit"],
                "evaluation": evaluation["evaluation"],
                "severity": evaluation["severity"],
                "reason": evaluation["reason"],
                "status": "active",
                "evaluated_at": firestore.SERVER_TIMESTAMP,
            }
            if before is None:
                event_type = EventType.REQUIREMENT_CREATED
                after_payload = payload
            elif not requirement_changed(before, payload):
                requirements.append({**before, "id": snap.id})
                continue  # idempotent: unchanged requirement writes nothing
            else:
                event_type = EventType.REQUIREMENT_CHANGED
                after_payload = {**before, **payload}
            write_with_event(
                "requirements",
                (req_ref.id if req_ref else key.replace(":", "_")),
                payload | ({} if before is None else {"updated_at": firestore.SERVER_TIMESTAMP}),
                event_type=event_type,
                entity_type="requirement",
                before=before,
                after=after_payload,
                triggered_by="impact_engine",
                cause={
                    "clause_id": clause["id"],
                    "document_id": clause.get("document_id"),
                    "market_id": market["id"],
                },
                confidence=clause.get("confidence"),
                merge=True,
            )
            requirements.append(payload | {"id": (req_ref.id if req_ref else key.replace(":", "_"))})
    _retire_orphans(product_id, {c["id"] for c in active})
    return requirements


def _retire_orphans(product_id: str, active_clause_ids: set[str]) -> int:
    """Remove requirements whose clause is no longer active.

    A requirement is a rule applied to a product; when the rule stops being the
    one in effect, so does the requirement. Nothing removed them, so a clause
    superseded by its own replacement kept failing the product on the limit it
    had just been replaced by — and kept the value the product held when that
    requirement was last written, because materialization only revisits clauses
    that are still active.

    Seen in production: a cured sausage reformulated to 20 mg/kg stayed
    `non_compliant` against `E 249-250 Nitrites 100`, superseded minutes
    earlier, recorded against the 120 mg/kg the recipe no longer contained.
    That is the same error as quoting a superseded limit, which `rollup_status`
    already refuses to do — arriving through the requirement instead of the
    clause.

    The clause and its events survive; only the derived row goes.
    """
    db = get_db()
    stale = [
        snapshot
        for snapshot in (
            db.collection("requirements")
            .where(filter=firestore.FieldFilter("product_id", "==", product_id))
            .limit(500)
            .stream()
        )
        if str((snapshot.to_dict() or {}).get("clause_id") or "") not in active_clause_ids
    ]
    for snapshot in stale:
        snapshot.reference.delete()
    if stale:
        log(
            logger, logging.INFO, "requirements_retired",
            product_id=product_id, count=len(stale),
        )
    return len(stale)


# ---------------------------------------------------------------------------
# When a rule binds


def _parse_date(value: object) -> date | None:
    """A stored `effective_date` as a date, or None when there is not one to
    read. Anything unreadable is None and says so in the log."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        log(logger, logging.WARNING, "effective_date unparseable", value=str(value)[:32])
        return None


def _in_force(effective_date: object, as_of: date) -> bool:
    """True when a clause binds on `as_of`.

    Absent means in force. Most stored clauses carry no date, and treating that
    as "not yet" would hide every limit the system already knows about.

    Unreadable also means in force. Failing open keeps a real limit on screen;
    failing closed would drop a rule from the verdict because a string was
    malformed, which is the failure this system is least allowed to have.
    """
    parsed = _parse_date(effective_date)
    return parsed is None or parsed <= as_of


def _requirements_for(product_id: str) -> list[dict]:
    return [
        d.to_dict() | {"id": d.id}
        for d in (
            get_db()
            .collection("requirements")
            .where(filter=firestore.FieldFilter("product_id", "==", product_id))
            .limit(200)
            .stream()
        )
    ]


def _status_from(requirements: list[dict]) -> str:
    """The verdict a set of requirements adds up to. Worst wins."""
    evaluations = {r.get("evaluation") for r in requirements}
    if not requirements:
        return "unknown"
    if "fail" in evaluations:
        return "non_compliant"
    if "needs_review" in evaluations:
        return "attention_required"
    return "compliant"


def _target_markets(product_id: str) -> list[dict]:
    product = next((p for p in products_all() if p["id"] == product_id), None)
    if product is None:
        return []
    return [m for m in markets_all() if m["id"] in set(product.get("target_markets") or [])]


def rollup_status(product_id: str, as_of: date | None = None) -> dict[str, str]:
    """Per-market compliance status for one product, as of a date.

    Only rules in force on that date count. A limit that enters into force next
    year does not make a product illegal today, and saying it does is the same
    class of error as quoting a superseded limit: a confident verdict drawn from
    a rule that is not the one in effect.
    """
    as_of = as_of or date.today()
    statuses: dict[str, str] = {}
    requirements = _requirements_for(product_id)
    for market in _target_markets(product_id):
        market_reqs = [r for r in requirements if r.get("market_id") == market["id"]]
        if not market_reqs:
            statuses[market["id"]] = "unknown"
            continue
        binding = [r for r in market_reqs if _in_force(r.get("effective_date"), as_of)]
        # Rules exist for this market and every one of them starts later. Today
        # nothing they say is broken, so the verdict is `compliant` rather than
        # `unknown` — "we have read no regulation" would be false. The date it
        # changes is carried by `upcoming_changes`, not hidden.
        statuses[market["id"]] = _status_from(binding) if binding else "compliant"
    return statuses


def _culprit(market_reqs: list[dict], when: date, status: str) -> dict:
    """The requirement that starts on `when` and explains the new verdict.

    Worst first, so the row named is the one that decides the status rather than
    whichever happened to be written first.
    """
    starting = [r for r in market_reqs if _parse_date(r.get("effective_date")) == when]
    rank = {"fail": 0, "needs_review": 1, "pass": 2}
    starting.sort(key=lambda r: rank.get(r.get("evaluation"), 3))
    return starting[0] if starting else {}


def _deciding(product_id: str, market_id: str, as_of: date | None = None) -> dict:
    """The requirement that the new verdict actually rests on.

    `run_impact` knows which clause *triggered* the re-evaluation, and that is
    not always the clause that *decided* it. One regulation can carry both, and
    Commission Regulation (EU) 2023/2108 does: reconciling its nitrates row set
    a sausage to `non_compliant` on its nitrites row, and the alert read "it
    sets nitrates at 150 mg/kg" above a verdict about 30 mg/kg of nitrites.
    Same regulation, wrong sentence.

    Worst first, and only rules in force, so the row named is the one that
    settles the status — the same rule `_status_from` applies, asked for the
    row instead of the word.
    """
    as_of = as_of or date.today()
    in_force = [
        r
        for r in _requirements_for(product_id)
        if r.get("market_id") == market_id and _in_force(r.get("effective_date"), as_of)
    ]
    rank = {"fail": 0, "needs_review": 1, "pass": 2}
    in_force.sort(key=lambda r: rank.get(r.get("evaluation"), 3))
    return in_force[0] if in_force else {}


def upcoming_changes(product_id: str, as_of: date | None = None) -> dict[str, dict]:
    """Per market, the next date the verdict changes and what it changes to.

    Empty for a market whose future rules do not move the verdict — a rule
    arriving in March that the product already satisfies is not a deadline, and
    presenting it as one trains people to ignore the ones that are.
    """
    as_of = as_of or date.today()
    requirements = _requirements_for(product_id)
    upcoming: dict[str, dict] = {}
    for market in _target_markets(product_id):
        market_id = market["id"]
        market_reqs = [r for r in requirements if r.get("market_id") == market_id]
        # Today's verdict for this market, from the rows already in hand rather
        # than by asking Firestore for them a second time.
        binding_now = [r for r in market_reqs if _in_force(r.get("effective_date"), as_of)]
        now = _status_from(binding_now) if binding_now else "compliant"
        future_dates = sorted(
            {
                d
                for r in market_reqs
                if (d := _parse_date(r.get("effective_date"))) is not None and d > as_of
            }
        )
        for when in future_dates:
            binding = [r for r in market_reqs if _in_force(r.get("effective_date"), when)]
            status = _status_from(binding) if binding else "compliant"
            if status != now:
                # Which rule sets the deadline. Carried because an alert that
                # cannot name its cause is indistinguishable from one whose
                # cause was deleted, and the UI says so out loud.
                culprit = _culprit(market_reqs, when, status)
                upcoming[market_id] = {
                    "effective_date": when.isoformat(),
                    "status": status,
                    "clause_id": culprit.get("clause_id"),
                    "document_id": culprit.get("document_id"),
                }
                break
    return upcoming


def _apply_upcoming(
    product_id: str,
    statuses: dict[str, str],
    cause: dict | None = None,
) -> dict[str, dict]:
    """Persist the product's scheduled verdicts and record what moved.

    Written through the same event path as every other mutation, so a deadline
    that appeared overnight is in the audit trail next to the ingestion that
    created it. Which of these events becomes an alert is `alerts.worsened`'s
    decision, not this module's.
    """
    from app.core.alerts import SEVERITY

    upcoming = upcoming_changes(product_id)
    snapshot = get_db().collection("products").document(product_id).get()
    stored = (snapshot.to_dict() or {}).get("compliance_upcoming") or {}
    moved = [m for m in set(stored) | set(upcoming) if stored.get(m) != upcoming.get(m)]
    for market_id in sorted(moved):
        entry = upcoming.get(market_id)
        write_with_event(
            "products",
            product_id,
            {"compliance_upcoming": upcoming, "updated_at": firestore.SERVER_TIMESTAMP},
            event_type=EventType.PRODUCT_STATUS_SCHEDULED,
            entity_type="product",
            before={"market": market_id, "status": statuses.get(market_id)},
            # A cleared entry is a real transition too — the date arrived, or the
            # rule that set it was superseded. `status: None` scores zero in
            # SEVERITY, so it lands in the trail without raising an alert.
            after={
                "market": market_id,
                "status": (entry or {}).get("status"),
                "effective_date": (entry or {}).get("effective_date"),
            },
            triggered_by="impact_engine",
            # The clause that sets the deadline beats whatever triggered the
            # re-evaluation: a reader asking "why" means the rule, not the run.
            cause={
                "clause_id": (entry or {}).get("clause_id"),
                "document_id": (entry or {}).get("document_id"),
            }
            if entry
            else cause,
            merge=True,
        )
        log(
            logger, logging.INFO, "status_scheduled",
            product_id=product_id, market_id=market_id,
            status=(entry or {}).get("status"),
            effective_date=(entry or {}).get("effective_date"),
            worse=SEVERITY.get((entry or {}).get("status"), 0) > SEVERITY.get(statuses.get(market_id), 0),
        )
    return upcoming


def _cause_of(
    product_id: str, market_id: str, clause_id: str | None, document_id: str | None
) -> dict:
    """The deciding rule where there is one, the triggering rule otherwise."""
    deciding = _deciding(product_id, market_id)
    if deciding.get("clause_id"):
        return {
            "clause_id": deciding.get("clause_id"),
            "document_id": deciding.get("document_id"),
        }
    if clause_id or document_id:
        return {"clause_id": clause_id, "document_id": document_id}
    # Nothing decides and nothing triggered: an empty cause, so the alert says
    # it cannot name one rather than storing two nulls that read as a cause.
    return {}


def run_impact(clause_id: str | None, document_id: str | None) -> dict:
    """`graph.changed` consumer. Re-evaluates every product; idempotent because
    unchanged requirements write nothing and status events fire only on actual
    transitions."""
    summary: dict = {"products": {}}
    for product in products_all():
        materialize_for_product(product["id"])
        new_statuses = rollup_status(product["id"])
        previous = _previous_status(product["id"])
        for market_id, new_status in new_statuses.items():
            old_status = previous.get(market_id)
            if old_status != new_status:
                merged = dict(previous)
                merged[market_id] = new_status
                write_with_event(
                    "products",
                    product["id"],
                    {"compliance_status": merged, "updated_at": firestore.SERVER_TIMESTAMP},
                    event_type=EventType.PRODUCT_STATUS_CHANGED,
                    entity_type="product",
                    before={"market": market_id, "status": old_status},
                    after={"market": market_id, "status": new_status},
                    triggered_by="impact_engine",
                    # The rule the verdict rests on, not the one whose arrival
                    # started the run. They are usually the same and the alert
                    # quotes whichever it is given, so when they differ the
                    # wrong one is a sentence that contradicts the verdict
                    # printed beside it.
                    cause=_cause_of(product["id"], market_id, clause_id, document_id),
                    merge=True,
                )
                log(
                    logger, logging.INFO, "status_changed",
                    product_id=product["id"], market_id=market_id,
                    before=old_status, after=new_status,
                )
        _apply_upcoming(
            product["id"],
            new_statuses,
            cause={"clause_id": clause_id, "document_id": document_id},
        )
        summary["products"][product["id"]] = new_statuses
    return summary


def _previous_status(product_id: str) -> dict[str, str | None]:
    """Read the stored per-market compliance map from the product doc."""
    snap = get_db().collection("products").document(product_id).get()
    return (snap.to_dict() or {}).get("compliance_status") or {}


def run_impact_for_product(product_id: str) -> dict:
    """Product create/update hook: materialize + evaluate + rollup."""
    materialize_for_product(product_id)
    statuses = rollup_status(product_id)
    db = get_db()
    snap = db.collection("products").document(product_id).get()
    previous = (snap.to_dict() or {}).get("compliance_status") or {}
    changed = {m: s for m, s in statuses.items() if previous.get(m) != s}
    for market_id, new_status in changed.items():
        write_with_event(
            "products",
            product_id,
            {"compliance_status": statuses},
            event_type=EventType.PRODUCT_STATUS_CHANGED,
            entity_type="product",
            before={"market": market_id, "status": previous.get(market_id)},
            after={"market": market_id, "status": new_status},
            triggered_by="impact_engine",
            # A verdict that moved because the recipe changed still rests on a
            # rule, and the alert has a sentence for a cause it cannot find:
            # "the rule behind this has since been removed". Nothing was
            # removed — the cause was never recorded. `_cause_of` returns None
            # only when the market genuinely has no rule in force, which is the
            # one case that sentence is true for.
            cause=_cause_of(product_id, market_id, None, None) or None,
            merge=True,
        )
    if changed:
        db.collection("products").document(product_id).set(
            {"compliance_status": statuses}, merge=True
        )
    upcoming = _apply_upcoming(product_id, statuses)
    return {"statuses": statuses, "changed": changed, "upcoming": upcoming}


# ---------------------------------------------------------------------------
# Evaluation — deterministic, no model


def evaluate(product: dict, requirement_clause: dict) -> dict:
    """Evaluate one clause against one product.

    Returns the raw amount as the user entered it AND the converted value the
    comparison actually used. Reporting `product_value` next to the clause's
    unit — 0.02 alongside a mg/kg limit when the ingredient was given as 0.02%
    — states a number that is off by four orders of magnitude, which is worse
    than saying nothing.
    """
    ingredient = next(
        (
            i for i in product.get("ingredients", [])
            if substances_comparable(i.get("normalized"), requirement_clause.get("substance_normalized"))
        ),
        None,
    )
    amount = ingredient.get("amount") if ingredient else None
    comparable_value: float | None = None
    comparable_limit: float | None = None

    if requirement_clause.get("clause_type") != "numeric_limit":
        result = "needs_review"
        reason = "non_numeric_clause"
    elif amount is None:
        result = "needs_review"
        reason = "product_amount_unknown"
    elif to_mg_per_kg(amount, ingredient.get("unit")) is None or \
            to_mg_per_kg(requirement_clause.get("limit_value"), requirement_clause.get("unit")) is None:
        result = "needs_review"
        reason = "unit_unconvertible"
    else:
        pv = to_mg_per_kg(amount, ingredient.get("unit"))
        lv = to_mg_per_kg(requirement_clause.get("limit_value"), requirement_clause.get("unit"))
        result = "pass" if pv <= lv else "fail"
        reason = None
        comparable_value = pv
        comparable_limit = lv

    if (requirement_clause.get("confidence") or 0) < 0.5 and result != "needs_review":
        result = "needs_review"
        reason = "clause_confidence_below_0_5"

    severity = {"fail": "high", "needs_review": "medium", "pass": "low"}.get(result, "medium")
    return {
        "evaluation": result,
        "severity": severity,
        "product_value": amount,
        "product_unit": (ingredient or {}).get("unit"),
        # Both sides in one unit, so a reader can see the comparison that was
        # actually made rather than being asked to trust it.
        "comparable_value": comparable_value,
        "comparable_limit": comparable_limit,
        "comparable_unit": "mg_per_kg" if comparable_value is not None else None,
        "reason": reason,
    }