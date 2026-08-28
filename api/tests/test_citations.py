"""Locating a clause inside the document it was read from.

The citation is the whole basis for trusting a number on screen. These tests
protect the two things that make it trustworthy: that it lands on the right
passage when it can, and that it admits it when it cannot.
"""

from app.core import citations

DOC = """Regulation (EC) No 1333/2008, Annex II Part E — Food category 14.1.4: Flavoured drinks.
Maximum level (mg/l or mg/kg as appropriate).
| E 200-202 | Sorbic acid – potassium sorbate | 300 | (1) (2) | excluding dairy-based drinks |
| E 210-213 | Benzoic acid — benzoates | 150 | (1) (2) | excluding dairy-based drinks |
| E 242 | Dimethyl dicarbonate | 250 | (24) |
"""


def test_a_verbatim_clause_is_found_exactly():
    clause = "| E 210-213 | Benzoic acid — benzoates | 150 | (1) (2) | excluding dairy-based drinks |"
    found = citations.locate(DOC, clause, "clause_1")
    assert found.match == "exact"
    assert DOC[found.start : found.end] == clause


def test_line_wrapping_does_not_break_the_match():
    """A PDF wraps a row across two lines; the clause quotes it as one."""
    wrapped = DOC.replace("Benzoic acid — benzoates | 150", "Benzoic acid — benzoates |\n150")
    clause = "| E 210-213 | Benzoic acid — benzoates | 150 | (1) (2) | excluding dairy-based drinks |"
    found = citations.locate(wrapped, clause, "clause_1")
    assert found.match == "exact"
    assert "150" in wrapped[found.start : found.end]


def test_a_tidied_quote_still_lands_on_the_right_row():
    """Models normalise punctuation. A dash swapped for a hyphen must not cost
    the reader their citation — but the result is labelled approximate."""
    clause = "| E 210-213 | Benzoic acid - benzoates | 150 | (1) (2) | excluding dairy based drinks |"
    found = citations.locate(DOC, clause, "clause_1")
    assert found.match in {"exact", "approximate"}
    assert "E 210-213" in DOC[found.start : found.end]


def test_a_passage_that_is_not_there_is_reported_missing():
    """Pointing at the nearest paragraph would be worse than pointing at
    nothing: the citation exists so the reader can trust what it points at."""
    found = citations.locate(DOC, "Cosmetics shall not contain lead.", "clause_1")
    assert found.match == "not_found"
    assert found.start == found.end == 0


def test_an_empty_document_cannot_be_cited():
    assert citations.locate("", "anything", "clause_1").match == "not_found"
    assert citations.locate(DOC, "", "clause_1").match == "not_found"


def test_every_clause_gets_an_answer():
    clauses = [
        {"id": "a", "text": "| E 242 | Dimethyl dicarbonate | 250 | (24) |"},
        {"id": "b", "text": "Nothing like this appears in the document."},
    ]
    found = citations.locate_all(DOC, clauses)
    assert [c.clause_id for c in found] == ["a", "b"]
    assert found[0].match == "exact"
    assert found[1].match == "not_found"


def test_the_snippet_shows_the_passage_in_context():
    clause = "| E 242 | Dimethyl dicarbonate | 250 | (24) |"
    found = citations.locate(DOC, clause, "clause_1")
    preview = citations.snippet(DOC, found)
    assert "Dimethyl dicarbonate" in preview
    # Context means the rows around it, so the reader can see where they are.
    assert "Benzoic acid" in preview
    assert citations.snippet(DOC, citations.locate(DOC, "absent", "x")) == ""


def test_the_offline_reader_quotes_the_document_it_read():
    """The fake extractor used to prefix the substance onto the row it quoted,
    which made its own clauses unfindable in their own document."""
    import json
    from pathlib import Path

    from app.core import library
    from app.core.extraction.llm import fake_candidates

    entries = json.loads(Path(library.__file__).with_name("library_data.json").read_text())
    text = next(e["text"] for e in entries if e["id"] == "bpom_11_2019_p766")
    for index, candidate in enumerate(fake_candidates(text)):
        if candidate.get("clause_type") != "numeric_limit":
            continue
        found = citations.locate(text, candidate["text"], f"clause_{index}")
        assert found.match == "exact", candidate["text"][:60]


BPOM_DOC = """Natrium benzoat (Sodium benzoate)
INS : 211
Batas
Nomor Maksimal
Kategori Nama Kategori Pangan (mg/kg)
14.1.3.3 Konsentrat Nektar Buah 1000
14.1.4.1 Minuman Berbasis Air Berperisa yang 400
Berkarbonat
14.1.4.2 Minuman Berbasis Air Berperisa Tidak 400
Berkarbonat, Termasuk Punches dan Ades
14.1.4.3 Konsentrat (Cair atau Padat) Untuk Minuman 900
Berbasis Air Berperisa
"""


def test_a_row_a_model_rewrote_is_still_found():
    """What a model actually returns from a wrapped table.

    It reflows the category name and appends the basis from the column header,
    which is a faithful reading of the row and a string that appears nowhere in
    the document. The row is still identifiable by its own number plus its
    limit, and that pair names one row and no other.
    """
    clause = (
        "14.1.4.2 Minuman Berbasis Air Berperisa Tidak Berkarbonat, Termasuk Punches "
        "dan Ades Batas Maksimal 400 mg/kg dihitung sebagai asam benzoat"
    )
    found = citations.locate(BPOM_DOC, clause, "clause_1")
    assert found.match == "approximate"
    span = BPOM_DOC[found.start : found.end]
    assert span.startswith("14.1.4.2")
    # Tight: the row and its wrapped continuation, not the rows around it.
    assert "14.1.4.3" not in span and "14.1.4.1" not in span


def test_the_row_fallback_needs_both_the_number_and_the_limit():
    """Either alone would match several rows. A citation that points at the
    wrong row is worse than one that admits it could not find it."""
    wrong_limit = "14.1.4.2 Minuman Berbasis Air Berperisa Batas Maksimal 777 mg/kg"
    assert citations.locate(BPOM_DOC, wrong_limit, "clause_1").match == "not_found"
    unknown_row = "99.9.9 Something Not In The Table Batas Maksimal 400 mg/kg"
    assert citations.locate(BPOM_DOC, unknown_row, "clause_1").match == "not_found"
