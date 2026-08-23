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