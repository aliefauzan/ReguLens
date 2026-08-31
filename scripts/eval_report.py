"""Print the accuracy table.

Offline stages always — the guardrail, unit conversion and the evaluator make no
model call, so the numbers cost nothing and can run in CI on every change.

Extraction is scored only with REGULENS_EVAL=1, because it needs live model
calls and therefore money. Its absence is stated rather than left blank: a
report with a silently missing row reads like a report with nothing to say about
that stage.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from app.core.eval_stages import score_all  # noqa: E402
from app.core.evaluation import table  # noqa: E402


def main() -> int:
    scores = score_all()
    print(table(scores))
    print()
    problems = []
    for name, scored in scores.items():
        for wrong in scored.get("wrong", []):
            problems.append(f"  {name}: {wrong}")
    if problems:
        print("Disagreements with the labels:")
        print("\n".join(problems))
        print()
    if os.environ.get("REGULENS_EVAL") == "1":
        print("extraction: run `pytest tests/test_extraction_quality.py` — live model")
    else:
        print(
            "extraction accuracy not measured here: it needs live model calls.\n"
            "  REGULENS_EVAL=1 cd api && .venv/bin/python -m pytest "
            "tests/test_extraction_quality.py"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
