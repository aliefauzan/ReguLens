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
    fixtures = _load_fixtures()
    assert fixtures, "fixture set must not be empty"
    passed = 0
    misses: list[str] = []
    for text_file, expected in fixtures:
        raw_candidates = generate_candidates(text_file.read_text(), sample_index=0)
        matched = False
        for raw in raw_candidates:
            candidate, rejection = build_candidate(
                raw,
                document_id="fixture",
                source_type="official_regulation",
                declared_effective_date=None,
            )
            if rejection:
                continue
            fields = _fields_of(candidate)
            if all(fields.get(k) == expected[k] for k in KEY_FIELDS if k in expected):
                passed += 1
                matched = True
                break
        if not matched:
            misses.append(text_file.name)
    print(f"extraction accuracy: {passed}/{len(fixtures)}; missed: {misses}")
    assert passed / len(fixtures) >= 0.8


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
