"""These tests exist because a wrong substance mapping is a silent failure: the
product says one thing, the clause says another, nothing matches, and the UI
reports "no issues" — which looks exactly like success."""

import pytest

from app.core.normalization import normalize_substance, parse_unit
from app.models import Unit


@pytest.mark.parametrize(
    "raw",
    ["sodium benzoate", "Sodium Benzoate", "natrium benzoat", "E211", "e 211", "INS 211"],
)
def test_all_spellings_of_the_demo_substance_converge(raw):
    normalized, unmatched = normalize_substance(raw)
    assert normalized == "sodium_benzoate"
    assert unmatched is False


def test_english_and_indonesian_names_meet():
    assert normalize_substance("sodium benzoate")[0] == normalize_substance("natrium benzoat")[0]


def test_parenthesised_e_number_still_matches():
    assert normalize_substance("Sodium Benzoate (E211)")[0] == "sodium_benzoate"


def test_unknown_name_passes_through_flagged_not_guessed():
    normalized, unmatched = normalize_substance("Fictional Extract 9000")
    assert normalized == "fictional_extract_9000"
    assert unmatched is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("%", Unit.PERCENT_W_W),
        ("percent", Unit.PERCENT_W_W),
        ("% w/w", Unit.PERCENT_W_W),
        ("mg/kg", Unit.MG_PER_KG),
        ("MG/KG", Unit.MG_PER_KG),
        ("ppm", Unit.PPM),
    ],
)
def test_accepted_units_normalize_to_the_enum(raw, expected):
    assert parse_unit(raw) is expected


def test_unknown_unit_is_rejected_rather_than_coerced():
    with pytest.raises(ValueError, match="unrecognised unit"):
        parse_unit("grams per gallon")


def test_missing_unit_is_an_error_not_a_default():
    with pytest.raises(ValueError, match="unit is required"):
        parse_unit(None)


def test_a_header_that_says_or_states_one_basis_not_two():
    """Live extractions write the Annex II header in both orders; both mean the
    same measurement basis, and refusing one sends a real limit to review."""
    from app.core.normalization import parse_unit

    assert parse_unit("mg/kg or mg/l") == parse_unit("mg/l or mg/kg")
    assert parse_unit("mg/kg or mg/l as appropriate") == parse_unit("mg/kg")


def test_a_row_with_no_number_is_not_a_units_problem():
    """"quantum satis" carries no limit, so there is no unit to normalize.
    Flagging it as an unusable unit sends the reader after a fault that is not
    there."""
    from app.core.extraction.candidates import build_candidate

    clause, rejected = build_candidate(
        {
            "text": "Group II Colours at quantum satis",
            "clause_type": "numeric_limit",
            "substance": "Group II Colours",
            "limit_value": None,
            "unit_raw": "quantum satis",
            "product_type": "food_beverage_liquid",
        },
        document_id="doc_1",
        source_type="official_regulation",
        source_jurisdiction="EU",
    )
    assert not rejected, rejected
    assert "unit_not_normalizable" not in clause.review_reasons


def test_the_curing_salt_group_names_are_known():
    """The EU Annex II limit rows print the group, not the member, so the group
    has to be a name the dictionary knows or the row binds nothing."""
    from app.core.normalization import normalize_substance

    for name, expected in [
        ("nitrites", "nitrites"),
        ("nitrates", "nitrates"),
        ("potassium nitrite", "potassium_nitrite"),
        ("sodium nitrate", "sodium_nitrate"),
        ("potassium nitrate", "potassium_nitrate"),
        ("E 249", "potassium_nitrite"),
        ("INS 252", "potassium_nitrate"),
    ]:
        normalized, unrecognised = normalize_substance(name)
        assert normalized == expected, name
        assert unrecognised is False, name
