"""Fixture-set extraction accuracy.

Fixtures are verbatim excerpts from the real corpus in data/regulations/
(see SOURCES.md) with hand-labelled expectations. Accuracy runs need live
Vertex calls, so they are gated behind REGULENS_EVAL=1.
"""

import json
import os
from pathlib import Path

import pytest

from app.core.extraction.candidates import build_candidate
from app.core.extraction.llm import generate_candidates

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"

KEY_FIELDS = ("substance_normalized", "limit_value", "unit_enum", "jurisdiction")


def _load_fixtures():
    out = []
    if not FIXTURES.exists():
        return out
    for text_file in sorted(FIXTURES.glob("*.txt")):
        expected_file = text_file.with_suffix(".expected.json")
        if not expected_file.exists():
            continue
        expected = json.loads(expected_file.read_text())
        out.append((text_file, expected))
    return out


def _fields_of(candidate):
    return {
        "substance_normalized": candidate.substance_normalized,
        "limit_value": candidate.limit_value,
        "unit_enum": str(candidate.unit_enum) if candidate.unit_enum else None,
        "jurisdiction": None,  # jurisdiction comes from the upload metadata
    }


@pytest.mark.skipif(
    os.environ.get("REGULENS_EVAL") != "1",
    reason="live-Vertex evaluation run — costs tokens; REGULENS_EVAL=1 to enable",
)
def test_fixture_accuracy_against_live_vertex():
    """Precision and recall, not a hit count.

    This used to stop at the first candidate that matched and never look at the
    others, so a fixture answered correctly *and* with four inventions beside it
    scored a clean pass. Every accepted candidate is now counted: the ones the
    label does not contain are false positives, and they are named, because the
    fix for a spurious clause is sometimes to correct the label instead.
    """
    from app.core.evaluation import score_sets

    fixtures = _load_fixtures()
    assert fixtures, "fixture set must not be empty"
    expected_items: set[tuple] = set()
    predicted_items: set[tuple] = set()
    for text_file, expected in fixtures:
        name = text_file.name
        expected_items.add(
            (
                name,
                expected.get("substance_normalized"),
                expected.get("limit_value"),
                expected.get("unit_enum"),
            )
        )
        # A label may name clauses beyond the headline one; those are expected
        # too, and without this every correct extra reads as an invention.
        for extra in expected.get("also_expected", []):
            expected_items.add(
                (
                    name,
                    extra.get("substance_normalized"),
                    extra.get("limit_value"),
                    extra.get("unit_enum"),
                )
            )
        for raw in generate_candidates(text_file.read_text(), sample_index=0):
            candidate, rejection = build_candidate(
                raw,
                document_id="fixture",
                source_type="official_regulation",
                declared_effective_date=None,
            )
            if rejection:
                continue  # the guardrail refusing is not a prediction
            fields = _fields_of(candidate)
            predicted_items.add(
                (
                    name,
                    fields["substance_normalized"],
                    fields["limit_value"],
                    fields["unit_enum"],
                )
            )

    scored = score_sets(expected_items, predicted_items)
    print(
        f"extraction over n={scored['n']} labelled clauses: "
        f"precision {scored['precision']:.2f}, recall {scored['recall']:.2f}, "
        f"F1 {scored['f1']:.2f}"
    )
    if scored["missed"]:
        print("  missed:", scored["missed"])
    if scored["spurious"]:
        print("  not in the labels:", scored["spurious"])
    assert scored["recall"] >= 0.8, scored["missed"]
    assert scored["precision"] >= 0.6, scored["spurious"]


def test_fake_llm_candidates_pass_the_gate():
    """The FAKE_LLM canned response must itself survive validation — the one
    deliberately-malformed emission exercises the rejection path."""
    from app.core.extraction.llm import fake_candidates
    from app.models import ClauseType, Unit

    accepted = []
    rejected = 0
    numeric = None
    for raw in fake_candidates(
        "The maximum permitted level of sodium benzoate (E 211) in flavoured drinks is 150 mg/kg."
    ):
        candidate, rejection = build_candidate(
            raw, document_id="fixture", source_type="official_regulation"
        )
        if rejection:
            rejected += 1
            continue
        if candidate.clause_type == ClauseType.NUMERIC_LIMIT:
            assert candidate.substance_normalized == "sodium_benzoate"
            assert str(candidate.unit_enum) == str(Unit.MG_PER_KG)
            numeric = candidate
        accepted.append(candidate)

    assert len(accepted) == 2
    assert rejected == 1  # the intentional malformed emission
    assert numeric is not None

    assert len(accepted) == 2
    assert rejected == 1  # the intentional malformed emission
