#!/usr/bin/env python3
"""Re-embed every stored clause after an embedding-model change.

REWRITTEN 29 Aug 2026. The original was deleted by accident during a lint
cleanup (`rm -rf api/scripts` to remove a stray duplicate of the library
builder, which took this file with it). It is reconstructed from what
`reconciliation.embed_text` documents it must do; if you have your own copy,
prefer it over this one.

Why it exists: a vector only means anything against vectors from the same
model. Switching between the Vertex path (`text-multilingual-embedding-002`)
and the Gemini Developer API path (`gemini-embedding-001`, 768 dimensions)
invalidates everything already stored. `find_similar` scores a length mismatch
as -1.0 rather than crashing, so a half-migrated corpus quietly degrades to bad
matches instead of failing loudly — which is exactly when you want this script.

Usage:
    python -m scripts.reembed --dry-run     # count what would change
    python -m scripts.reembed               # re-embed everything stale
    python -m scripts.reembed --all         # re-embed everything, stale or not

Run it from `api/` with the same environment the service uses (GEMINI_API_KEY
set, or unset for Vertex). It is safe to interrupt and re-run: each clause is
written on its own, and a clause already at the right width is skipped unless
`--all` is given.
"""

from __future__ import annotations

import argparse
import sys
import time

from app.core.reconciliation import embed_text
from app.db import get_db
from app.settings import get_settings

COLLECTION = "clauses"


def expected_width() -> int | None:
    """How many dimensions the current configuration produces.

    Vertex's multilingual model is fixed at 768, and the Gemini path is asked
    for `embed_dimensions` explicitly, so both are known without a call. If that
    ever stops being true, one probe call settles it.
    """
    settings = get_settings()
    if settings.use_gemini_api:
        return settings.embed_dimensions
    return 768


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    parser.add_argument("--all", action="store_true", help="re-embed even matching vectors")
    parser.add_argument("--limit", type=int, default=0, help="stop after N clauses")
    args = parser.parse_args()

    settings = get_settings()
    width = expected_width()
    print(
        f"path={'gemini-api' if settings.use_gemini_api else 'vertex'} "
        f"model={settings.gemini_embed_model if settings.use_gemini_api else settings.embed_model} "
        f"expected_dimensions={width}"
    )

    db = get_db()
    done = skipped = failed = 0
    for snapshot in db.collection(COLLECTION).stream():
        clause = snapshot.to_dict() or {}
        current = clause.get("embedding") or []
        if not args.all and width is not None and len(current) == width:
            skipped += 1
            continue
        text = clause.get("text") or ""
        if not text.strip():
            skipped += 1
            continue
        if args.dry_run:
            done += 1
        else:
            try:
                vector = embed_text(text)
            except Exception as exc:  # noqa: BLE001 - one bad clause must not stop the run
                failed += 1
                print(f"  {snapshot.id}: {exc}", file=sys.stderr)
                continue
            db.collection(COLLECTION).document(snapshot.id).set(
                {"embedding": vector}, merge=True
            )
            done += 1
            # Embedding endpoints are rate-limited and this is a background
            # migration, not a user waiting on a page.
            time.sleep(0.05)
        if args.limit and done >= args.limit:
            break
        if done and done % 25 == 0:
            print(f"  {done} re-embedded…")

    verb = "would re-embed" if args.dry_run else "re-embedded"
    print(f"{verb} {done}, skipped {skipped}, failed {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
