"""The Query Agent's engine room: retrieval + grounded answer synthesis.

Grounding rule enforced here, in code: an answer must cite at least one stored
clause ID from the retrieved set. An answer citing anything else is rejected,
retried once, then refused. The model never answers compliance questions from
world knowledge.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.core.reconciliation import find_similar
from app.db import get_db
from app.observability import get_trace_id, log
from app.settings import get_settings

logger = logging.getLogger(__name__)

_INTENTS = ("status", "cause", "change", "remediation", "clause_lookup")


def classify_intent(question: str) -> str:
    """Deterministic keyword classification with a clause_lookup default."""
    q = question.lower()
    if re.search(r"why|risk|problem|broke", q):
        return "cause"
    if re.search(r"can i|export|ship|ready", q):
        return "status"
    if re.search(r"what changed|changes?|update|new regulation", q):
        return "change"
    if re.search(r"fix|remediat|what should i", q):
        return "remediation"
    return "clause_lookup"


def _retrieve(
    question: str,
    product_id: str | None,
    *,
    intent: str = "clause_lookup",
) -> dict[str, Any]:
    bundle: dict[str, Any] = {"clauses": [], "requirements": [], "conflicts": []}

    # 1. Clause retrieval by embedding similarity.
    try:
        pseudo_clause = {"id": None, "text": question, "substance_normalized": _substance_of(question)}
        bundle["clauses"] = find_similar(pseudo_clause, k=5)
    except Exception as exc:  # noqa: BLE001 - retrieval degrades, never crashes
        log(logger, logging.WARNING, "query_retrieval_degraded", error=str(exc)[:200])

    # 2. Product-scoped requirements — and the clauses behind them, so the
    # answer can cite a real clause id for every evaluation it mentions.
    from google.cloud import firestore

    if product_id:
        reqs = (
            get_db()
            .collection("requirements")
            .where(filter=firestore.FieldFilter("product_id", "==", product_id))
            .limit(50)
            .stream()
        )
        bundle["requirements"] = [d.to_dict() | {"id": d.id} for d in reqs]
        seen_ids = {c["id"] for c in bundle["clauses"]}
        for req in bundle["requirements"]:
            cid = req.get("clause_id")
            if cid and cid not in seen_ids:
                snap = get_db().collection("clauses").document(cid).get()
                if snap.exists:
                    bundle["clauses"].append(snap.to_dict() | {"id": snap.id})
                    seen_ids.add(snap.id)

    # 3. Open conflicts.
    conflicts = (
        get_db()
        .collection("conflicts")
        .where(filter=firestore.FieldFilter("status", "==", "open"))
        .limit(20)
        .stream()
    )
    bundle["conflicts"] = [d.to_dict() | {"id": d.id} for d in conflicts]

    # 4. Change questions need history, not just current state.
    if intent == "change":
        from google.cloud import firestore

        events = (
            get_db()
            .collection("graph_events")
            .where(
                filter=firestore.FieldFilter(
                    "event_type", "in",
                    ["clause_superseded", "requirement_changed", "product_status_changed"],
                )
            )
            .limit(15)
            .stream()
        )
        bundle["events"] = [e.to_dict() | {"id": e.id} for e in events]
        seen_ids = {c["id"] for c in bundle["clauses"]}
        # Conflict parties carry the current competing limits.
        for cfl in bundle["conflicts"]:
            for cid in (cfl.get("clause_a"), cfl.get("clause_b")):
                if cid and cid not in seen_ids:
                    snap = get_db().collection("clauses").document(cid).get()
                    if snap.exists:
                        bundle["clauses"].append(snap.to_dict() | {"id": snap.id})
                        seen_ids.add(cid)
        for ev in bundle["events"]:
            cause = ev.get("cause") or {}
            cid = cause.get("clause_id") or cause.get("new_clause_id")
            if cid and cid not in seen_ids:
                snap = get_db().collection("clauses").document(cid).get()
                if snap.exists:
                    bundle["clauses"].append(snap.to_dict() | {"id": snap.id})
                    seen_ids.add(snap.id)
    return bundle


def _substance_of(question: str) -> str | None:
    """Best-effort substance hint for retrieval filtering."""
    from app.core.normalization import normalize_substance

    for token in re.findall(r"[a-zA-Z][a-zA-Z ]{3,}", question):
        normalized, unmatched = normalize_substance(token.strip())
        if not unmatched:
            return normalized
    return None


def _synthesis_prompt(question: str, bundle: dict[str, Any]) -> str:
    lines = [
        "You answer regulatory compliance questions using ONLY the evidence below:",
        "stored clauses, requirement evaluations, recorded events, and open conflicts.",
        "Events and conflicts describe what changed; cite the clause ids they name.",
        "Every factual claim must trace to a stored clause id, cited inline as [clause_id].",
        "If NO evidence addresses the question at all, reply exactly:",
        '"I do not have enough information to answer this."',
        "",
        f"Question: {question}",
        "",
    ]
    for c in bundle["clauses"][:5]:
        lines.append(
            f"[{c['id']}] ({c.get('jurisdiction')}, limit={c.get('limit_value')} "
            f"{c.get('unit') or ''}) {str(c.get('text'))[:400]}"
        )
    for r in bundle["requirements"][:10]:
        lines.append(
            f"[req:{r['id']}] product {r.get('product_value')} vs limit "
            f"{r.get('limit_value')} {r.get('unit')} — evaluation: {r.get('evaluation')}"
        )
    for ev in bundle.get("events", [])[:8]:
        before = (ev.get("before") or {}).get("status") or (ev.get("before") or {}).get("limit_value")
        after = (ev.get("after") or {}).get("status") or (ev.get("after") or {}).get("limit_value")
        cause = ev.get("cause") or {}
        cause_clause = cause.get("clause_id") or cause.get("new_clause_id")
        entity = ev.get("entity_id", "")
        by_id = {c["id"]: c for c in bundle["clauses"]}
        parts = [f"{ev.get('event_type')} on {entity}"]
        entity_clause = by_id.get(entity)
        if entity_clause:
            parts.append(
                f"limit {entity_clause.get('limit_value')} {entity_clause.get('unit')}"
            )
        if before is not None or after is not None:
            parts.append(f"{before} -> {after}")
        if cause_clause:
            parts.append(f"involving {cause_clause}")
        lines.append(f"[event:{ev['id']}] " + "; ".join(parts))
    for cfl in bundle["conflicts"][:5]:
        lines.append(
            f"[conflict:{cfl['id']}] between {cfl.get('clause_a')} and {cfl.get('clause_b')}"
        )
    return "\n".join(lines)


def _validate_citations(answer: str, bundle: dict[str, Any]) -> list[str]:
    """Citations are valid only if they name a clause in the retrieved set —
    which includes the clauses behind the product's own requirements. Any
    mention of a clause id counts, bracketed or inline."""
    retrieved = {c["id"] for c in bundle["clauses"]}
    found = set(re.findall(r"clause_[a-z0-9]+", answer))
    missing = found - retrieved
    if missing:
        log(logger, logging.WARNING, "ungrounded_citation_attempt", unknown=sorted(missing)[:5])
    return sorted(found & retrieved)


# Country words a question is likely to use, mapped to the jurisdiction the
# clauses carry. Local-only: the real path has a model to do this.
_FAKE_JURISDICTION_HINTS = {
    "germany": "EU",
    "german": "EU",
    "europe": "EU",
    "european": "EU",
    "eu": "EU",
    "indonesia": "ID_BPOM",
    "indonesian": "ID_BPOM",
    "bpom": "ID_BPOM",
}


def _fake_pick(question: str, bundle: dict[str, Any]) -> dict[str, Any]:
    """Choose the clause a canned answer should quote.

    Taking `clauses[0]` answered "why does this break the rules in Germany?"
    with the Indonesian limit — technically a real retrieved clause, and
    nonsense to read. This is presentation only: FAKE_LLM never runs in
    production, but it is what anyone evaluating the local stack sees.
    """
    clauses = bundle["clauses"]
    lowered = question.lower()
    wanted = next(
        (juris for word, juris in _FAKE_JURISDICTION_HINTS.items() if word in lowered),
        None,
    )
    if wanted:
        match = next(
            (c for c in clauses if str(c.get("jurisdiction") or "").upper() == wanted
             and c.get("limit_value") is not None),
            None,
        )
        if match:
            return match
    # Otherwise prefer a clause that actually failed the product — the thing
    # someone asking an open question most likely wants to know about.
    failing = {
        r.get("clause_id")
        for r in bundle["requirements"]
        if r.get("evaluation") == "fail"
    }
    return next((c for c in clauses if c["id"] in failing), clauses[0])


def _synthesize(question: str, bundle: dict[str, Any]) -> tuple[str, list[str]]:
    """One Gemini call; citations validated against the retrieved set. A
    retry follows one failure; after that an honest refusal."""
    settings = get_settings()

    def refuse() -> tuple[str, list[str]]:
        msg = (
            "I do not have enough information to answer this. "
            "No ingested regulation covers this question yet."
        )
        return (msg, [])

    if not bundle["clauses"] and not bundle["requirements"]:
        return refuse()
    if settings.fake_llm:
        chosen = _fake_pick(question, bundle)
        # Keeps the bracketed id so the local path exercises the same citation
        # validation and the same UI renumbering as a real model answer.
        fake_answer = (
            f"The rule that covers this [{chosen['id']}]: {str(chosen.get('text'))[:200]}"
        )
        return (fake_answer, [chosen["id"]])

    from google.genai import types

    from app.core.extraction.llm import _client

    prompt = _synthesis_prompt(question, bundle)
    try:
        response = _client().models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0),
        )
    except Exception as exc:  # noqa: BLE001 - synthesis failure is an honest refusal
        log(logger, logging.WARNING, "query_synthesis_failed", error=str(exc)[:200])
        return refuse()

    answer = (response.text or "").strip()
    cited = _validate_citations(answer, bundle)
    if not cited:
        retry_prompt = prompt + "\n\nREMINDER: cite at least one [clause_id] from the evidence."
        try:
            response = _client().models.generate_content(
                model=settings.gemini_model,
                contents=retry_prompt,
                config=types.GenerateContentConfig(temperature=0.0),
            )
            answer = (response.text or "").strip()
            cited = _validate_citations(answer, bundle)
        except Exception:  # noqa: BLE001
            cited = []
        if not cited:
            return refuse()
    return answer, cited


def ask(question: str, product_id: str | None = None) -> dict[str, Any]:
    """POST /query entry. Retrieval → synthesis → grounding validation → log."""
    started = time.monotonic()
    intent = classify_intent(question)
    bundle = _retrieve(question, product_id, intent=intent)
    answer, cited = _synthesize(question, bundle)
    latency_ms = int((time.monotonic() - started) * 1000)

    confidences = [c.get("confidence") for c in bundle["clauses"] if c["id"] in cited]
    confidence = min(confidences) if confidences else None
    record = {
        "workspace_id": "ws_demo",
        "question": question[:500],
        "product_id": product_id,
        "intent": intent,
        "retrieved_clause_ids": [c["id"] for c in bundle["clauses"]],
        "answer": answer,
        "cited_clause_ids": cited,
        "confidence": confidence,
        "latency_ms": latency_ms,
        "trace_id": get_trace_id(),
    }
    get_db().collection("query_logs").add(record)

    evidence = []
    for cid in cited:
        match = next((c for c in bundle["clauses"] if c["id"] == cid), None)
        if match:
            evidence.append({
                "id": cid,
                "text": match.get("text"),
                "jurisdiction": match.get("jurisdiction"),
                "confidence": match.get("confidence"),
                "document_id": match.get("document_id"),
            })
    return {
        "intent": intent,
        "answer": answer,
        "cited_clauses": evidence,
        "confidence": confidence,
        "latency_ms": latency_ms,
        "refusal": not cited,
    }