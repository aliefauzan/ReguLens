"""Cloud Storage helper. One lazily-created client per process, mirroring db.py.

The API service account holds `storage.objectAdmin` on the uploads bucket only
(bucket-scoped in setup.sh); the worker holds objectViewer — the worker reads
the bytes it extracts from, it never writes.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from google.cloud import storage

from app.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_bucket() -> storage.Bucket:
    settings = get_settings()
    client = storage.Client(project=settings.project_id)
    return client.bucket(settings.uploads_bucket)


def upload(name: str, data: bytes, content_type: str = "application/pdf") -> str:
    """Store one file and return its gs:// URI."""
    blob = get_bucket().blob(name)
    blob.upload_from_string(data, content_type=content_type)
    logger.info("stored %s (%d bytes)", name, len(data))
    return f"gs://{get_settings().uploads_bucket}/{name}"
