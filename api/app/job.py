"""Cloud Run Job entrypoint — seeding and reprocessing.

Runs to completion and exits. Phase 0 uses it to seed markets; later phases add
document reprocessing here rather than inventing another runtime.
"""

from __future__ import annotations

import logging
import sys

from app.core.markets import seed_markets
from app.observability import configure_logging, log, set_trace_id
from app.settings import get_settings

settings = get_settings()
configure_logging(settings.log_level, "regulens-job")
logger = logging.getLogger(__name__)


def main(argv: list[str]) -> int:
    set_trace_id(None)
    task = argv[1] if len(argv) > 1 else "seed"
    if task == "seed":
        result = seed_markets()
        log(logger, logging.INFO, "job complete", task=task, markets=len(result))
        return 0
    log(logger, logging.ERROR, "unknown task", task=task)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
