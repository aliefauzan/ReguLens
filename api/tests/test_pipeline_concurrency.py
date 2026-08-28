"""The upload-to-flip path was measured at 183s against a 90s target, and
almost all of it was work waiting on other work that had no reason to wait.

Three things were serial and are not any more:
  - the two extraction samples, which are independent by construction;
  - the embedding call, which ran once per clause instead of once per document;
  - the worker's blocking handlers, which held the event loop and made a
    document's clauses reconcile in single file no matter how many Pub/Sub
    deliveries were in flight.

These tests assert the shape of the fix, not a stopwatch reading: parallelism
and batching are properties of the call graph, and a timing assertion in CI
would be flaky theatre.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.core.extraction import pipeline


def test_the_two_samples_run_at_the_same_time(monkeypatch):
    """Each sample blocks on a barrier the other has to reach. In sequence this
    deadlocks and times out; in parallel both pass through."""
    barrier = threading.Barrier(2, timeout=5)
    seen: list[int] = []

    def fake_generate(text, *, sample_index):
        barrier.wait()
        seen.append(sample_index)
        return [{"text": f"sample {sample_index}", "clause_type": "other"}]

    monkeypatch.setattr(pipeline, "generate_candidates", fake_generate)

    samples = pipeline._direct_samples("some regulation text")

    assert sorted(seen) == [0, 1]
    # Order matters downstream: sample 0 supplies the candidates that become
    # clauses, sample 1 only supplies the self-consistency comparison.
    assert samples[0][0]["text"] == "sample 0"
    assert samples[1][0]["text"] == "sample 1"


def test_a_transient_failure_in_either_sample_still_nacks(monkeypatch):
    """Parallelism must not swallow the classification the worker acks on."""
    from app.core.extraction.llm import TransientLLMError

    def fake_generate(text, *, sample_index):
        if sample_index == 1:
            raise TransientLLMError("429 quota")
        return []

    monkeypatch.setattr(pipeline, "generate_candidates", fake_generate)

    with pytest.raises(pipeline.TransientExtractionError):
        pipeline._direct_samples("text")


def test_a_permanent_failure_in_either_sample_still_fails_the_document(monkeypatch):
    from app.core.extraction.llm import PermanentLLMError

    def fake_generate(text, *, sample_index):
        if sample_index == 0:
            raise PermanentLLMError("unparseable")
        return []

    monkeypatch.setattr(pipeline, "generate_candidates", fake_generate)

    with pytest.raises(pipeline.PermanentExtractionError):
        pipeline._direct_samples("text")


class _Candidate:
    def __init__(self, text: str) -> None:
        self.text = text


def test_a_document_is_embedded_in_one_call_not_one_per_clause(monkeypatch):
    calls: list[list[str]] = []
    stored: dict[str, list[float]] = {}

    def fake_embed_texts(texts):
        calls.append(list(texts))
        return [[float(i)] for i, _ in enumerate(texts)]

    monkeypatch.setattr("app.core.reconciliation.embed_texts", fake_embed_texts)
    monkeypatch.setattr("app.core.clauses.store_embeddings", stored.update)

    candidates = [_Candidate(f"clause {i}") for i in range(5)]
    pipeline._embed_batch(candidates, [f"id_{i}" for i in range(5)])

    assert len(calls) == 1, "one document, one embedding request"
    assert calls[0] == [f"clause {i}" for i in range(5)]
    assert stored["id_3"] == [3.0]


def test_a_failed_batch_leaves_extraction_alone(monkeypatch):
    """Reconciliation still embeds a clause it finds without a vector, so the
    batch is a fast path. Losing it must not lose the document."""

    def boom(texts):
        raise RuntimeError("embedding backend down")

    monkeypatch.setattr("app.core.reconciliation.embed_texts", boom)

    pipeline._embed_batch([_Candidate("clause")], ["id_0"])  # must not raise


def test_embed_texts_batches_rather_than_looping(monkeypatch):
    """FAKE_LLM has no backend to count calls against, so this checks the real
    contract instead: every text in, one vector each out, same order."""
    from app.core import reconciliation

    monkeypatch.setenv("FAKE_LLM", "1")
    from app.settings import get_settings

    get_settings.cache_clear()
    try:
        expected = 40  # more than one EMBED_BATCH, so chunking is exercised
        texts = [f"clause {i}" for i in range(expected)]
        vectors = reconciliation.embed_texts(texts)
        assert expected > reconciliation.EMBED_BATCH
        assert len(vectors) == expected
        assert vectors[0] == reconciliation.embed_text("clause 0")
        assert vectors[7] != vectors[8]
    finally:
        get_settings.cache_clear()


def test_a_short_document_is_one_part(monkeypatch):
    """The path a pasted announcement takes must not change because long annexes
    needed splitting."""
    from app.core.extraction.text import split_for_extraction

    assert split_for_extraction("one short rule.") == ["one short rule."]
    assert split_for_extraction("") == []


def test_splitting_never_cuts_a_line_in_half():
    """A limit table row carries its substance and its number on one line. Half
    a row is a wrong clause, which is worse than a missing one."""
    from app.core.extraction.text import split_for_extraction

    rows = "\n\n".join(f"| E 21{i} | Benzoic acid | {100 + i} |" for i in range(400))
    chunks = split_for_extraction(rows, max_chars=500)

    assert len(chunks) > 1
    for chunk in chunks:
        for line in chunk.splitlines():
            assert line == "" or line.count("|") == 4, line
    # Nothing lost, nothing duplicated.
    assert sum(c.count("| E 2") for c in chunks) == 400


def test_an_oversized_paragraph_is_left_whole():
    from app.core.extraction.text import split_for_extraction

    giant = "x" * 5000
    assert split_for_extraction(f"{giant}\n\nshort", max_chars=1000) == [giant, "short"]


def test_every_part_is_extracted_and_scored_against_its_own_twin(monkeypatch):
    """Self-consistency compares two samples of the SAME text. Scoring page one
    against page four would be a number with no meaning behind it."""
    seen: list[tuple[str, int]] = []

    def fake_generate(text, *, sample_index):
        seen.append((text[:12], sample_index))
        return [{"text": text[:12], "clause_type": "other"}]

    monkeypatch.setattr(pipeline, "generate_candidates", fake_generate)
    monkeypatch.setattr("app.core.extraction.text.CHUNK_CHARS", 40)

    text = "\n\n".join(f"part number {i} of the document" for i in range(4))
    pairs = pipeline._direct_pairs(text)

    assert len(pairs) > 1, "a long document must split"
    for primary, secondary in pairs:
        # Both halves of a pair saw the same text.
        assert primary[0]["text"] == secondary[0]["text"]
    assert len(seen) == len(pairs) * 2


def test_reconcile_does_not_hold_the_worker_event_loop(monkeypatch):
    """The regression this whole file exists for: `async def` handlers calling
    blocking work directly serialise every delivery on one instance."""
    import asyncio
    import inspect

    from app import worker

    source = inspect.getsource(worker)
    for call in ("reconcile_clause", "run_impact", "run_extraction"):
        assert f"run_in_threadpool({call}" in source, f"{call} runs on the event loop"

    # And prove the mechanism, not just the spelling: a blocking call handed to
    # the threadpool lets the loop keep running.
    async def drive():
        from fastapi.concurrency import run_in_threadpool

        ticks = 0
        task = asyncio.create_task(run_in_threadpool(time.sleep, 0.2))
        while not task.done():
            await asyncio.sleep(0.01)
            ticks += 1
        return ticks

    assert asyncio.run(drive()) > 1
