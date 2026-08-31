"""The fix a person could approve, drafted from state we already hold.

An alert tells someone their product breaks a rule. It does not tell them what
number to hit, in which market, or on whose authority. This module answers
that: for every substance that fails, the single number that satisfies every
market the product actually sells into, the market that sets it, and the
verbatim clauses behind each limit.

Two properties matter more than the arithmetic:

  it is read-only     nothing here writes to Firestore, publishes to Pub/Sub or
                      emits a `graph_event`. It reads `requirements`, `clauses`,
                      `products` and `markets` and returns a dict.

  it has no model     picking the strictest of several numbers is a comparison,
                      not a judgement. Same reason the Impact Engine has no
                      agent: a model that "decides" 150 < 400 can also decide
                      otherwise, and this number ends up on a page a person
                      signs off.

The third property is the one the UI depends on: silence is a failure mode
here. A market we hold no rule for is named as uncovered rather than left out
of the list, and an ingredient that produced no comparison is listed with the
reason it produced none. A quiet omission reads exactly like a pass.
"""

from __future__ import annotations

import logging

from google.cloud import firestore

from app.core import substances as substances_module
from app.core.guardrail import substances_comparable
from app.core.paging import read_capped
from app.db import get_db
from app.observability import get_trace_id, log

logger = logging.getLogger(__name__)

# Why an ingredient carries no comparison. Every ingredient on the product that
# is not behind a target gets exactly one of these, and each one is a sentence
# a reader can act on rather than an absence they have to notice.
REASON_NAME_NOT_RECOGNISED = "name_not_recognised"
REASON_FOOD_NOT_ADDITIVE = "food_not_additive"
REASON_AMOUNT_MISSING = "amount_missing"
REASON_UNIT_UNCONVERTIBLE = "unit_unconvertible"
REASON_NO_RULE = "no_rule_for_it"
REASON_NON_NUMERIC = "rule_has_no_number"
REASON_RULE_NEEDS_A_PERSON = "rule_needs_a_person"
REASON_NOT_COMPARED = "not_compared"
REASON_CLAUSE_UNIT_UNREADABLE = "rule_unit_unreadable"
REASON_CONDITIONAL = "rule_applies_only_in_one_case"

_REASON_TEXT: dict[str, str] = {
    REASON_AMOUNT_MISSING: (
        "No amount is recorded for this ingredient, so there was nothing to compare "
        "against a limit. Add the amount and it will be checked."
    ),
    # Not the ingredient's unit. The amount form offers three units and all
    # three convert (`guardrail._CONVERSIONS_TO_MG_PER_KG`), so this reason can
    # only ever be the rule's side — and telling a reader their own entry was
    # the problem sends them to correct something that was already right.
    REASON_UNIT_UNCONVERTIBLE: (
        "The rule is written in a unit that does not convert to the one your amount "
        "is in, so no comparison was made. Your entry is not the problem."
    ),
    REASON_CLAUSE_UNIT_UNREADABLE: (
        "The rule does state a number, but not in a unit we could read, so nothing "
        "was compared against it rather than a guess being made."
    ),
    REASON_CONDITIONAL: (
        "The rule applies in one named case only, and whether your product is that "
        "case is the one thing we cannot read off the label."
    ),
    REASON_NO_RULE: (
        "None of the rules we hold set a limit on this for the markets you sell into. "
        "That is not a pass — it means nothing was checked."
    ),
    REASON_NON_NUMERIC: (
        "The rules we hold for this state no number, and none of the wordings we can "
        "decide from either. These are the ones that do need a person."
    ),
    REASON_RULE_NEEDS_A_PERSON: (
        "There is a rule for this, but we are not confident enough in how it was read "
        "to compare your product against it. It is waiting in the review queue."
    ),
    REASON_NOT_COMPARED: (
        "We hold a rule for this and no comparison was made against it. Nothing here "
        "says it passed."
    ),
}

# Why a target could not be produced. `target_value` is None only with one of
# these set, and the model enforces it.
NO_TARGET_NO_COMPARABLE_LIMIT = "no_comparable_limit"

_NO_TARGET_TEXT: dict[str, str] = {
    NO_TARGET_NO_COMPARABLE_LIMIT: (
        "Every limit we hold for this is written in a unit we could not convert, so we "
        "cannot state one number that satisfies them all."
    ),
}


