"""The pack an auditor is handed.

A screenshot is not an answer to "why does it say that". These tests pin that
the pack carries the rule as written, where it came from, the arithmetic that
was done, and the hash proving the file behind the quote is the file that was
read — and that it admits, rather than hides, the parts it can no longer
support.
"""

import json

from app.core import evidence

PRODUCT = {
    "name": "Herbal Drink Powder",
    "product_type": "food_beverage_powder",
    "target_markets": ["market_de"],
    "compliance_status": {"market_de": "non_compliant"},
}
REQUIREMENT = {
    "id": "req_1",
    "requirement_key": "prod_1:market_de:clause_1",
    "product_id": "prod_1",
    "market_id": "market_de",
    "jurisdiction": "EU",
    "clause_id": "clause_1",
    "document_id": "doc_1",
    "substance_normalized": "sodium_benzoate",
    "evaluation": "fail",
    "comparable_value": 300.0,
    "comparable_limit": 150.0,
    "comparable_unit": "mg_per_kg",
    "product_value": 0.03,
    "product_unit": "percent_w_w",
    "limit_value": 150.0,
    "unit": "mg_per_kg",
}
CLAUSE = {
    "text": "The maximum permitted level of E 211 in flavoured drinks is 150 mg/kg.",
    "clause_type": "numeric_limit",
    "status": "active",
    "confidence": 0.81,
    "document_id": "doc_1",
}
DOCUMENT = {
    "source_name": "Commission Regulation (EU) No 1129/2011",
    "source_type": "official_regulation",
    "jurisdiction": "EU",
    "origin": "watched_source",
    "content_sha256": "abc123",
}


def install(monkeypatch, *, requirements=None, clauses=None, documents=None, events=None,
            product=PRODUCT):
    class Snapshot:
        def __init__(self, data, doc_id="x"):
            self._data = data
            self.id = doc_id

        @property
        def exists(self):
            return self._data is not None

        def to_dict(self):
            return self._data

    class Ref:
        def __init__(self, snapshot):
            self._snapshot = snapshot

        def get(self):
            return self._snapshot

    class Collection:
        def __init__(self, name, db):
            self.name = name
            self.db = db

        def document(self, doc_id):
            store = {"products": {"prod_1": product}, "clauses": clauses or {},
                     "documents": documents or {}}[self.name]
            return Ref(Snapshot(store.get(doc_id), doc_id))

        def where(self, **_kw):
            return self

        def limit(self, _n):
            return self

        def stream(self):
            rows = {"requirements": requirements or [], "graph_events": events or []}[self.name]
            return [Snapshot(dict(r), r.get("id", "x")) for r in rows]

    class DB:
        def collection(self, name):
            return Collection(name, self)

    monkeypatch.setattr(evidence, "get_db", lambda: DB())


def test_the_pack_quotes_the_rule_as_the_regulator_wrote_it(monkeypatch):
    install(monkeypatch, requirements=[REQUIREMENT], clauses={"clause_1": CLAUSE},
            documents={"doc_1": DOCUMENT})
    pack = evidence.build("prod_1")
    finding = pack["findings"][0]
    assert finding["rule"]["text"].startswith("The maximum permitted level")
    assert finding["source"]["source_name"] == "Commission Regulation (EU) No 1129/2011"


def test_the_pack_shows_the_arithmetic_in_both_forms(monkeypatch):
    """0.03% and 300 mg/kg are the same number. A pack that shows only one of
    them asks the reader to take the conversion on trust."""
    install(monkeypatch, requirements=[REQUIREMENT], clauses={"clause_1": CLAUSE},
            documents={"doc_1": DOCUMENT})
    comparison = evidence.build("prod_1")["findings"][0]["comparison"]
    assert comparison["product_value"] == 300.0
    assert comparison["limit"] == 150.0
    assert comparison["product_value_as_entered"] == 0.03
    assert comparison["product_unit_as_entered"] == "percent_w_w"


def test_the_source_hash_travels_with_the_quote(monkeypatch):
    install(monkeypatch, requirements=[REQUIREMENT], clauses={"clause_1": CLAUSE},
            documents={"doc_1": DOCUMENT})
    assert evidence.build("prod_1")["findings"][0]["source"]["content_sha256"] == "abc123"


def test_a_deleted_rule_is_marked_not_dropped(monkeypatch):
    """A pack that quietly omits what it cannot support is worse than one that
    admits it."""
    install(monkeypatch, requirements=[REQUIREMENT], clauses={}, documents={})
    pack = evidence.build("prod_1")
    assert pack["findings"][0]["rule"]["available"] is False
    assert pack["coverage"]["rules_no_longer_on_file"] == 1
    assert pack["coverage"]["sources_no_longer_on_file"] == 1


def test_the_pack_states_what_it_is_not(monkeypatch):
    """It is not signed, and it only knows what ReguLens read."""
    install(monkeypatch, requirements=[], clauses={}, documents={})
    limitations = " ".join(evidence.build("prod_1")["limitations"])
    assert "not signed" in limitations
    assert "nobody uploaded" in limitations


def test_the_pack_hashes_itself_and_survives_being_written_to_a_file(monkeypatch):
    install(monkeypatch, requirements=[REQUIREMENT], clauses={"clause_1": CLAUSE},
            documents={"doc_1": DOCUMENT})
    pack = evidence.build("prod_1")
    assert len(pack["content_hash"]) == 64
    json.dumps(pack)  # must not raise: a pack that cannot be saved is not a pack


def test_an_unknown_product_is_a_miss_not_an_empty_pack(monkeypatch):
    install(monkeypatch, product=None)
    try:
        evidence.build("prod_missing")
    except KeyError:
        return
    raise AssertionError("a pack for a product that does not exist must not be produced")
