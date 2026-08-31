"""Running the labelled sets through the code, offline.

Kept apart from `evaluation.py` — that module is arithmetic and knows nothing
about this system; this one knows where the labels live and which function each
one is a label *for*.

Every stage here is deterministic and free: the guardrail, unit conversion and
the evaluator make no model call, and they are the stages that actually decide a
verdict. Extraction accuracy needs a live model and is scored separately, behind
a flag, because it costs money and cannot be part of an offline suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.evaluation import prf1, score_labels

LABELS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "labels"


def _load(name: str) -> dict[str, Any]:
    return json.loads((LABELS / f"{name}.json").read_text())


def score_guardrail() -> dict[str, dict[str, Any]]:
    """Two comparability questions and one conversion, against hand labels."""
    from app.core.guardrail import (
        product_types_comparable,
        substances_comparable,
        to_mg_per_kg,
    )

    labels = _load("guardrail")

    def comparability(rows: list[dict], fn) -> dict[str, Any]:
        # "Comparable" is the positive class: a false positive here compares two
        # things that must not be compared, which is how a nitrite limit ends up
        # failing a drink powder.
        tp = fp = fn_count = 0
        wrong = []
        for row in rows:
            predicted = bool(fn(row["a"], row["b"]))
            expected = bool(row["comparable"])
            if predicted and expected:
                tp += 1
            elif predicted and not expected:
                fp += 1
                wrong.append(f"{row['a']} vs {row['b']}: said comparable ({row['why']})")
            elif not predicted and expected:
                fn_count += 1
                wrong.append(f"{row['a']} vs {row['b']}: said not comparable ({row['why']})")
        scored = prf1(tp, fp, fn_count)
        # prf1 reports `n` as the positive class, which is the right denominator
        # for a set comparison and the wrong one to print beside a classifier:
        # a reader seeing "n=4" would not know six negatives were also judged.
        scored["n"] = len(rows)
        scored["wrong"] = wrong
        return scored

    units = labels["units"]
    unit_cases = [
        (row["mg_per_kg"], to_mg_per_kg(row["value"], row["unit"])) for row in units
    ]
    return {
        "guardrail: substances": comparability(labels["substances"], substances_comparable),
        "guardrail: product types": comparability(
            labels["product_types"], product_types_comparable
        ),
        "unit conversion": score_labels(unit_cases),
    }


def score_verdicts() -> dict[str, dict[str, Any]]:
    """The evaluator, against the verdict a compliance officer would give."""
    from app.core.impact import evaluate

    cases = []
    for case in _load("verdicts")["cases"]:
        product = {
            "product_type": "food_beverage_liquid",
            "ingredients": [
                {
                    "name": "sodium benzoate",
                    "normalized": "sodium_benzoate",
                    "amount": case["amount"],
                    "unit": case["unit"],
                }
            ],
        }
        clause = {
            "clause_type": case.get("clause_type", "numeric_limit"),
            "substance_normalized": "sodium_benzoate",
            "limit_value": case["limit"],
            "unit": case["limit_unit"],
            "confidence": case.get("confidence", 0.9),
        }
        cases.append((case["expected"], evaluate(product, clause)["evaluation"]))
    return {"verdict": score_labels(cases)}


def score_all() -> dict[str, dict[str, Any]]:
    return score_guardrail() | score_verdicts()
