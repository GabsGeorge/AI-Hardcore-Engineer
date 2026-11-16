"""Hybrid retrieval (ADR 0003, research R-03/R-04/R-05).

Per query: top-20 BM25 (bm25s, in memory) + top-20 dense (pgvector cosine) → RRF (k = 60) → the
fused top-30 reranked by the FlashRank cross-encoder → top-5 at or above RAG_RELEVANCE_THRESHOLD.
Multi-query (PT↔EN variants) is done by the Knowledge agent, one call per variant.

The BM25 index is built from `chunks` on first use and rebuilt when the fingerprint
`(count(*), max(id))` changes, checked at most every REFRESH_SECONDS. Ingestion replaces the chunks
of a changed document (new ids), so any change moves the fingerprint.
"""

import asyncio
import math
import os
import re
import threading
import time
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import bm25s
from bm25s.stopwords import STOPWORDS_EN, STOPWORDS_PORTUGUESE
from flashrank import Ranker, RerankRequest

from app.core.config import get_settings
from app.core.llm import get_embeddings
from app.db.pool import Pool, get_pool
from app.rag.chunking import passage
from app.tools.interfaces import KnowledgeHit

RRF_K = 60
CANDIDATES = 20
RERANK_POOL = 30
TOP_K = 5
REFRESH_SECONDS = 60.0
RERANK_MODEL = "ms-marco-MultiBERT-L-12"


