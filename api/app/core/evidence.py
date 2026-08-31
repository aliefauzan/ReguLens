"""The pack somebody hands an auditor.

A compliance officer asked "why does it say that" cannot answer with a
screenshot. They need, for every verdict: the rule as the regulator wrote it,
where the document came from, when it was read, what the system compared, and
proof that the file behind the quote is the file that was read.

Every one of those facts is already stored — this module does no new work and
makes no new claim. It reads `products`, `requirements`, `clauses`, `documents`
and `graph_events`, and lays them out in the order a person checking the work
would want them.

Two deliberate refusals:

* Nothing here is signed. The pack carries content hashes — the stored hash of
  each source document, and a hash over the pack itself — which prove the file
  has not changed since it was read. It does not prove who produced the pack,
  and calling it "signed" would claim exactly that.
* A verdict whose clause or document has since been deleted is included and
  marked, not dropped. A pack that quietly omits the parts it cannot support is
  worse than one that admits them.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from google.cloud import firestore

from app.core.paging import read_capped
from app.db import get_db
from app.observability import log

logger = logging.getLogger(__name__)


def _by_id(collection: str, ids: set[str]) -> dict[str, dict]:
    db = get_db()
    found: dict[str, dict] = {}
    for entity_id in sorted(i for i in ids if i):
        snapshot = db.collection(collection).document(entity_id).get()
        if snapshot.exists:
            found[entity_id] = snapshot.to_dict() or {}
    return found


def _json_safe(value: Any) -> Any:
    """Firestore timestamps and sentinels are not JSON. Everything the pack
    shows a reader has to survive being written to a file."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def build(product_id: str) -> dict[str, Any]:
    """Every fact behind one product's verdicts, in one document."""
    db = get_db()
    product_snapshot = db.collection("products").document(product_id).get()
    if not product_snapshot.exists:
        raise KeyError(product_id)
    product = product_snapshot.to_dict() or {}

    # This module refuses to drop a verdict whose clause was deleted; dropping
    # one because it was the five-hundred-and-first row would be the same
    # omission arriving through the query instead.
    requirements = read_capped(
        db.collection("requirements").where(
            filter=firestore.FieldFilter("product_id", "==", product_id)
        ),
        what="requirements",
    )
    clauses = _by_id("clauses", {r.get("clause_id") for r in requirements})
    documents = _by_id(
        "documents",
        {r.get("document_id") for r in requirements}
        | {c.get("document_id") for c in clauses.values()},
    )
    events = sorted(
        (
            e
            for e in read_capped(
                db.collection("graph_events").where(
                    filter=firestore.FieldFilter("entity_id", "==", product_id)
                ),
                what="graph_events",
            )
        ),
        key=lambda e: str(e.get("occurred_at") or ""),
    )

    findings: list[dict[str, Any]] = []
    for requirement in sorted(requirements, key=lambda r: str(r.get("requirement_key"))):
        clause = clauses.get(requirement.get("clause_id"))
        document = documents.get(requirement.get("document_id") or (clause or {}).get("document_id"))
        findings.append(
            {
                "market_id": requirement.get("market_id"),
                "jurisdiction": requirement.get("jurisdiction"),
                "substance": requirement.get("substance_normalized"),
                "verdict": requirement.get("evaluation"),
                "reason": requirement.get("reason"),
                "effective_date": requirement.get("effective_date"),
                # The comparison as it was actually made, in one unit, so a
                # reader checks arithmetic instead of trusting a badge.
                "comparison": {
                    "product_value": requirement.get("comparable_value"),
                    "limit": requirement.get("comparable_limit"),
                    "unit": requirement.get("comparable_unit"),
                    "product_value_as_entered": requirement.get("product_value"),
                    "product_unit_as_entered": requirement.get("product_unit"),
                    "limit_as_written": requirement.get("limit_value"),
                    "limit_unit_as_written": requirement.get("unit"),
                },
                "rule": {
                    "clause_id": requirement.get("clause_id"),
                    "available": clause is not None,
                    "text": (clause or {}).get("text"),
                    "clause_type": (clause or {}).get("clause_type"),
                    "status": (clause or {}).get("status"),
                    "confidence": (clause or {}).get("confidence"),
                    "confidence_breakdown": (clause or {}).get("confidence_breakdown"),
                    "needs_review": (clause or {}).get("needs_review"),
                    "review_reasons": (clause or {}).get("review_reasons"),
                },
                "source": {
                    "document_id": requirement.get("document_id"),
                    "available": document is not None,
                    "source_name": (document or {}).get("source_name"),
                    "source_type": (document or {}).get("source_type"),
                    "jurisdiction": (document or {}).get("jurisdiction"),
                    "origin": (document or {}).get("origin"),
                    "url": (document or {}).get("source_url") or (document or {}).get("url"),
                    "read_at": (document or {}).get("uploaded_at"),
                    # Proof the file behind the quote is the file that was read.
                    "content_sha256": (document or {}).get("content_sha256"),
                },
            }
        )

    pack: dict[str, Any] = {
        "kind": "regulens.evidence_pack",
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "product": {
            "id": product_id,
            "name": product.get("name"),
            "product_type": product.get("product_type"),
            "origin": product.get("origin"),
            "packaging": product.get("packaging"),
            "ingredients": product.get("ingredients"),
            "target_markets": product.get("target_markets"),
            "compliance_status": product.get("compliance_status"),
            "compliance_upcoming": product.get("compliance_upcoming"),
        },
        "findings": findings,
        # The audit trail as stored. Every status this product ever held, what
        # caused it, and when — not a narrative assembled for this document.
        "history": [
            {
                "occurred_at": e.get("occurred_at"),
                "event_type": e.get("event_type"),
                "before": e.get("before"),
                "after": e.get("after"),
                "cause": e.get("cause"),
                "triggered_by": e.get("triggered_by"),
            }
            for e in events
        ],
        "coverage": {
            "findings": len(findings),
            "rules_no_longer_on_file": sum(1 for f in findings if not f["rule"]["available"]),
            "sources_no_longer_on_file": sum(1 for f in findings if not f["source"]["available"]),
        },
        "limitations": [
            "This pack is not signed. Its hashes show the content has not "
            "changed; they do not establish who produced it.",
            "It reports what ReguLens read. A regulation nobody uploaded and no "
            "watched source published is not represented here.",
            "A verdict marked needs_review was not decided automatically and "
            "carries no assertion of compliance.",
        ],
    }
    pack = _json_safe(pack)
    # Over the pack minus the hash field itself, so the value is reproducible by
    # anybody holding the file.
    pack["content_hash"] = hashlib.sha256(
        json.dumps(pack, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    log(
        logger, logging.INFO, "evidence pack built",
        product_id=product_id, findings=len(findings), events=len(events),
    )
    return pack
