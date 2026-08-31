"""Which rules could touch what this workspace actually makes.

The review queue reached two hundred entries the day watched sources started
reading whole regulations, and every one of them was the guardrail behaving
correctly: an EU nitrite limit for cured meats is a real rule, read accurately,
which nobody could confirm because nothing in the workspace is a cured meat. A
queue like that is not a safety feature. It is a queue nobody reads, and an
unread queue is worse than a short one because it hides the three entries that
mattered.

Three commitments hold this to something honest:

**Nothing is deleted and nothing is downgraded.** Relevance is computed when a
list is read, never written to a clause. A rule filtered out today is in the
graph, is `active` if reconciliation made it active, and is evaluated against
any product added tomorrow without a migration or a recompute. There is no
stored flag to go stale.

**Irrelevant is not the same as wrong.** The reasons below say "nothing you make
contains this", never "this rule is incorrect". The distinction is the whole
point: the app has no opinion on a regulation it cannot apply.

**Silence is never the answer.** Every caller gets the count of what was held
back and why, so the UI can say "148 rules are not shown because nothing you
sell is affected" rather than quietly showing twelve.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.guardrail import substances_comparable
from app.observability import log

logger = logging.getLogger(__name__)


# Machine tokens. The UI owns the sentences, exactly as it does for every other
# status word in the system.
NO_MARKET = "no_market"
SUBSTANCE_ABSENT = "substance_absent"
PRODUCT_TYPE_ABSENT = "product_type_absent"
RELEVANT = "relevant"
NO_PRODUCTS = "no_products"


@dataclass
class Workspace:
    """What this workspace makes, reduced to the three things a rule is matched
    on. Built once per request and reused across every clause in the list."""

    jurisdictions: set[str] = field(default_factory=set)
    substances: set[str] = field(default_factory=set)
    product_types: set[str] = field(default_factory=set)
    product_count: int = 0

    @property
    def empty(self) -> bool:
        return self.product_count == 0


@dataclass
class Verdict:
    relevant: bool
    reason: str


def build_workspace(products: list[dict[str, Any]], markets: list[dict[str, Any]]) -> Workspace:
    """Collapse the product list into what it can be matched against.

    Ingredients that normalization did not recognise are deliberately *not*
    added. An unrecognised name matches no clause anyway, and pretending
    otherwise here would quietly widen the filter on exactly the products whose
    ingredients the app already admits it cannot check.
    """
    by_id = {market["id"]: market for market in markets}
    workspace = Workspace()
    for product in products:
        workspace.product_count += 1
        if product.get("product_type"):
            workspace.product_types.add(str(product["product_type"]))
        for market_id in product.get("target_markets") or []:
            market = by_id.get(market_id)
            for jurisdiction in (market or {}).get("jurisdictions") or []:
                workspace.jurisdictions.add(str(jurisdiction).upper())
        for ingredient in product.get("ingredients") or []:
            normalized = ingredient.get("normalized")
            if normalized:
                workspace.substances.add(str(normalized))
    return workspace


def assess(clause: dict[str, Any], workspace: Workspace) -> Verdict:
    """Could this clause ever bear on something in this workspace?

    Deliberately generous. Every uncertainty resolves to `relevant`, because the
    cost of hiding a rule that mattered is a wrong verdict, while the cost of
    showing one that did not is a line of text. In particular a clause that
    names no substance and no product type is shown: a labelling or
    documentation requirement usually applies across a category, and there is
    nothing in it to rule out.
    """
    # An empty workspace has nothing to be irrelevant to. Filtering here would
    # empty the rulebook for a brand-new user, which is the one moment they most
    # need to see that the app knows something.
    if workspace.empty:
        return Verdict(True, NO_PRODUCTS)

    jurisdiction = str(clause.get("jurisdiction") or "").upper()
    if jurisdiction and workspace.jurisdictions and jurisdiction not in workspace.jurisdictions:
        return Verdict(False, NO_MARKET)

    substance = clause.get("substance_normalized")
    if substance:
        # The documented family equivalence, reused rather than re-derived: EU
        # limits the benzoate group where BPOM names natrium benzoat, and a
        # workspace holding one is affected by a rule naming the other.
        if not any(
            substance == held or substances_comparable(substance, held)
            for held in workspace.substances
        ):
            return Verdict(False, SUBSTANCE_ABSENT)

    product_type = clause.get("product_type")
    # An unstated product type is the documented wildcard — it binds. Only an
    # explicit type this workspace does not make rules the clause out.
    if product_type and workspace.product_types:
        if str(product_type) not in workspace.product_types:
            return Verdict(False, PRODUCT_TYPE_ABSENT)

    return Verdict(True, RELEVANT)


def partition(
    clauses: list[dict[str, Any]], workspace: Workspace
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Split a clause list into what bears on this workspace and a tally of why
    the rest does not. The tally is not optional — a caller that shows the first
    list without the second is hiding rules silently."""
    kept: list[dict[str, Any]] = []
    held_back: dict[str, int] = {}
    for clause in clauses:
        verdict = assess(clause, workspace)
        if verdict.relevant:
            kept.append(clause)
        else:
            held_back[verdict.reason] = held_back.get(verdict.reason, 0) + 1
    if held_back:
        log(
            logger, logging.INFO, "clauses filtered by relevance",
            shown=len(kept), hidden=sum(held_back.values()), reasons=held_back,
        )
    return kept, held_back


def current_workspace() -> Workspace:
    """The workspace as it stands right now, read fresh.

    Read at request time on purpose. A stored relevance flag would be wrong the
    moment somebody adds a product, and it would be wrong silently — the new
    product would be evaluated against rules the queue had already decided not
    to mention.
    """
    from app.core import markets as markets_core
    from app.core import products as products_core

    products = [p.model_dump(mode="json") for p in products_core.list_products()]
    return build_workspace(products, markets_core.list_markets())