def _fold(text: str) -> str:
    """Lowercase without accents: "Antecipação" → "antecipacao"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


_STOPWORDS = frozenset(_fold(w) for w in (*STOPWORDS_EN, *STOPWORDS_PORTUGUESE))
_WORD = re.compile(r"\w+")


def tokenize(text: str) -> list[str]:
    """Lowercase, no accents, no PT ∪ EN stopwords, no stemming (the PT↔EN rewrite covers
    variations)."""
    return [t for t in _WORD.findall(_fold(text)) if t not in _STOPWORDS]


class Bm25Index:
    def __init__(self, rows: Sequence[tuple[int, str, str]]) -> None:
        """rows: (chunk id, lang, passage text)."""
        self.ids = [r[0] for r in rows]
        self.langs = [r[1] for r in rows]
        self._model = bm25s.BM25()
        if rows:
            self._model.index([tokenize(r[2]) for r in rows], show_progress=False)

    def search(self, query: str, k: int, lang: str | None = None) -> list[int]:
        tokens = tokenize(query)
        if not self.ids or not tokens:
            return []
        docs, scores = self._model.retrieve([tokens], k=len(self.ids), show_progress=False)
        ranked = [
            self.ids[d]
            for d, score in zip(docs[0].tolist(), scores[0].tolist(), strict=True)
            if score > 0 and (lang is None or self.langs[d] == lang)
        ]
        return ranked[:k]


@dataclass
class IndexCache:
    index: Bm25Index | None = None
    fingerprint: tuple[int, int] | None = None
    checked_at: float = -math.inf
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_cache = IndexCache()


async def bm25_index(pool: Pool) -> Bm25Index | None:
    """The in-memory BM25 index; None while the knowledge base is empty."""
    cache = _cache
    async with cache.lock:
        now = time.monotonic()
        if cache.fingerprint is not None and now - cache.checked_at < REFRESH_SECONDS:
            return cache.index
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) AS n, coalesce(max(id), 0) AS last_id FROM chunks"
            )
            row = await cur.fetchone()
            fingerprint = (int(row["n"]), int(row["last_id"])) if row else (0, 0)
            if fingerprint != cache.fingerprint:
                cur = await conn.execute(
                    "SELECT c.id, c.lang, d.title, c.section, c.content FROM chunks c"
                    " JOIN documents d ON d.id = c.document_id ORDER BY c.id"
                )
                rows = [
                    (r["id"], r["lang"], passage(r["title"], r["section"], r["content"]))
                    for r in await cur.fetchall()
                ]
                # Decouple the build from the caller: a timed-out request must not scrap a
                # minutes-long rebuild, or the next caller will restart it (finding 7).
                if rows:
                    task = asyncio.create_task(asyncio.to_thread(Bm25Index, rows))

                    def _store(
                        t: asyncio.Task[Bm25Index], fp: tuple[int, int] = fingerprint
                    ) -> None:
                        if not t.cancelled() and t.exception() is None:
                            cache.index, cache.fingerprint = t.result(), fp

                    task.add_done_callback(_store)
                    cache.index = await asyncio.shield(task)
                else:
                    cache.index = None
                cache.fingerprint = fingerprint
        cache.checked_at = now
        return cache.index


async def dense_hits(
    pool: Pool, query: str, k: int, lang: str | None = None
) -> list[tuple[int, float]]:
    """(chunk id, cosine similarity), most similar first."""
    vector = await get_embeddings().aembed_query(query)
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, 1 - (embedding <=> %(vector)s::vector) AS score FROM chunks"
            " WHERE (%(lang)s::text IS NULL OR lang = %(lang)s)"
            " ORDER BY embedding <=> %(vector)s::vector LIMIT %(k)s",
            {"lang": lang, "vector": str([float(x) for x in vector]), "k": k},
        )
        return [(r["id"], float(r["score"])) for r in await cur.fetchall()]


async def dense_search(pool: Pool, query: str, k: int, lang: str | None = None) -> list[int]:
    return [chunk_id for chunk_id, _ in await dense_hits(pool, query, k, lang)]


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: score(d) = Σ 1 / (k + rank of d in each list), best first."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


class Reranker(Protocol):
    def rerank(self, query: str, passages: list[str]) -> list[tuple[int, float]]:
        """(passage index, relevance 0..1), best first."""
        ...


def _flashrank_dir() -> Path:
    cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    return cache.parent / "flashrank"


class FlashRankReranker:
    """Multilingual cross-encoder (~150 MB, CPU). Download runs ONCE in `warm_reranker` (job or
    lifespan): a search that arrives before the model is ready fails fast instead of parking a
    thread on the download lock. The model lives in the `models-cache` volume (constitution XI)."""

    def __init__(self) -> None:
        self._ranker: Any = None
        self._lock = threading.Lock()

    def rerank(self, query: str, passages: list[str]) -> list[tuple[int, float]]:
        if self._ranker is None:
            if not self._lock.acquire(blocking=False):
                raise RuntimeError("reranker is warming up; try again shortly")
            try:
                self._ranker = Ranker(model_name=RERANK_MODEL, cache_dir=str(_flashrank_dir()))
            finally:
                self._lock.release()
        request = RerankRequest(
            query=query, passages=[{"id": i, "text": p} for i, p in enumerate(passages)]
        )
        return [(int(r["id"]), float(r["score"])) for r in self._ranker.rerank(request)]


_reranker: Reranker | None = None


def set_reranker(reranker: Reranker | None) -> None:
    """Tests install a fake here (ADR 0006); None restores FlashRank."""
    global _reranker
    _reranker = reranker


class _SkippedReranker:
    """Com SKIP_RERANKER=1, retriever.search pega esta excecao e vai direto para o
    fallback RRF. Economiza ~500MB de modelo + numpy em maquinas apertadas."""

    def rerank(self, query: str, passages: list[str]) -> list[tuple[int, float]]:
        raise RuntimeError("rerank disabled via SKIP_RERANKER")


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        if os.environ.get("SKIP_RERANKER", "").lower() in ("1", "true", "yes"):
            _reranker = _SkippedReranker()
        else:
            _reranker = FlashRankReranker()
    return _reranker


def warm_reranker() -> None:
    """Load the model synchronously into the shared reranker. On failure a half-extracted model
    directory is removed so the next warm-up does not reuse a corrupted cache. Call this from the
    ingest job or the API lifespan so no request waits on the download."""
    import shutil

    global _reranker
    reranker = _reranker if isinstance(_reranker, FlashRankReranker) else FlashRankReranker()
    try:
        reranker._ranker = Ranker(model_name=RERANK_MODEL, cache_dir=str(_flashrank_dir()))
    except Exception:
        model_dir = _flashrank_dir() / RERANK_MODEL
        if model_dir.exists():
            shutil.rmtree(model_dir, ignore_errors=True)
        raise
    _reranker = reranker


class KbHit(KnowledgeHit):
    """KnowledgeHit plus the collection date of its page, so a KB source can show its date."""

    fetched_at: datetime


def dense_relevance(cosine: float, gate: float, strong: float, at_gate: float) -> float:
    """Cosine similarity on the 0..1 relevance scale the agent's confidence uses.

    The agent's confidence is min(model self-assessment, best passage score). A raw cosine of a
    good match sits around 0.55-0.75 (text-embedding-3-small), so used as-is it would cap every
    answer below `confidence_replan` and send correct replies to replan/escalate. Passing the
    calibrated gate is what proves the passage is relevant, so a passage at the gate scores
    `at_gate` (the replan threshold: retrieval is not the limiting factor) and one at `strong`
    or above scores 1.0, linear in between. The model's own confidence still decides."""
    if strong <= gate:
        return 1.0
    fraction = min(max((cosine - gate) / (strong - gate), 0.0), 1.0)
    return at_gate + (1.0 - at_gate) * fraction


