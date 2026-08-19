"""Firestore client. One lazily-created client per process; works against the
emulator locally and ADC/workload identity in Cloud Run without a code change."""

from __future__ import annotations

from functools import lru_cache

from google.cloud import firestore

from app.settings import get_settings


@lru_cache
def get_db() -> firestore.Client:
    settings = get_settings()
    return firestore.Client(project=settings.project_id, database=settings.firestore_database)


def health_check() -> str:
    """A real round-trip, not a hardcoded string. Reads one document that may or
    may not exist — either answer proves the connection works."""
    db = get_db()
    db.collection("_health").document("probe").get(timeout=5)
    return "ok"
