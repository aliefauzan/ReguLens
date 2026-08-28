"""What a document says about itself, read without asking the user.

The upload form used to make a non-specialist declare a jurisdiction code and an
authority tier before it would accept their PDF. These tests protect the reading
that replaced those questions — and, more importantly, protect the *refusal* to
read: a text that could plausibly be either country, or that never says where it
came from, has to come back uncertain so the UI asks instead of guessing.
"""

import pytest

from app.core.detection import detect
from app.core.samples import BPOM_EXCERPT, EU_EXCERPT
from app.models import SourceType

CHAT = (
    "Forwarded from WA grup sebelah: Guys, BPOM naikin batas natrium benzoat "
    "jadi 500 mg/kg, mulai berlaku tanggal 12 Januari 2026. Sebarkan ya."
)
NEWS = (
    "JAKARTA (Reuters) - Indonesia's food and drug agency BPOM said on Tuesday it "
    "would tighten limits for benzoates in drinks. The change takes effect on "
    "1 March 2026, a correspondent reported."
)
CIRCULAR = (
    "SURAT EDARAN Nomor HK.02.02/2026 tentang Batas Maksimal Bahan Tambahan Pangan. "
    "Badan Pengawas Obat dan Makanan Republik Indonesia. "
    "Mulai berlaku pada tanggal 01/03/2026."
)


def test_the_eu_sample_reads_as_an_eu_regulation():
    found = detect(EU_EXCERPT)
    assert found.jurisdiction.value == "EU"
    assert found.source_type.value == str(SourceType.OFFICIAL_REGULATION)
    assert not found.needs_confirmation
    # The evidence is quoted from the document, not composed for the UI.
    assert found.jurisdiction.evidence
    assert found.jurisdiction.evidence.lower() in EU_EXCERPT.lower()


def test_the_bpom_sample_reads_as_an_indonesian_regulation():
    found = detect(BPOM_EXCERPT)
    assert found.jurisdiction.value == "ID_BPOM"
    assert found.source_type.value == str(SourceType.OFFICIAL_REGULATION)
    assert not found.needs_confirmation


def test_both_samples_name_themselves():
    assert "1129/2011" in (detect(EU_EXCERPT).source_name.value or "")
    assert "11 Tahun 2019" in (detect(BPOM_EXCERPT).source_name.value or "")


def test_a_forwarded_chat_message_is_not_mistaken_for_the_rule_it_quotes():
    """The whole authority-tier idea dies if this one is wrong: a screenshot
    that mentions BPOM must not be allowed to change a limit on its own."""
    found = detect(CHAT)
    assert found.source_type.value == str(SourceType.SOCIAL_CHAT)
    assert found.jurisdiction.value == "ID_BPOM"


def test_a_news_report_about_a_regulation_reads_as_news():
    found = detect(NEWS)
    assert found.source_type.value == str(SourceType.NEWS_ARTICLE)


def test_a_circular_reads_as_guidance_not_as_the_law():
    found = detect(CIRCULAR)
    assert found.source_type.value == str(SourceType.OFFICIAL_GUIDANCE)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (CHAT, "2026-01-12"),  # "mulai berlaku tanggal 12 Januari 2026"
        (NEWS, "2026-03-01"),  # "takes effect on 1 March 2026"
        (CIRCULAR, "2026-03-01"),  # "mulai berlaku pada tanggal 01/03/2026"
        (
            "This Regulation shall apply from 1 June 2013.",
            "2013-06-01",
        ),
        (
            "Effective date: 2026-07-15 for all categories.",
            "2026-07-15",
        ),
    ],
)
def test_effective_dates_are_read_in_both_languages_and_three_formats(text, expected):
    assert detect(text).effective_date.value == expected


def test_a_date_with_no_effect_wording_is_not_claimed_as_the_effective_date():
    """Regulations are full of dates — adoption, signature, the annex being
    amended. Picking one of those would be a confident lie."""
    text = "COMMISSION REGULATION (EU) No 1129/2011 of 11 November 2011 amending Annex II."
    assert detect(text).effective_date.value is None


def test_an_unattributed_limit_is_left_for_the_user_to_answer():
    found = detect("Sodium benzoate shall not exceed 200 mg/kg in soft drinks.")
    assert found.jurisdiction.value is None
    assert found.source_type.value is None
    assert found.needs_confirmation


def test_a_document_pulling_both_ways_is_uncertain_rather_than_confident():
    """A comparison table naming both regulators is exactly the case where a
    single-signal detector would be confidently wrong."""
    both = (
        "Comparison of limits. European Commission, Official Journal of the "
        "European Union. Badan Pengawas Obat dan Makanan, Peraturan Badan POM."
    )
    found = detect(both)
    assert found.jurisdiction.confidence < 0.6
    assert found.needs_confirmation


def test_the_filename_counts_as_evidence():
    found = detect("Batas maksimal 400 mg/kg.", filename="bpom-perka-11-2019.pdf")
    assert found.jurisdiction.value == "ID_BPOM"


def test_an_empty_document_claims_nothing():
    found = detect("")
    assert found.jurisdiction.value is None
    assert found.source_name.value is None
    assert found.effective_date.value is None
