"""The bundled samples are the only path through the app for someone without a
regulation of their own, so they are load-bearing product surface, not fixtures.

What these tests protect: an edit to an excerpt that quietly stops producing the
numbers the UI promises. The samples page says the EU excerpt is stricter than
the Indonesian one; if that stops being true, the demo teaches a lie.
"""

import pytest

from app.core.extraction.llm import fake_candidates
from app.core.normalization import normalize_substance
from app.core.samples import (
    BPOM_EXCERPT,
    DEMO_PRODUCT,
    EU_EXCERPT,
    get_sample,
    list_samples,
)
from app.models import ProductIn


def _numeric_limits(text: str) -> list[float]:
    return [
        c["limit_value"]
        for c in fake_candidates(text)
        if c.get("clause_type") == "numeric_limit"
    ]


def test_eu_sample_yields_the_stricter_limit():
    assert _numeric_limits(EU_EXCERPT) == [150]


def test_bpom_sample_yields_the_looser_limit():
    assert _numeric_limits(BPOM_EXCERPT) == [400]


def test_the_two_samples_actually_disagree():
    """The whole demo rests on this divergence being real, not narrated."""
    assert _numeric_limits(EU_EXCERPT) != _numeric_limits(BPOM_EXCERPT)


@pytest.mark.parametrize("sample", list_samples())
def test_every_sample_is_complete_enough_to_submit(sample):
    for field in ("id", "title", "summary", "source_type", "source_name", "jurisdiction", "citation"):
        assert sample[field], f"{sample.get('id')} is missing {field}"
    assert len(sample["text"]) > 100, "an excerpt too short to extract from is not a sample"


def test_sample_ids_are_unique_and_addressable():
    ids = [s["id"] for s in list_samples()]
    assert len(ids) == len(set(ids))
    for sample_id in ids:
        assert get_sample(sample_id) is not None
    assert get_sample("no_such_sample") is None


def test_demo_product_validates_against_the_real_schema():
    """The seed endpoint builds this with ProductIn(**DEMO_PRODUCT); a typo here
    would 500 the one button a first-time user is told to press."""
    product = ProductIn(**DEMO_PRODUCT)
    assert product.target_markets == ["market_de", "market_id"]


def test_demo_product_ingredients_all_normalize():
    """An unrecognised ingredient matches no clause and renders as "no problems
    found" — the demo would show a false pass."""
    for ingredient in DEMO_PRODUCT["ingredients"]:
        _, unmatched = normalize_substance(ingredient["name"])
        assert unmatched is False, f"{ingredient['name']} does not normalize"


def test_demo_product_sits_between_the_two_limits():
    """300 mg/kg is the reason the same product reads differently in two
    markets. If it drifts outside 150..400, the demo stops demonstrating."""
    benzoate = next(
        i for i in DEMO_PRODUCT["ingredients"] if normalize_substance(i["name"])[0] == "sodium_benzoate"
    )
    assert _numeric_limits(EU_EXCERPT)[0] < benzoate["amount"] < _numeric_limits(BPOM_EXCERPT)[0]