def build_remediation(product_id: str) -> dict | None:
    """Draft a fix plan for one product. `None` when the product does not exist.

    Read-only by construction: the only Firestore calls in this function are
    `.get()` and `.stream()`.
    """
    db = get_db()
    snapshot = db.collection("products").document(product_id).get()
    if not snapshot.exists:
        return None
    product = (snapshot.to_dict() or {}) | {"id": snapshot.id}

    market_ids = [str(m) for m in (product.get("target_markets") or [])]
    # Capped through `read_capped` rather than a bare limit: the target this
    # plan prints is the strictest limit across these rows, so a row silently
    # dropped is a fix plan recommending a number that is not strict enough.
    requirements = read_capped(
        db.collection("requirements").where(
            filter=firestore.FieldFilter("product_id", "==", product_id)
        ),
        what="requirements",
    )
    # Requirements outlive a market being removed from the product. A limit for
    # a market they no longer sell into must not tighten the number they are
    # asked to hit.
    requirements = [r for r in requirements if r.get("market_id") in set(market_ids)]

    clauses = _clauses_for(db, {r.get("clause_id") for r in requirements})
    targets = _targets(requirements, clauses, market_ids)
    not_checked = _not_checked(product, requirements)

    log(
        logger,
        logging.INFO,
        "remediation drafted",
        product_id=product_id,
        targets=len(targets),
        not_checked=len(not_checked),
    )
    return {
        "product_id": product_id,
        "product_name": product.get("name") or product_id,
        "generated_for_markets": market_ids,
        "targets": targets,
        "not_checked": not_checked,
        "trace_id": get_trace_id(),
    }


def _clauses_for(db, clause_ids: set) -> dict[str, dict]:
    """The clauses behind these requirements, keyed by id.

    Read one at a time on purpose: the set is small (one per requirement) and a
    `where in` query is capped at 30 values, which a rulebook exceeds.
    """
    found: dict[str, dict] = {}
    for clause_id in sorted(cid for cid in clause_ids if cid):
        snap = db.collection("clauses").document(str(clause_id)).get()
        if snap.exists:
            found[str(clause_id)] = (snap.to_dict() or {}) | {"id": snap.id}
    return found


def _limit_of(requirement: dict) -> float | None:
    """The limit in the unit the comparison was actually made in.

    `comparable_limit` is written by the Impact Engine only when both sides
    converted. Falling back to `limit_value` here would rank a percentage
    against a mg/kg figure and produce a target four orders of magnitude wrong.
    """
    value = requirement.get("comparable_limit")
    return float(value) if isinstance(value, int | float) else None


def _targets(
    requirements: list[dict], clauses: dict[str, dict], market_ids: list[str]
) -> list[dict]:
    """One entry per substance that fails somewhere, worst first.

    Grouping is family-aware, and it has to be. The EU limits the group
    "Benzoic acid — benzoates" while BPOM limits "natrium benzoat, computed as
    benzoic acid" — the same chemistry on a basis both documents state, which
    is why the guardrail compares them at all. Keying on the raw
    `substance_normalized` split that into two targets, each showing its own
    market's number and each announcing "we hold no rule for the other market".
    Found against live data: a product over the limit in both markets was told
    it needed 150 mg/kg for Germany and, separately, 310 mg/kg for Indonesia,
    with both marked as partial coverage. Saying we have no rule when we do is
    the same failure as saying nothing at all.
    """
    groups: dict[str, list[dict]] = {}
    for requirement in sorted(
        requirements, key=lambda r: str(r.get("substance_normalized") or "")
    ):
        substance = requirement.get("substance_normalized")
        if not substance:
            continue
        key = next(
            (k for k in groups if substances_comparable(k, str(substance))), str(substance)
        )
        groups.setdefault(key, []).append(requirement)

    targets: list[dict] = []
    for substance, group in groups.items():
        if not any(r.get("evaluation") == "fail" for r in group):
            continue  # "nothing to fix here" is a legitimate answer, not a row
        targets.append(_target(substance, group, clauses, market_ids))

    targets.sort(key=lambda t: (t["target_value"] is None, t["substance"]))
    return targets


