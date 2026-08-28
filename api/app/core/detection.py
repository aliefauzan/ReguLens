"""Work out what a document is from the document itself.

A first-time user should not have to know that "authority tier" exists, or which
of two jurisdiction codes their PDF belongs to. They have a file. Everything on
the old upload form except the file was us asking them to do our reading for us.

So this module reads the first pages and answers four questions: which country's
rules is this, what kind of source is it, who published it, and when does it take
effect. It is deterministic — keyword and date patterns, no model call — because
upload must stay fast and because a wrong guess here changes what the system is
allowed to do with the clauses later.

Every answer carries a confidence and the phrase it was read from, so the UI can
show its working and so an uncertain answer can be handed back to the user
instead of quietly defaulting. Nothing here mutates anything: `detect()` is a
pure function of the text.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.models import SourceType

# Reading the whole of a 100-page regulation to find its masthead is waste; the
# jurisdiction, the publisher and the entry-into-force clause all live near the
# front (or, for pasted chat messages, in the whole of a very short text).
MAX_SCAN_CHARS = 20_000

# A guess at or above this is shown as settled; below it the UI asks.
CERTAIN = 0.6


@dataclass(frozen=True)
class Guess:
    """One answer, what it was read from, and how sure we are.

    `evidence` is the literal text matched in the document — not a paraphrase.
    It is what lets the UI say "because it says «Official Journal of the
    European Union»" rather than asking to be trusted.
    """

    value: str | None
    confidence: float
    evidence: str | None = None

    @property
    def certain(self) -> bool:
        return self.value is not None and self.confidence >= CERTAIN


@dataclass(frozen=True)
class Detection:
    jurisdiction: Guess
    source_type: Guess
    source_name: Guess
    effective_date: Guess

    @property
    def needs_confirmation(self) -> bool:
        """True when the user has to answer something themselves.

        Only the two answers that change behaviour count: jurisdiction decides
        which market the clause lands in, source type decides how much the
        clause is allowed to do. A missing date or a fallback publisher name is
        editable but never blocking.
        """
        return not (self.jurisdiction.certain and self.source_type.certain)

    def to_dict(self) -> dict[str, Any]:
        return {
            "jurisdiction": asdict(self.jurisdiction),
            "source_type": asdict(self.source_type),
            "source_name": asdict(self.source_name),
            "effective_date": asdict(self.effective_date),
            "needs_confirmation": self.needs_confirmation,
        }


Signal = tuple[str, float]

# Weights are "how much does this phrase alone settle it". 1.0 phrases appear in
# one jurisdiction's documents and essentially nowhere else; 0.4–0.6 phrases are
# suggestive but appear in translations, commentary and quotations too.
JURISDICTION_SIGNALS: dict[str, list[Signal]] = {
    "EU": [
        (r"official journal of the european union", 1.0),
        (r"commission regulation \(e[uc]\)", 1.0),
        (r"regulation \(e[uc]\)\s*no", 1.0),
        (r"european parliament and of the council", 1.0),
        (r"european commission", 0.9),
        (r"european food safety authority|\befsa\b", 0.6),
        (r"\bcelex\b", 0.6),
        (r"union list of food additives", 0.6),
        (r"\be\s?\d{3}[a-z]?\b(?=[^\n]*\|)", 0.4),
    ],
    "ID_BPOM": [
        (r"badan pengawas obat dan makanan", 1.0),
        (r"\bbpom\b", 1.0),
        (r"peraturan badan pom", 1.0),
        (r"republik indonesia", 0.9),
        (r"\bperka\b", 0.8),
        (r"bahan tambahan pangan", 0.7),
        (r"kategori pangan", 0.6),
        (r"batas maksimal", 0.5),
        (r"menteri kesehatan", 0.5),
    ],
}

# Checked lowest-authority-first on a tie: if a text looks equally like a news
# report and like a regulation, it is the one that cannot change a verdict on
# its own. Being wrong in that direction costs a confirmation click; being wrong
# the other way lets a forwarded screenshot rewrite a limit.
SOURCE_TYPE_ORDER: list[SourceType] = [
    SourceType.SOCIAL_CHAT,
    SourceType.NEWS_ARTICLE,
    SourceType.INDUSTRY_ASSOCIATION,
    SourceType.OFFICIAL_GUIDANCE,
    SourceType.OFFICIAL_REGULATION,
]

SOURCE_TYPE_SIGNALS: dict[SourceType, list[Signal]] = {
    SourceType.SOCIAL_CHAT: [
        (r"\bforwarded\b|\bditeruskan\b", 1.0),
        (r"whatsapp|\bgrup wa\b|\bwa group\b", 1.0),
        (r"\bbroadcast\b|pesan berantai", 0.8),
        (r"\bsebarkan\b|please share|tolong share", 0.8),
    ],
    SourceType.NEWS_ARTICLE: [
        (r"\breuters\b|associated press|\bafp\b|bloomberg", 1.0),
        (r"the jakarta post|\bkompas\b|detik\.com|\btempo\.co\b|antaranews", 0.9),
        (r"\bcorrespondent\b|\bwartawan\b", 0.7),
        (r"reported (?:on|that)|dilaporkan bahwa", 0.6),
        (r"said in an interview|dalam wawancara", 0.6),
    ],
    SourceType.INDUSTRY_ASSOCIATION: [
        (r"\basosiasi\b|gabungan pengusaha|\bgapmmi\b", 0.9),
        (r"\b(?:industry|trade|producers?)\s+association\b", 0.9),
        (r"member(?:s'?)? bulletin|to our members", 0.9),
        (r"\bfederation of\b|\btrade body\b", 0.6),
    ],
    SourceType.OFFICIAL_GUIDANCE: [
        (r"surat edaran", 1.0),
        (r"notice to industry|guidance note", 1.0),
        (r"\bcircular\b|\bpedoman\b", 0.8),
        (r"\bguidelines?\b|petunjuk teknis", 0.6),
        (r"frequently asked questions", 0.6),
    ],
    SourceType.OFFICIAL_REGULATION: [
        (r"official journal|\bgazette\b|lembaran negara", 1.0),
        (r"commission regulation|regulation \(e[uc]\)", 1.0),
        (r"peraturan (?:badan|menteri|pemerintah|presiden)", 1.0),
        (r"undang-undang|\bdecree\b|\bkeputusan\b", 0.8),
        (r"\bpasal \d+", 0.6),
        (r"\bannex\b|\blampiran\b", 0.4),
        (r"\barticle \d+", 0.4),
    ],
}

# A document's own title is a better label than "European Commission", and it is
# what a user would call the thing. Fall back to the regulator only when the
# document does not name itself.
TITLE_PATTERNS: list[str] = [
    r"(?:commission\s+)?regulation\s*\((?:eu|ec)\)\s*(?:no\.?\s*)?[\d/]+",
    r"peraturan\s+badan\s+pom\s+nomor\s+\d+\s+tahun\s+\d{4}",
    r"peraturan\s+(?:menteri|pemerintah|presiden)[^\n.]{0,60}nomor\s+[\d/]+[^\n.]{0,40}",
    r"surat\s+edaran(?:\s+nomor)?\s+[\w./-]+",
    r"directive\s*\((?:eu|ec)\)\s*(?:no\.?\s*)?[\d/]+",
]

REGULATOR_BY_JURISDICTION: dict[str, str] = {
    "EU": "European Commission",
    "ID_BPOM": "Badan Pengawas Obat dan Makanan (BPOM)",
}

MONTHS: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    # Indonesian, including the two spellings that differ from English.
    "januari": 1, "februari": 2, "maret": 3, "mei": 5, "juni": 6, "juli": 7,
    "agustus": 8, "oktober": 10, "desember": 12,
}

# A date only counts as the effective date if the document ties it to taking
# effect. Regulations are full of other dates — adoption, signature, the date of
# the annex being amended — and picking one of those would be a confident lie.
EFFECT_CUE = (
    r"(shall apply from|applies from|application of this regulation from|"
    r"with effect from|takes? effect (?:on|from)|shall (?:enter|come) into force on|"
    r"enters? into force on|entry into force[:\s]|effective (?:from|on|date[:\s])|"
    r"mulai berlaku(?: pada)?(?: tanggal)?|berlaku (?:mulai|sejak|efektif)(?: tanggal)?)"
)

DATE_PATTERNS: list[str] = [
    r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
    r"(\d{4})-(\d{2})-(\d{2})",
    r"(\d{1,2})[./](\d{1,2})[./](\d{4})",
]


def _matches(haystack: str, signals: list[Signal]) -> tuple[float, str | None]:
    """Total weight of the signals present, plus the first phrase that hit."""
    score = 0.0
    evidence: str | None = None
    for pattern, weight in signals:
        found = re.search(pattern, haystack, re.IGNORECASE)
        if found:
            score += weight
            if evidence is None:
                evidence = found.group(0).strip()
    return score, evidence


def _confidence(winner: float, runner_up: float) -> float:
    """How separated the winner is, not how loud it is.

    A text that shouts both "BPOM" and "Official Journal" — a comparison table,
    a news piece about an EU rule in an Indonesian paper — should come out
    uncertain even though both scores are high.
    """
    return max(0.0, min(1.0, winner - runner_up))


def _detect_jurisdiction(haystack: str) -> Guess:
    scored = {
        code: _matches(haystack, signals) for code, signals in JURISDICTION_SIGNALS.items()
    }
    ranked = sorted(scored.items(), key=lambda item: item[1][0], reverse=True)
    (top_code, (top_score, evidence)), (_, (runner_score, _)) = ranked[0], ranked[1]
    if top_score <= 0:
        return Guess(value=None, confidence=0.0)
    return Guess(
        value=top_code,
        confidence=_confidence(top_score, runner_score),
        evidence=evidence,
    )


def _detect_source_type(haystack: str) -> Guess:
    scored = {
        source_type: _matches(haystack, signals)
        for source_type, signals in SOURCE_TYPE_SIGNALS.items()
    }
    # Sort by score, then by the conservative order for ties.
    ranked = sorted(
        scored.items(),
        key=lambda item: (item[1][0], -SOURCE_TYPE_ORDER.index(item[0])),
        reverse=True,
    )
    (top_type, (top_score, evidence)), (_, (runner_score, _)) = ranked[0], ranked[1]
    if top_score <= 0:
        return Guess(value=None, confidence=0.0)
    return Guess(
        value=str(top_type),
        confidence=_confidence(top_score, runner_score),
        evidence=evidence,
    )


def _detect_source_name(haystack: str, jurisdiction: str | None) -> Guess:
    for pattern in TITLE_PATTERNS:
        found = re.search(pattern, haystack, re.IGNORECASE)
        if found:
            title = re.sub(r"\s+", " ", found.group(0)).strip(" .,;:")[:200]
            return Guess(value=title, confidence=0.9, evidence=title)
    regulator = REGULATOR_BY_JURISDICTION.get(jurisdiction or "")
    if regulator:
        # Not read from the document — inferred from which country it belongs
        # to. Below the certainty line on purpose, so the UI leaves it editable.
        return Guess(value=regulator, confidence=0.4)
    return Guess(value=None, confidence=0.0)


def _parse_date(fragment: str) -> tuple[str, str] | None:
    """First date in the fragment, as `(iso, the text it was written as)`."""
    for pattern in DATE_PATTERNS:
        found = re.search(pattern, fragment)
        if not found:
            continue
        a, b, c = found.groups()
        try:
            if pattern.startswith(r"(\d{4})"):
                year, month, day = int(a), int(b), int(c)
            elif b.isdigit():
                day, month, year = int(a), int(b), int(c)
            else:
                month_number = MONTHS.get(b.lower())
                if month_number is None:
                    continue
                day, month, year = int(a), month_number, int(c)
        except ValueError:
            continue
        if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2999):
            continue
        return f"{year:04d}-{month:02d}-{day:02d}", found.group(0)
    return None


def _detect_effective_date(haystack: str) -> Guess:
    for cue in re.finditer(EFFECT_CUE, haystack, re.IGNORECASE):
        window = haystack[cue.end() : cue.end() + 80]
        parsed = _parse_date(window)
        if parsed:
            iso, as_written = parsed
            # The quote stops at the date. Carrying the rest of the sentence
            # into the UI ("…12 Januari 2026. Sebarkan ya.") reads as sloppy
            # and proves nothing extra.
            evidence = re.sub(r"\s+", " ", f"{cue.group(0)} {as_written}").strip()
            return Guess(value=iso, confidence=0.9, evidence=evidence[:120])
    return Guess(value=None, confidence=0.0)


def detect(text: str, filename: str | None = None) -> Detection:
    """Read a document's own words for the four things the upload form asked for.

    `filename` is scanned alongside the text: people name files `bpom-se-2026.pdf`
    and that is real evidence, but it is never the only evidence — the same
    patterns have to earn their weight wherever they appear.
    """
    haystack = f"{filename or ''}\n{text or ''}"[: MAX_SCAN_CHARS + 200]
    jurisdiction = _detect_jurisdiction(haystack)
    return Detection(
        jurisdiction=jurisdiction,
        source_type=_detect_source_type(haystack),
        source_name=_detect_source_name(haystack, jurisdiction.value),
        effective_date=_detect_effective_date(haystack),
    )
