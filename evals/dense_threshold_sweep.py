"""Calibra RAG_RELEVANCE_THRESHOLD para a estratégia densa (ADR 0003).

Para cada limiar mede, nas perguntas rotuladas, recall@5 / MRR / nDCG@5 só com passagens
acima dele, e nas perguntas sem fonte (retrieval_oos.yaml) quantas ainda trazem alguma passagem
(vazamento). O limiar ideal mantém o recall e zera o vazamento.

    docker compose --profile eval run --rm eval python evals/dense_threshold_sweep.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_compare import mrr, ndcg, recall_at_k  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS = [round(0.25 + 0.025 * i, 3) for i in range(0, 23)]  # 0.25 … 0.80
TOP_K = 5


def _load(name: str) -> list[dict[str, Any]]:
    data = yaml.safe_load((ROOT / "evals" / name).read_text(encoding="utf-8"))
    return list(data["queries"])


async def _scored_urls(pool: Any, query: str) -> list[tuple[str, float]]:
    from app.rag import retriever

    """(page url, best similarity) of the pages the product would consider: CANDIDATES chunks
    collapsed per page, most similar first (same unit as retriever._search_dense)."""
    hits = await retriever.dense_hits(pool, query, retriever.CANDIDATES)
    async with pool.connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT c.id, d.url FROM chunks c JOIN documents d ON d.id = c.document_id"
                " WHERE c.id = ANY(%s)",
                ([chunk_id for chunk_id, _ in hits],),
            )
        ).fetchall()
    url_of = {r["id"]: r["url"] for r in rows}
    best: dict[str, float] = {}
    for chunk_id, score in hits:
        url = url_of.get(chunk_id)
        if url is not None and url not in best:
            best[url] = score
    return list(best.items())


async def _run() -> dict[str, Any]:
    from app.core.config import get_settings
    from app.db.pool import close_pool, open_pool

    pool = await open_pool(get_settings().database_url)
    try:
        labeled = [
            (q, await _scored_urls(pool, q["text"])) for q in _load("retrieval_labeled.yaml")
        ]
        oos = [(q, await _scored_urls(pool, q["text"])) for q in _load("retrieval_oos.yaml")]
    finally:
        await close_pool()

    rows = []
    for t in THRESHOLDS:
        metrics = []
        for q, scored in labeled:
            urls = [u for u, s in scored if s >= t][:TOP_K]
            metrics.append(
                (
                    recall_at_k(urls, q["relevant"]),
                    mrr(urls, q["relevant"]),
                    ndcg(urls, q["relevant"]),
                )
            )
        leaked = sum(1 for _, scored in oos if any(s >= t for _, s in scored))
        rows.append(
            {
                "threshold": t,
                "recall@5": round(sum(m[0] for m in metrics) / len(metrics), 3),
                "mrr": round(sum(m[1] for m in metrics) / len(metrics), 3),
                "ndcg@5": round(sum(m[2] for m in metrics) / len(metrics), 3),
                "oos_leak": f"{leaked}/{len(oos)}",
            }
        )
    return {
        "top1_labeled_min": round(min(s[0][1] for _, s in labeled if s), 3),
        "top1_oos_max": round(max(s[0][1] for _, s in oos if s), 3),
        "oos_top1": {q["id"]: round(s[0][1], 3) for q, s in oos if s},
        "sweep": rows,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(_run()), indent=2, ensure_ascii=False))