async def _search_dense(pool: Pool, query: str, lang: str | None) -> list[KbHit]:
    """Dense strategy: the best passage of each of the top-K distinct pages, by cosine
    similarity at or above RAG_DENSE_THRESHOLD. CANDIDATES chunks are fetched and collapsed
    per page, so K slots cover K pages (the unit `evals/retrieval_compare.py` measures) instead
    of K chunks of one page. A query with no passage above the threshold returns nothing, so
    the agent says it found nothing instead of answering from weak context."""
    settings = get_settings()
    threshold = settings.rag_dense_threshold
    candidates = [h for h in await dense_hits(pool, query, CANDIDATES, lang) if h[1] >= threshold]
    if not candidates:
        return []
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT c.id, c.section, c.content, d.title, d.url, d.fetched_at FROM chunks c"
            " JOIN documents d ON d.id = c.document_id WHERE c.id = ANY(%s)",
            ([chunk_id for chunk_id, _ in candidates],),
        )
        by_id = {r["id"]: r for r in await cur.fetchall()}
    seen: set[str] = set()
    scored: list[tuple[int, float]] = []
    for chunk_id, score in candidates:  # most similar first: the first chunk of a page is its best
        row = by_id.get(chunk_id)
        if row is None or row["url"] in seen:
            continue
        seen.add(row["url"])
        scored.append((chunk_id, score))
        if len(scored) == TOP_K:
            break
    return [
        KbHit(
            chunk_id=chunk_id,
            title=by_id[chunk_id]["title"],
            url=by_id[chunk_id]["url"],
            section=by_id[chunk_id]["section"],
            content=by_id[chunk_id]["content"],
            score=dense_relevance(
                score, threshold, settings.rag_dense_strong, settings.confidence_replan
            ),
            fetched_at=by_id[chunk_id]["fetched_at"],
        )
        for chunk_id, score in scored
    ]


async def search(query: str, lang: str | None = None) -> list[KbHit]:
    pool = get_pool()
    if get_settings().rag_strategy == "dense":
        return await _search_dense(pool, query, lang)
    index = await bm25_index(pool)
    lexical = index.search(query, CANDIDATES, lang) if index else []
    dense = await dense_search(pool, query, CANDIDATES, lang)
    fused = [doc for doc, _ in rrf([lexical, dense])][:RERANK_POOL]
    if not fused:
        return []
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT c.id, c.section, c.content, d.title, d.url, d.fetched_at FROM chunks c"
            " JOIN documents d ON d.id = c.document_id WHERE c.id = ANY(%s)",
            (fused,),
        )
        by_id = {r["id"]: r for r in await cur.fetchall()}
    rows = [by_id[i] for i in fused if i in by_id]  # a chunk may vanish after a re-ingestion
    # Rerank com degradação: se o cross-encoder cair ou estourar tempo, devolve top-K da
    # ordem RRF com score 0.6 (abaixo do confidence_replan, para o supervisor decidir
    # replan/escalate em vez de sintetizar resposta sem sinal real).
    try:
        scored = await asyncio.wait_for(
            asyncio.to_thread(
                get_reranker().rerank,
                query,
                [passage(r["title"], r["section"], r["content"]) for r in rows],
            ),
            timeout=4.0,
        )
        threshold = get_settings().rag_relevance_threshold
        hits = [
            KbHit(
                chunk_id=rows[i]["id"],
                title=rows[i]["title"],
                url=rows[i]["url"],
                section=rows[i]["section"],
                content=rows[i]["content"],
                score=min(max(score, 0.0), 1.0),
                fetched_at=rows[i]["fetched_at"],
            )
            for i, score in scored
            if score >= threshold
        ]
        return sorted(hits, key=lambda h: h.score, reverse=True)[:TOP_K]
    except (TimeoutError, Exception):  # noqa: BLE001 — degradação proposital
        return [
            KbHit(
                chunk_id=r["id"],
                title=r["title"],
                url=r["url"],
                section=r["section"],
                content=r["content"],
                score=0.6,
                fetched_at=r["fetched_at"],
            )
            for r in rows[:TOP_K]
        ]
