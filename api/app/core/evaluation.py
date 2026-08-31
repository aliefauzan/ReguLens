"""Scoring, so accuracy is a number somebody can check rather than a claim.

"5/5 on fixtures" was the honest limit of what this repo measured, and it is not
accuracy: it counted whether the right clause appeared somewhere in the output
and never counted the wrong ones that appeared beside it. A stage that emits the
correct answer plus four inventions scores 5/5 under that rule.

So: precision, recall and F1, over sets, with the false positives counted.
Nothing here calls a model or touches a database — it takes labelled expectations
and predictions and does arithmetic, which is what makes it testable itself. A
scoring function that is quietly wrong makes every number downstream of it wrong
and confident.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from typing import Any


def prf1(true_positives: int, false_positives: int, false_negatives: int) -> dict[str, float]:
    """Precision, recall and F1 from counts.

    A stage that predicted nothing scores 0 recall and — by convention here —
    0 precision rather than 1. Dividing by zero and calling the result perfect
    is how "no output" becomes "no mistakes".
    """
    predicted = true_positives + false_positives
    actual = true_positives + false_negatives
    precision = true_positives / predicted if predicted else 0.0
    recall = true_positives / actual if actual else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "n": actual,
    }


def score_sets(
    expected: Iterable[Hashable],
    predicted: Iterable[Hashable],
) -> dict[str, Any]:
    """Compare two sets of labelled items.

    Multiplicity is deliberately ignored: the question these fixtures ask is
    "which rules are in this excerpt", not "how many times was each emitted".
    """
    expected_set, predicted_set = set(expected), set(predicted)
    matched = expected_set & predicted_set
    result = prf1(
        len(matched),
        len(predicted_set - expected_set),
        len(expected_set - predicted_set),
    )
    result["missed"] = sorted(str(x) for x in expected_set - predicted_set)
    result["spurious"] = sorted(str(x) for x in predicted_set - expected_set)
    return result


def score_labels(cases: Iterable[tuple[Any, Any]]) -> dict[str, Any]:
    """Accuracy over `(expected_label, predicted_label)` pairs, with a per-label
    breakdown — an overall figure hides a stage that gets the common label right
    and the one that matters wrong."""
    cases = list(cases)
    labels = sorted({str(expected) for expected, _ in cases})
    per_label: dict[str, dict[str, float]] = {}
    for label in labels:
        tp = sum(1 for e, p in cases if str(e) == label and str(p) == label)
        fp = sum(1 for e, p in cases if str(e) != label and str(p) == label)
        fn = sum(1 for e, p in cases if str(e) == label and str(p) != label)
        per_label[label] = prf1(tp, fp, fn)
    correct = sum(1 for e, p in cases if str(e) == str(p))
    return {
        "n": len(cases),
        "correct": correct,
        "accuracy": round(correct / len(cases), 4) if cases else 0.0,
        "per_label": per_label,
        "wrong": [
            {"expected": str(e), "predicted": str(p)} for e, p in cases if str(e) != str(p)
        ],
    }


def table(sections: dict[str, dict[str, Any]]) -> str:
    """The report as printed. Every row carries `n`, because a precision quoted
    without its sample size is a number pretending to be evidence."""
    lines = [
        f"{'STAGE':<28}{'N':>5}{'PRECISION':>11}{'RECALL':>9}{'F1':>7}",
        f"{'-----':<28}{'-':>5}{'---------':>11}{'------':>9}{'--':>7}",
    ]
    for name, scores in sections.items():
        if "accuracy" in scores:
            lines.append(
                f"{name:<28}{scores['n']:>5}{'':>11}{'':>9}{scores['accuracy']:>7.2f}"
                "  (accuracy)"
            )
            continue
        lines.append(
            f"{name:<28}{scores['n']:>5}{scores['precision']:>11.2f}"
            f"{scores['recall']:>9.2f}{scores['f1']:>7.2f}"
        )
    return "\n".join(lines)
