"""The bundled library is the answer to "why do I have to add a regulation?".

It is product surface, not a fixture: if an entry stops being a faithful slice
of the corpus, the app teaches a lie with a citation attached to it. These tests
pin the parts that would rot silently — the citations, the jurisdiction each
entry claims, the starter set, and the divergence the whole demo rests on.
"""

import json
import re
from pathlib import Path

import pytest

from app.core import library
from app.core.normalization import normalize_substance
from app.models import DocumentIn, SourceType

ENTRIES = library.list_entries()
RAW = json.loads((Path(library.__file__).with_name("library_data.json")).read_text())
BY_ID = {entry["id"]: entry for entry in RAW}


def test_the_library_is_not_empty_and_covers_both_markets():
    jurisdictions = {entry["jurisdiction"] for entry in ENTRIES}
    assert jurisdictions == {"EU", "ID_BPOM"}
    assert len(ENTRIES) >= 20, "a library this small is a demo, not a rulebook"


@pytest.mark.parametrize("entry", RAW, ids=lambda e: e["id"])
def test_every_entry_is_complete_enough_to_ingest(entry):
    """An entry has to survive the same validation as a user's own upload."""
    meta = DocumentIn(
        source_type=SourceType(entry["source_type"]),
        source_name=entry["source_name"],
        jurisdiction=entry["jurisdiction"],
    )
    assert meta.jurisdiction in {"EU", "ID_BPOM"}
    assert entry["text"].strip()
    assert entry["citation"].strip()
    assert entry["summary"].strip()
    assert entry["product_types"], "an entry nobody can be matched against is noise"


@pytest.mark.parametrize("entry", RAW, ids=lambda e: e["id"])
def test_every_entry_carries_a_citation_that_names_its_source(entry):
    citation = entry["citation"]
    if entry["jurisdiction"] == "EU":
        assert "1333/2008" in citation and "Annex II" in citation
    else:
        assert "11 Tahun 2019" in citation and "page" in citation


@pytest.mark.parametrize("entry", RAW, ids=lambda e: e["id"])
def test_the_text_states_its_unit_basis(entry):
    """Extraction reads the unit from the table header. A block that never says
    mg/kg anywhere produces limits with no unit, which the guardrail rejects."""
    assert "mg/kg" in entry["text"] or "mg/l" in entry["text"]


@pytest.mark.parametrize("entry", RAW, ids=lambda e: e["id"])
def test_the_text_is_a_table_with_numbers_in_it(entry):
    """Not a proof of accuracy — a proof that the excerpt is the limit table and
    not the preamble that happens to sit above it."""
    assert re.search(r"\d", entry["text"])
    rows = [line for line in entry["text"].split("\n") if line.strip()]
    assert len(rows) >= 8


def test_ids_are_unique():
    ids = [entry["id"] for entry in RAW]
    assert len(ids) == len(set(ids))


def test_the_starter_set_exists_and_covers_both_markets():
    known = {entry["id"] for entry in RAW}
    missing = [entry_id for entry_id in library.STARTER_IDS if entry_id not in known]
    assert not missing, f"starter set names rules that do not exist: {missing}"
    starter = [BY_ID[entry_id] for entry_id in library.STARTER_IDS]
    assert {entry["jurisdiction"] for entry in starter} == {"EU", "ID_BPOM"}
    # One button, one wait. Every starter entry is a separate extraction run.
    assert len(library.STARTER_IDS) <= 10


def test_the_starter_set_answers_the_demo_product():
    """The seeded product is a drink powder with sodium benzoate in it. If the
    starter set does not carry a benzoate limit in both markets, the first thing
    a new user sees is still 'no rules added yet'."""
    starter = [BY_ID[entry_id] for entry_id in library.STARTER_IDS]
    eu = [e for e in starter if e["jurisdiction"] == "EU"]
    bpom = [e for e in starter if e["jurisdiction"] == "ID_BPOM"]
    assert any("Benzoic acid" in e["text"] for e in eu)
    assert any("benzoat" in e["text"].lower() for e in bpom)


def test_the_two_markets_still_disagree_about_benzoates():
    """The premise of the product. EU flavoured drinks cap benzoates at 150
    mg/kg; the Indonesian table for the same kind of drink allows more."""
    eu = BY_ID["eu_annex_ii_14_1_4"]["text"]
    assert re.search(r"E 210-213 \| Benzoic acid [—-] benzoates \| 150", eu)
    bpom = BY_ID["bpom_11_2019_p766"]["text"]
    assert "14.1.4.1" in bpom
    row = next(line for line in bpom.split("\n") if line.startswith("14.1.4.1"))
    assert "400" in row


def test_substances_named_in_the_library_normalize():
    """A limit for a substance the dictionary cannot match is a limit nobody
    will ever be compared against."""
    for name in ("Benzoic acid — benzoates", "natrium benzoat", "aspartam", "tartrazin"):
        _, unnormalized = normalize_substance(name)
        assert not unnormalized, f"{name} does not normalize"


def test_entry_listing_hides_the_text_but_keeps_the_label():
    entry = ENTRIES[0]
    assert "text" not in entry
    assert entry["title"] and entry["citation"]
    assert isinstance(entry["starter"], bool)


def test_a_truncated_entry_says_so():
    """Some categories are longer than one extraction pass. Cutting is fine;
    pretending the excerpt is the whole category is not."""
    for entry in RAW:
        assert isinstance(entry["truncated"], bool)


def test_library_entries_read_as_tables_offline():
    """FAKE_LLM has to reflect the library, not paper over it.

    Before the library existed the offline extractor answered every document
    with the same canned pair, which would have made twenty-eight different
    rules look identical — and disagree with themselves. It now reads the rows
    that are actually there.
    """
    from app.core.extraction.llm import fake_candidates

    eu = [c for c in fake_candidates(BY_ID["eu_annex_ii_14_1_4"]["text"]) if c.get("limit_value")]
    bpom = [c for c in fake_candidates(BY_ID["bpom_11_2019_p766"]["text"]) if c.get("limit_value")]
    assert len({c["limit_value"] for c in eu}) > 3, "one canned answer per document again"
    assert any("Benzoic acid" in c["substance"] and c["limit_value"] == 150 for c in eu)
    assert any("14.1.4.1" in c["text"] and c["limit_value"] == 400 for c in bpom)
    # Every numeric row states the unit its table's header gave.
    assert all(c["unit_raw"] == "mg/kg" for c in eu + bpom)


def test_the_offline_reader_labels_supplements_and_drinks_apart():
    """Category numbers decide the product kind, not words in the rows — a
    bakery table mentions milk, and a preservative table mentions supplements."""
    from app.core.extraction.llm import fake_candidates

    drinks = fake_candidates(BY_ID["eu_annex_ii_14_1_4"]["text"])
    supplements = fake_candidates(BY_ID["eu_annex_ii_17_1"]["text"])
    bakery = fake_candidates(BY_ID["eu_annex_ii_07_2"]["text"])
    assert {c["product_type"] for c in drinks if c.get("limit_value")} == {"food_beverage_liquid"}
    assert {c["product_type"] for c in supplements if c.get("limit_value")} == {"supplement"}
    assert {c["product_type"] for c in bakery if c.get("limit_value")} == {"food_solid"}
