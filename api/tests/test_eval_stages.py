"""The labelled sets, run against the code, offline and free.

These are not unit tests of the guardrail — those exist. They are the regression
that stops accuracy sliding: the labels say what a compliance officer would
answer, and a change that makes the code disagree with them has to be argued
for, not merged quietly.
"""

from app.core.eval_stages import score_all, score_guardrail, score_verdicts


def test_the_guardrail_agrees_with_the_hand_labels():
    for name, scored in score_guardrail().items():
        if "accuracy" in scored:
            assert scored["accuracy"] == 1.0, (name, scored.get("wrong"))
        else:
            assert scored["precision"] == 1.0, (name, scored.get("wrong"))
            assert scored["recall"] == 1.0, (name, scored.get("wrong"))


def test_the_evaluator_agrees_with_the_hand_labels():
    scored = score_verdicts()["verdict"]
    assert scored["accuracy"] == 1.0, scored["wrong"]


def test_no_label_set_is_silently_empty():
    """An empty fixture file scores 100% and means nothing."""
    for name, scored in score_all().items():
        assert scored["n"] > 0, name


def test_a_false_positive_in_the_guardrail_would_be_caught():
    """The label set has to contain negatives, or precision is unmeasurable."""
    from app.core.eval_stages import _load

    labels = _load("guardrail")
    assert any(not row["comparable"] for row in labels["substances"])
    assert any(not row["comparable"] for row in labels["product_types"])
