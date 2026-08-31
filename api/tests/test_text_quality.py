"""parse_quality is deterministic: same bytes, same score, no model involved."""

from app.core.extraction.text import compute_parse_quality, decode_penalty


def test_no_content_scores_floor():
    assert compute_parse_quality(char_count=0, page_count=0) == 0.05


def test_dense_text_layer_scores_high():
    text = "x" * 2000
    score = compute_parse_quality(char_count=2000, page_count=1, text=text)
    assert score > 0.95


THIN = "word " * 40  # ~200 chars over one page


def test_thin_text_layer_scores_midrange():
    score = compute_parse_quality(char_count=200, page_count=1, text=THIN)
    assert 0.1 < score < 0.6


def test_ocr_penalty_applies():
    dense = "y" * 3000
    plain = compute_parse_quality(char_count=3000, page_count=2, method="pdfplumber", text=dense)
    ocr = compute_parse_quality(char_count=3000, page_count=2, method="ocr", text=dense)
    assert ocr < plain


def test_corrupt_characters_lower_the_score():
    clean = "clean regulatory text. " * 100
    corrupt = clean + ("�" * 50)
    clean_score = compute_parse_quality(char_count=len(clean), page_count=1, text=clean)
    corrupt_score = compute_parse_quality(char_count=len(corrupt), page_count=1, text=corrupt)
    assert corrupt_score < clean_score


def test_decode_penalty_bounds():
    assert decode_penalty("") == 1.0
    assert decode_penalty("perfectly fine text") == 0.0

# ---------------------------------------------------------------------------
# What reading a long PDF is allowed to cost
# ---------------------------------------------------------------------------


def test_every_page_is_flushed_as_it_is_read(monkeypatch):
    """pdfplumber caches every character object it parses onto the page, and the
    page is held by the document for the whole loop — so reading page 900 still
    holds pages 1 through 899. Measured on the 1156-page BPOM annex already in
    `data/`: 5612 MB peak without the flush, 119 MB with it. Cloud Run killed
    the container at 512 MiB and again at 1 GiB before this was found, each time
    mid-check, which left the watched source displaying the *previous* run's
    error as though it were current.

    The test pins the call, not the megabytes: a memory assertion would be flaky
    across machines, while dropping the flush is the one edit that reintroduces
    the bug.
    """
    import io

    from app.core.extraction import text as text_module

    flushed = []

    class FakePage:
        def __init__(self, n):
            self.n = n

        def extract_text(self):
            return f"page {self.n}"

        def flush_cache(self):
            flushed.append(self.n)

    class FakePdf:
        pages = [FakePage(1), FakePage(2), FakePage(3)]

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class FakePlumber:
        @staticmethod
        def open(_stream):
            return FakePdf()

    monkeypatch.setitem(__import__("sys").modules, "pdfplumber", FakePlumber)
    result = text_module.extract_pdf(io.BytesIO(b"%PDF-1.4").getvalue())

    assert flushed == [1, 2, 3], "every page must be flushed, not just the last"
    assert result.page_count == 3
    assert "page 2" in result.text
