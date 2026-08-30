"""The scorer has to be right before any number it prints means anything.

A quietly wrong scoring function makes every figure downstream of it wrong and
confident, which is worse than having no figures. So the arithmetic is pinned
here against cases worked by hand.
"""

from app.core.evaluation import prf1, score_labels, score_sets


def test_perfect_prediction_scores_one():
    assert prf1(10, 0, 0) | {} == prf1(10, 0, 0)
    scored = prf1(10, 0, 0)
    assert (scored["precision"], scored["recall"], scored["f1"]) == (1.0, 1.0, 1.0)


def test_predicting_nothing_is_not_a_perfect_score():
    """The failure this whole module exists to prevent: dividing by zero and
    calling silence flawless."""
    scored = prf1(0, 0, 5)
    assert scored["precision"] == 0.0
    assert scored["recall"] == 0.0
    assert scored["f1"] == 0.0


def test_extra_predictions_cost_precision_not_recall():
    """The old '5/5' counted a right answer beside four inventions as perfect."""
    scored = score_sets({"a", "b"}, {"a", "b", "x", "y"})
    assert scored["recall"] == 1.0
    assert scored["precision"] == 0.5
    assert scored["spurious"] == ["x", "y"]


def test_missing_predictions_cost_recall_not_precision():
    scored = score_sets({"a", "b", "c", "d"}, {"a", "b"})
    assert scored["precision"] == 1.0
    assert scored["recall"] == 0.5
    assert scored["missed"] == ["c", "d"]


def test_f1_is_the_harmonic_mean_not_the_average():
    scored = prf1(1, 1, 3)  # precision 0.5, recall 0.25
    assert scored["precision"] == 0.5
    assert scored["recall"] == 0.25
    assert scored["f1"] == round(2 * 0.5 * 0.25 / 0.75, 4)


def test_labels_are_scored_per_class_not_only_overall():
    """An overall figure hides a stage that gets the common label right and the
    one that matters wrong."""
    cases = [("pass", "pass")] * 9 + [("fail", "pass")]
    scored = score_labels(cases)
    assert scored["accuracy"] == 0.9
    assert scored["per_label"]["fail"]["recall"] == 0.0
    assert scored["wrong"] == [{"expected": "fail", "predicted": "pass"}]


def test_every_row_reports_its_sample_size():
    """A precision quoted without n is a number pretending to be evidence."""
    assert score_sets({"a"}, {"a"})["n"] == 1
    assert score_labels([("x", "x"), ("y", "y")])["n"] == 2
