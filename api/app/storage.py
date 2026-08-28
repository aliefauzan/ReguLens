"""Object storage helper. One lazily-created client per process, mirroring db.py.

The API service account holds `storage.objectAdmin` on the uploads bucket only
(bucket-scoped in setup.sh); the worker holds objectViewer — the worker reads
the bytes it extracts from, it never writes.

There is no Cloud Storage emulator worth running, so the fully-local stack sets
`LOCAL_STORAGE_DIR` and the same two functions read and write a directory that
the api and worker containers share. The `gs://` URI shape is preserved in both
modes so nothing downstream has to know which backend is live.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from app.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_bucket():
    from google.cloud import storage

    settings = get_settings()
    client = storage.Client(project=settings.project_id)
    return client.bucket(settings.uploads_bucket_name)


def _local_root() -> Path | None:
    """Return the local uploads directory, or None when GCS is the backend."""
    directory = get_settings().local_storage_dir
    if not directory:
        return None
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _blob_path(uri: str) -> str:
    """Strip the bucket prefix off a gs:// URI, leaving the object name."""
    prefix = f"gs://{get_settings().uploads_bucket_name}/"
    _, _, path = uri.partition(prefix)
    return path or uri


def upload(name: str, data: bytes, content_type: str = "application/pdf") -> str:
    """Store one file and return its gs:// URI."""
    root = _local_root()
    if root is not None:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        logger.info("stored %s locally (%d bytes)", name, len(data))
    else:
        blob = get_bucket().blob(name)
        blob.upload_from_string(data, content_type=content_type)
        logger.info("stored %s (%d bytes)", name, len(data))
    return f"gs://{get_settings().uploads_bucket_name}/{name}"


def download(uri: str) -> bytes:
    """Fetch the bytes behind a storage URI written by `upload`."""
    path = _blob_path(uri)
    root = _local_root()
    if root is not None:
        target = root / path
        if not target.exists():
            raise FileNotFoundError(f"local object missing: {target}")
        return target.read_bytes()
    return get_bucket().blob(path).download_as_bytes()
