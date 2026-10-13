"""Block review findings 2 and 7: reranker download and BM25 rebuild under timeouts."""

import asyncio
import threading
import time
from typing import Any

import pytest

from app.db.pool import Pool
from app.rag import retriever
from tests.fixtures.kb import add_document

pytestmark = pytest.mark.req("REQ-RAG-04", "REQ-REL-01")


async def test_bm25_rebuild_survives_a_cancelled_caller(
    db_pool: Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add_document(db_pool, "https://www.getnet.com.br/x", "X", "pt", [("S", "get smart")])
    monkeypatch.setattr(retriever, "_cache", retriever.IndexCache())
    real = retriever.Bm25Index

    def slow_index(rows: Any) -> Any:
        time.sleep(0.3)
        return real(rows)

    monkeypatch.setattr(retriever, "Bm25Index", slow_index)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(retriever.bm25_index(db_pool), 0.05)
    await asyncio.sleep(0.6)
    assert retriever._cache.index is not None  # the build finished and was kept
    assert retriever._cache.fingerprint is not None


def test_concurrent_rerank_during_download_fails_fast() -> None:
    ranker = retriever.FlashRankReranker()
    ranker._lock.acquire()  # another thread is downloading the model
    try:
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="warming up"):
            ranker.rerank("q", ["p"])
        assert time.monotonic() - started < 0.5  # no thread parked on the lock
    finally:
        ranker._lock.release()


def test_failed_warmup_removes_a_partial_model_dir(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "flashrank" / retriever.RERANK_MODEL
    model_dir.mkdir(parents=True)
    (model_dir / "half-extracted.onnx").write_bytes(b"x")
    monkeypatch.setattr(retriever, "_flashrank_dir", lambda: tmp_path / "flashrank")

    def broken(**_: Any) -> Any:
        raise OSError("corrupted model")

    monkeypatch.setattr(retriever, "Ranker", broken)
    with pytest.raises(OSError):
        retriever.warm_reranker()
    assert not model_dir.exists()


def test_warmup_loads_the_model_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    calls: list[Any] = []

    class FakeRanker:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

        def rerank(self, request: Any) -> list[dict[str, Any]]:
            return [{"id": 0, "score": 0.9}]

    monkeypatch.setattr(retriever, "Ranker", FakeRanker)
    monkeypatch.setattr(retriever, "_flashrank_dir", lambda: tmp_path / "flashrank")
    monkeypatch.setattr(retriever, "_reranker", None)
    retriever.warm_reranker()
    assert retriever.get_reranker().rerank("q", ["p"]) == [(0, 0.9)]
    assert len(calls) == 1
    assert threading.active_count() >= 1
