"""Reading a document that does not fit in one request.

The worker answers a push inside 300 seconds and a dense four-page annex already
takes 174 of them, so a long document is read one piece per message. That buys
capacity and inherits every hazard of at-least-once delivery, which is what
these tests are about: a piece delivered twice, two pieces finishing at the same
instant, and a piece that never arrives.
"""

import pytest

from app.core.extraction import fanout


@pytest.fixture
def store(monkeypatch):
    """A Firestore stand-in that records writes and can lose a race."""
    jobs: dict[str, dict] = {}
    parts: dict[str, dict] = {}
    published: list[dict] = []

    class Snapshot:
        def __init__(self, data):
            self._data = data
            self.exists = data is not None

        def to_dict(self):
            return dict(self._data) if self._data else None

    class Ref:
        def __init__(self, bucket, key):
            self.bucket, self.key = bucket, key

        def get(self, transaction=None):
            return Snapshot(self.bucket.get(self.key))

        def set(self, data, merge=False):
            if merge and self.key in self.bucket:
                self.bucket[self.key] = self.bucket[self.key] | data
            else:
                self.bucket[self.key] = dict(data)

    class Query:
        def __init__(self, rows):
            self.rows = rows

        def where(self, **_kw):
            return self

        def limit(self, _n):
            return self

        def stream(self):
            return [Snapshot(r) for r in self.rows]

    class Collection:
        def __init__(self, name):
            self.name = name
            self.bucket = {"extraction_jobs": jobs, "extraction_parts": parts}.get(name, {})

        def document(self, key):
            return Ref(self.bucket, key)

        def where(self, **kw):
            return Query(list(parts.values())).where(**kw)

    class Transaction:
        def update(self, ref, data):
            ref.bucket[ref.key] = ref.bucket[ref.key] | data

    class DB:
        def collection(self, name):
            return Collection(name)

        def transaction(self):
            return Transaction()

    monkeypatch.setattr(fanout, "get_db", lambda: DB())
    monkeypatch.setattr(fanout.firestore, "SERVER_TIMESTAMP", "now", raising=False)
    monkeypatch.setattr(
        fanout.firestore, "transactional", lambda fn: (lambda transaction: fn(transaction))
    )
    monkeypatch.setattr(
        fanout, "publish", lambda topic, payload, **kw: published.append(payload)
    )
    # `process_chunk` imports this from the pipeline at call time, so the patch
    # has to land on the pipeline module rather than on this one.
    import app.core.extraction.pipeline as pipeline

    monkeypatch.setattr(
        pipeline, "_direct_samples", lambda text: ([{"text": text[:20]}], [{"text": text[:20]}])
    )
    return jobs, parts, published


def test_a_short_document_is_not_fanned_out():
    """The path the demo runs on must be untouched."""
    assert fanout.should_fan_out({"char_count": 12_000}) is False
    assert fanout.should_fan_out({}) is False


def test_a_long_document_is_fanned_out():
    assert fanout.should_fan_out({"char_count": 300_000}) is True


def test_a_document_beyond_the_ceiling_is_refused_not_truncated(monkeypatch, store):
    """A partly-read regulation produces a confident answer from the part we
    happened to reach, which is the failure this whole system exists to avoid."""
    from app.core.extraction.pipeline import PermanentExtractionError

    monkeypatch.setattr(fanout, "_begin", lambda _id: object())
    monkeypatch.setattr(fanout, "_load_text", lambda _doc: ("x", "pdfplumber"))
    monkeypatch.setattr(fanout, "split_for_extraction", lambda _t: ["c"] * 500)

    with pytest.raises(PermanentExtractionError) as caught:
        fanout.plan("doc_1")
    assert "Nothing was read" in str(caught.value)


def test_planning_publishes_one_message_per_piece(monkeypatch, store):
    jobs, _parts, published = store
    monkeypatch.setattr(fanout, "_begin", lambda _id: object())
    monkeypatch.setattr(fanout, "_load_text", lambda _doc: ("x", "pdfplumber"))
    monkeypatch.setattr(fanout, "split_for_extraction", lambda _t: ["a", "b", "c"])

    assert fanout.plan("doc_1")["chunks"] == 3
    assert [p["chunk_index"] for p in published] == [0, 1, 2]
    # Each message carries its own text: two consumers splitting the same
    # document with different settings would be reading different documents.
    assert [p["text"] for p in published] == ["a", "b", "c"]
    assert jobs["doc_1"]["total"] == 3


def test_a_piece_delivered_twice_overwrites_itself(store):
    """At-least-once delivery is the contract, not the exception."""
    _jobs, parts, _published = store
    fanout.process_chunk("doc_1", 2, "some text")
    fanout.process_chunk("doc_1", 2, "some text")
    assert len(parts) == 1
    assert parts["doc_1_0002"]["chunk_index"] == 2


def test_reducing_waits_for_every_piece(store):
    """A document missing a piece must stay unfinished rather than produce
    clauses from the parts that happened to land."""
    jobs, _parts, _published = store
    jobs["doc_1"] = {"document_id": "doc_1", "total": 3, "reduced": False}
    fanout.process_chunk("doc_1", 0, "a")
    fanout.process_chunk("doc_1", 1, "b")
    assert fanout.reduce_if_complete("doc_1") is None
    assert jobs["doc_1"]["reduced"] is False


def test_only_one_piece_wins_the_reduce(monkeypatch, store):
    """Two pieces finishing in the same instant is the ordinary case, not the
    rare one. Both will see every part present; exactly one may reduce."""
    jobs, _parts, _published = store
    jobs["doc_1"] = {"document_id": "doc_1", "total": 2, "reduced": False, "method": "pdfplumber"}
    fanout.process_chunk("doc_1", 0, "a")
    fanout.process_chunk("doc_1", 1, "b")

    applied: list[int] = []
    monkeypatch.setattr(fanout, "_parse_quality", lambda *_a: 0.9)
    monkeypatch.setattr(fanout, "_apply", lambda *a, **k: applied.append(1) or "result")
    monkeypatch.setattr(fanout, "RegulatoryDocument", lambda **_kw: object())

    # The real claim runs against the fake transaction in `store`, so the first
    # caller flips `reduced` and the second is refused by the same code path
    # production uses.
    first = fanout.reduce_if_complete("doc_1")
    second = fanout.reduce_if_complete("doc_1")
    assert first == "result"
    assert second is None
    assert len(applied) == 1
    assert jobs["doc_1"]["reduced"] is True