def _target(
    substance: str, group: list[dict], clauses: dict[str, dict], market_ids: list[str]
) -> dict:
    limits: list[dict] = []
    for market_id in market_ids:
        in_market = [
            r for r in group if r.get("market_id") == market_id and _limit_of(r) is not None
        ]
        if not in_market:
            continue
        # A loaded rulebook holds several rows for one substance in one market —
        # the flavoured-drink row, the juice row. The strictest is the one that
        # decides whether they can sell; the others are counted, not dropped.
        strictest_here = min(in_market, key=lambda r: _limit_of(r))  # type: ignore[arg-type]
        clause = clauses.get(str(strictest_here.get("clause_id") or ""), {})
        limits.append(
            {
                "market_id": market_id,
                "limit": _limit_of(strictest_here),
                "unit": strictest_here.get("comparable_unit"),
                "clause_id": strictest_here.get("clause_id"),
                "document_id": strictest_here.get("document_id"),
                "effective_date": clause.get("effective_date"),
                "quote": clause.get("text"),
                "citation_href": (
                    f"/documents/{strictest_here.get('document_id')}"
                    f"?cite={strictest_here.get('clause_id')}"
                    if strictest_here.get("document_id")
                    else None
                ),
                "other_limits_in_market": len(in_market) - 1,
                "is_strictest": False,
            }
        )

    markets_without_rules = [m for m in market_ids if all(x["market_id"] != m for x in limits)]

    target_value: float | None = None
    target_unit: str | None = None
    strictest_market_id: str | None = None
    no_target_reason: str | None = NO_TARGET_NO_COMPARABLE_LIMIT
    if limits:
        strictest = min(limits, key=lambda x: x["limit"])
        strictest["is_strictest"] = True
        target_value = strictest["limit"]
        target_unit = strictest["unit"]
        strictest_market_id = strictest["market_id"]
        no_target_reason = None

    # What the product holds today, in the unit the target is stated in. The
    # raw amount the user typed is kept beside it: 0.02 shown under a mg/kg
    # heading is the four-orders-of-magnitude bug the product page already fixed
    # once, and this page must not reintroduce it.
    failing = next((r for r in group if r.get("evaluation") == "fail"), group[0])
    current = failing.get("comparable_value")
    severity_rank = {"fail": 0, "needs_review": 1, "pass": 2}
    verdict_today = sorted(
        (r.get("evaluation") or "needs_review" for r in group),
        key=lambda e: severity_rank.get(e, 1),
    )[0]

    return {
        "substance": substance,
        "substance_label": substances_module.label_for(substance),
        "target_value": target_value,
        "target_unit": target_unit,
        "no_target_reason": no_target_reason,
        "no_target_reason_text": _NO_TARGET_TEXT.get(no_target_reason or "", "")
        if no_target_reason
        else "",
        "coverage": "full" if not markets_without_rules else "partial",
        "markets_without_rules": markets_without_rules,
        "strictest_market_id": strictest_market_id,
        "current_value": float(current) if isinstance(current, int | float) else None,
        "current_unit": failing.get("comparable_unit"),
        "raw_value": failing.get("product_value"),
        "raw_unit": failing.get("product_unit"),
        "verdict_today": verdict_today,
        "limits": limits,
    }


def _not_checked(product: dict, requirements: list[dict]) -> list[dict]:
    """Every ingredient that no target speaks for, and why.

    An ingredient list that quietly loses its unrecognised entries reads like a
    clean bill of health. `core.substances` already owns the vocabulary for
    "that is a food" and "we do not know that name"; this reuses it rather than
    writing a second set of words for the same refusals.
    """
    compared = {"pass", "fail"}
    out: list[dict] = []
    for ingredient in product.get("ingredients") or []:
        name = str(ingredient.get("name") or "").strip()
        if not name:
            continue
        normalized = ingredient.get("normalized")
        mine = [
            r
            for r in requirements
            if substances_comparable(normalized, r.get("substance_normalized"))
        ]
        if any(r.get("evaluation") in compared for r in mine):
            continue  # it was actually compared against a number

        resolution = substances_module.resolve(name)
        if not resolution.recognised and resolution.kind in {"unknown", "function"}:
            reason_code, reason_text = REASON_NAME_NOT_RECOGNISED, resolution.message
        elif resolution.kind == "food":
            reason_code, reason_text = REASON_FOOD_NOT_ADDITIVE, resolution.message
        elif ingredient.get("amount") is None:
            reason_code, reason_text = REASON_AMOUNT_MISSING, _REASON_TEXT[REASON_AMOUNT_MISSING]
        elif any(r.get("reason") == "unit_unconvertible" for r in mine):
            reason_code = REASON_UNIT_UNCONVERTIBLE
            reason_text = _REASON_TEXT[REASON_UNIT_UNCONVERTIBLE]
        elif any(r.get("reason") == "clause_unit_unreadable" for r in mine):
            reason_code = REASON_CLAUSE_UNIT_UNREADABLE
            reason_text = _REASON_TEXT[REASON_CLAUSE_UNIT_UNREADABLE]
        elif any(r.get("reason") == "conditional_permission" for r in mine):
            reason_code = REASON_CONDITIONAL
            reason_text = _REASON_TEXT[REASON_CONDITIONAL]
        elif any(r.get("reason") == "non_numeric_clause" for r in mine):
            reason_code, reason_text = REASON_NON_NUMERIC, _REASON_TEXT[REASON_NON_NUMERIC]
        elif any(r.get("reason") == "clause_confidence_below_0_5" for r in mine):
            reason_code = REASON_RULE_NEEDS_A_PERSON
            reason_text = _REASON_TEXT[REASON_RULE_NEEDS_A_PERSON]
        elif not mine:
            reason_code, reason_text = REASON_NO_RULE, _REASON_TEXT[REASON_NO_RULE]
        else:
            # A rule exists and no comparison came out of it for a reason we do
            # not have a sentence for. Saying "no rule covers this" here would
            # be a wrong sentence, which is worse than a general true one.
            reason_code, reason_text = REASON_NOT_COMPARED, _REASON_TEXT[REASON_NOT_COMPARED]

        out.append({"ingredient": name, "reason_code": reason_code, "reason_text": reason_text})
    return out
