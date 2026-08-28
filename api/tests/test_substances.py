"""Working out what somebody meant by an ingredient name.

The strict matcher exists so a wrong mapping can never happen silently. The cost
of that strictness is a row that matches nothing and looks like a pass. These
tests pin the half that pays the cost back: saying what we think was meant,
without deciding it.
"""

import pytest

from app.core.substances import resolve, suggest


def test_a_known_additive_is_recognised():
    found = resolve("sodium benzoate")
    assert found.recognised
    assert found.canonical == "sodium_benzoate"
    assert found.kind == "additive"


@pytest.mark.parametrize("query", ["E211", "e 211", "INS 211", "211", "e-211"])
def test_numbers_are_understood_however_they_are_written(query):
    found = resolve(query)
    assert found.recognised, query
    assert found.canonical == "sodium_benzoate"


def test_a_misspelling_offers_the_name_back():
    found = resolve("sodium benzoat")
    assert not found.recognised
    assert "sodium_benzoate" in {item.canonical for item in found.suggestions}


def test_a_partial_name_offers_the_family():
    found = resolve("benzoate")
    canonicals = {item.canonical for item in found.suggestions}
    assert {"sodium_benzoate", "benzoic_acid"} <= canonicals


def test_meat_is_told_it_is_food_not_a_mistake():
    """The case that sent a user asking. "meat" is not misspelled and it is not
    an additive; answering "unrecognised" would be true and useless."""
    found = resolve("meat")
    assert found.kind == "food"
    assert not found.recognised
    assert "not an additive" in found.message
    # And it must not pretend the product was checked against it.
    assert "does not mean the product passed" in found.message


@pytest.mark.parametrize("query", ["daging ayam", "wheat flour", "susu bubuk", "minyak sawit"])
def test_foods_in_either_language_are_understood_as_foods(query):
    assert resolve(query).kind == "food"


@pytest.mark.parametrize("query", ["preservative", "pengawet", "artificial sweetener"])
def test_a_function_word_asks_for_the_substance(query):
    found = resolve(query)
    assert found.kind == "function"
    assert "which one" in found.message


def test_a_genuinely_unknown_name_says_nothing_is_checked():
    found = resolve("zorblax extract")
    assert found.kind == "unknown"
    assert not found.suggestions
    assert "nothing will be checked against it" in found.message


def test_suggestions_are_not_offered_for_anything_distant():
    """Inviting a wrong pick is worse than offering nothing."""
    assert suggest("qqqqqqq") == []


def test_an_empty_query_asks_for_a_name():
    found = resolve("   ")
    assert found.kind == "unknown"
    assert not found.suggestions


def test_a_food_the_dictionary_knows_is_still_a_food():
    """"ginger" normalizes, so the strict matcher says yes — but no additive
    annex sets a limit for ginger, and promising it "will be checked" invents a
    rule that does not exist."""
    found = resolve("ginger")
    assert found.recognised
    assert found.kind == "food"
    assert "not an additive" in found.message


def test_an_additive_the_dictionary_knows_promises_a_check():
    found = resolve("aspartame")
    assert found.kind == "additive"
    assert "will be checked" in found.message
