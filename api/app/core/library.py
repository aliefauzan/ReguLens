"""The bundled rule library.

The app used to start knowing nothing. A user's first product showed "no rules
added yet" in every market, and the only way forward was to go and find a
regulation PDF — which is the job they came here to avoid. The library is the
answer to "why do I have to add a regulation?": we already hold two real
regulations, so the app ships with excerpts of them and offers to read them.

Every entry is verbatim source text with its citation, built by
`scripts/build_library.py` from the corpus in `data/regulations/`. Nothing here
is written by hand and nothing is summarised — a limit in this file is a limit
the regulator wrote.

Loading an entry goes through the ordinary upload path: same hashing, same
Pub/Sub message, same extraction, same guardrail. There is no back door that
writes clauses directly, and there is no claim that a loaded entry is "verified"
beyond what the pipeline itself decides.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.documents import create_document
from app.models import DocumentIn, RegulatoryDocument, SourceType
from app.observability import get_trace_id, log

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).with_name("library_data.json")

# What a first-time user gets from one button. Deliberately small: each entry is
# a real extraction run, and eight of them already cover both markets for the
# drinks and powders the demo product is made of. The rest of the library is
# there to be picked from, one at a time, by someone who knows what they sell.
STARTER_IDS: tuple[str, ...] = (
    "eu_annex_ii_14_1_4",
    "eu_annex_ii_14_1_2",
    "eu_annex_ii_14_1_5_2",
    "eu_annex_ii_17_1",
    "bpom_11_2019_p766",
    "bpom_11_2019_p124",
    "bpom_11_2019_p137",
    "bpom_11_2019_p130",
)


@lru_cache
def _entries() -> list[dict[str, Any]]:
    return json.loads(DATA_FILE.read_text())


def list_entries() -> list[dict[str, Any]]:
    """Every entry, without its text. The UI lists these; it never renders the
    excerpt itself, which belongs on the document page after it is read."""
    return [
        {key: value for key, value in entry.items() if key != "text"}
        | {"starter": entry["id"] in STARTER_IDS}
        for entry in _entries()
    ]


def get_entry(entry_id: str) -> dict[str, Any] | None:
    return next((entry for entry in _entries() if entry["id"] == entry_id), None)


def load_entries(entry_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Ingest the named entries (or the starter set) and report what happened.

    Idempotent: an entry already read short-circuits on its content hash, so
    pressing the button twice costs two Firestore lookups and no extraction.
    Unknown ids are reported rather than silently dropped — a caller asking for
    a rule that does not exist has a bug, and hiding it would hide the bug.
    """
    wanted = list(entry_ids) if entry_ids else list(STARTER_IDS)
    results: list[dict[str, Any]] = []
    for entry_id in wanted:
        entry = get_entry(entry_id)
        if entry is None:
            results.append({"id": entry_id, "found": False})
            continue
        document, cached = create_document(
            meta=DocumentIn(
                source_type=SourceType(entry["source_type"]),
                source_name=entry["source_name"],
                jurisdiction=entry["jurisdiction"],
            ),
            text=entry["text"],
            trace_id=get_trace_id(),
            origin="library",
        )
        results.append(
            {
                "id": entry_id,
                "found": True,
                "document_id": document.id,
                "cached": cached,
                "status": str(document.status),
            }
        )
    log(
        logger,
        logging.INFO,
        "library entries loaded",
        requested=len(wanted),
        ingested=sum(1 for r in results if r.get("found") and not r.get("cached")),
        already_read=sum(1 for r in results if r.get("cached")),
        unknown=sum(1 for r in results if not r.get("found")),
    )
    return results


def documents_for(results: list[dict[str, Any]]) -> list[RegulatoryDocument]:
    """The documents behind a load, for a caller that wants to link to them."""
    from app.core.documents import get_document

    out: list[RegulatoryDocument] = []
    for result in results:
        if not result.get("found"):
            continue
        document = get_document(result["document_id"])
        if document is not None:
            out.append(document)
    return out
