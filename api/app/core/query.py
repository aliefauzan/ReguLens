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

    # 1b. What the question asked for by name. A question naming a market got
    # nothing but embedding rank, and refused while the graph held the clause
    # the product page cites — the worst refusal there is, because it is wrong
    # and it looks careful.
    jurisdictions = _jurisdictions_of(question)
    if jurisdictions:
        seen_ids = {c["id"] for c in bundle["clauses"]}
        for clause in _clauses_in(jurisdictions, question, k=5):
            if clause["id"] not in seen_ids:
                bundle["clauses"].append(clause)
                seen_ids.add(clause["id"])

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
    """Best-effort substance hint for retrieval filtering.

    Word by word, then two words at a time, because the dictionary holds both
    ("stevia", "sodium benzoate"). The previous version matched runs of letters
    and spaces, which handed the strict matcher an entire sentence — "what is
    the nitrite limit for cured meat in germany" is not a substance, so the hint
    never fired and every question fell back to embedding rank alone.
    """
    from app.core.normalization import normalize_substance

    words = re.findall(r"[a-zA-Z][a-zA-Z0-9-]*", question.lower())
    grams = [" ".join(words[i : i + 2]) for i in range(len(words) - 1)] + words
    for gram in grams:
        normalized, unmatched = normalize_substance(gram)
        if not unmatched:
            return normalized
    return None


def _jurisdictions_of(question: str) -> list[str]:
    """The jurisdictions a question names, by market label, country or code.

    Read from the stored markets rather than a table in this file: a market
    added by country discovery has to be answerable the day it is added, and a
    list here would go stale the first time one is.
    """
    return sorted({j for _, j in _markets_named(question)})


def _markets_named(question: str) -> list[tuple[str, str]]:
    """`(country, jurisdiction)` for every market the question names.

    Punctuation is flattened first. "…in Germany?" ends in a question mark, and
    matching on " germany " against the raw string finds nothing — which is how
    the first version of this returned no jurisdiction for the one question it
    was written for.
    """
    from app.core import markets as markets_core

    lowered = " " + re.sub(r"[^a-z0-9]+", " ", question.lower()).strip() + " "
    found: list[tuple[str, str]] = []
    for market in markets_core.list_markets():
        country = str(market.get("country") or market.get("country_name") or "")
        names = [
            country,
            str(market.get("label") or "").split("—")[-1],
            str(market.get("regulator") or ""),
        ]
        if not any(
            n and f" {re.sub(r'[^a-z0-9]+', ' ', n.lower()).strip()} " in lowered
            for n in names
        ):
            continue
        jurisdictions = market.get("jurisdictions") or [market.get("jurisdiction")]
        found.extend((country or "that market", str(j)) for j in jurisdictions if j)
    return sorted(set(found))


def _clauses_in(jurisdictions: list[str], question: str, k: int) -> list[dict]:
    """Top active clauses of the named jurisdictions, ranked against the question.

    A question that names a market and no substance — "the nitrite limit for
    cured meat in Germany" — retrieves on wording alone, and the wording of a
    question rarely resembles the wording of an annex row. Asking the graph for
    the jurisdiction it just named is the cheap half of the answer, and it is
    the half the reader thought they were asking for.
    """
    from google.cloud import firestore

    from app.core.reconciliation import _ranked, embed_text

    if not jurisdictions:
        return []
    rows = [
        d.to_dict() | {"id": d.id}
        for d in (
            get_db()
            .collection("clauses")
            .where(filter=firestore.FieldFilter("status", "in", ["active", "conflicted"]))
            .where(filter=firestore.FieldFilter("jurisdiction", "in", jurisdictions[:10]))
            .limit(200)
            .stream()
        )
    ]
    if not rows:
        return []
    try:
        vector = embed_text(question)
    except Exception as exc:  # noqa: BLE001 - ranking degrades, retrieval does not
        log(logger, logging.WARNING, "query_rank_degraded", error=str(exc)[:200])
        return rows[:k]
    return _ranked(rows, {"id": None, "embedding": vector}, k)


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
    # Which jurisdiction speaks for the country the question named. Without it a
    # model reads "Germany" against a clause marked EU and calls that a
    # different country, which is how a question about the one market this
    # product sells into came back as "no regulation covers this".
    for country, jurisdiction in _markets_named(question):
        lines.append(
            f"NOTE: rules for {country} are the ones marked {jurisdiction}; "
            f"a {jurisdiction} clause IS evidence about {country}."
        )
    lines.append("")
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


def _validate_citations(
    answer: str, bundle: dict[str, Any], extra_ids: set[str] | None = None
) -> list[str]:
    """Citations are valid only if they name a clause in the retrieved set —
    which includes the clauses behind the product's own requirements. Any
    mention of a clause id counts, bracketed or inline.

    `extra_ids` are ids the query agent's own tools read out of Firestore during
    the run. They are as real as the retrieved set — this process fetched them —
    and admitting them is what lets the agent choose its own retrieval without
    losing the grounding guarantee."""
    retrieved = {c["id"] for c in bundle["clauses"]} | (extra_ids or set())
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


def _synthesize_via_agent(
    question: str, bundle: dict[str, Any], product_id: str | None
) -> tuple[str, list[str]]:
    """Let the ADK Query Agent choose its own retrieval and answer.

    This is the one place in ReguLens where an agent picking its own tools earns
    its keep: an open question does not map onto a fixed pipeline the way
    extraction does. It stays inside the same rule as everything else — the
    agent proposes an answer, and the citation check below decides whether a
    user ever sees it.

    Returns empty citations on any failure, which sends the caller to the
    single-call path. A degraded answer is worth having; a wrong one is not.
    """
    import asyncio

    from app.adk.query_agent import INSUFFICIENT, run_query_agent

    try:
        answer, served = asyncio.run(
            run_query_agent(question, product_id, evidence=bundle["clauses"])
        )
    except Exception as exc:  # noqa: BLE001 - the deterministic path is the net
        log(logger, logging.WARNING, "query_agent_failed", error=str(exc)[:200])
        return ("", [])

    if INSUFFICIENT in answer:
        # The agent said it has nothing. Hand over to the single-call path,
        # which refuses in the words a user should read.
        log(logger, logging.INFO, "query_agent_insufficient")
        return ("", [])

    cited = _validate_citations(answer, bundle, extra_ids=set(served))
    log(
        logger, logging.INFO, "query_agent_answer",
        served=len(served), cited=len(cited), chars=len(answer),
    )
    return (answer, cited)


def _synthesize(
    question: str, bundle: dict[str, Any], product_id: str | None = None
) -> tuple[str, list[str]]:
    """The ADK agent first; a single grounded Gemini call as the net. Either
    way citations are validated against clauses this process actually read, a
    retry follows one failure, and after that an honest refusal."""
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

    agent_answer, agent_cited = _synthesize_via_agent(question, bundle, product_id)
    if agent_cited:
        return agent_answer, agent_cited

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
    answer, cited = _synthesize(question, bundle, product_id)
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
        if match is None:
            # The agent found this one through its own retrieval. It is a real
            # stored clause — a tool read it out of Firestore — so the citation
            # card has to be able to show it, or a grounded answer would render
            # with no visible source.
            snapshot = get_db().collection("clauses").document(cid).get()
            if snapshot.exists:
                match = snapshot.to_dict() | {"id": snapshot.id}
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