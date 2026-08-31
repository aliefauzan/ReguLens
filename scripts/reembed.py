"""Re-embed every stored clause with the embedding backend now configured.

`reconciliation.embed_texts` has told readers to "run scripts/reembed.py" since
the batching work landed. The script did not exist. That gap is worse than it
looks, because of how the two backends line up:

- Vertex serves `text-multilingual-embedding-002`.
- The Gemini Developer API serves `gemini-embedding-001`, asked here for
  `EMBED_DIMENSIONS` (768) output.

Both return 768 numbers. So `find_similar`'s guard — score a length mismatch as
-1.0 rather than crash — never fires when a corpus is half-migrated. Nothing
errors. Nothing logs. Reconciliation simply starts comparing vectors from two
different spaces and quietly stops recognising that two clauses are about the
same thing, which in this product means a superseding amendment lands as a new
unrelated rule and a real conflict is never opened.

Setting or clearing `GEMINI_API_KEY` switches the backend for the whole app, so
run this immediately after any deploy that changes it.

    cd api && .venv/bin/python ../scripts/reembed.py            # re-embed all
    cd api && .venv/bin/python ../scripts/reembed.py --dry-run  # count only

Idempotent: re-embedding a clause that is already correct writes the same
vector. Safe to re-run after an interruption.
"""

from __future__ import annotations

import argparse
import sys

# Run from api/, where the app package and its venv live.
sys.path.insert(0, ".")

from app.core.reconciliation import EMBED_BATCH, embed_texts  # noqa: E402
from app.db import get_db  # noqa: E402
from app.models import WORKSPACE_ID  # noqa: E402
from app.settings import get_settings  # noqa: E402

COLLECTION = "clauses"


def backend_name() -> str:
    settings = get_settings()
    if settings.fake_llm:
        return "FAKE_LLM (hashed, not a real embedding)"
    if settings.use_gemini_api:
        return f"Gemini Developer API · {settings.gemini_embed_model} @ {settings.embed_dimensions}d"
    return f"Vertex · {settings.embed_model} @ {settings.embed_location}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="count, do not write")
    parser.add_argument("--batch", type=int, default=EMBED_BATCH, help="clauses per write batch")
    args = parser.parse_args()

    settings = get_settings()
    print(f"project   {settings.project_id}")
    print(f"backend   {backend_name()}")
    if settings.fake_llm:
        print("\nFAKE_LLM is set. Those are hashes, not embeddings — refusing to write them")
        print("over real vectors. Unset FAKE_LLM and run again.")
        return 2

    db = get_db()
    clauses = [
        (doc.id, doc.to_dict() or {})
        for doc in db.collection(COLLECTION)
        .where("workspace_id", "==", WORKSPACE_ID)
        .stream()
    ]
    with_text = [(cid, d) for cid, d in clauses if (d.get("text") or "").strip()]
    print(f"clauses   {len(clauses)} total, {len(with_text)} with text to embed")

    missing = len(clauses) - len(with_text)
    if missing:
        # Say how many are skipped and why. A clause with no text cannot be
        # embedded, and silently passing over it would make the totals lie.
        print(f"skipped   {missing} with no text — nothing to embed from")

    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    written = 0
    for start in range(0, len(with_text), args.batch):
        chunk = with_text[start : start + args.batch]
        vectors = embed_texts([d["text"] for _, d in chunk])
        batch = db.batch()
        for (cid, _), vector in zip(chunk, vectors, strict=True):
            batch.set(db.collection(COLLECTION).document(cid), {"embedding": vector}, merge=True)
        batch.commit()
        written += len(chunk)
        print(f"  {written}/{len(with_text)}")

    print(f"\nre-embedded {written} clauses with {backend_name()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
