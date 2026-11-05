"""Sweep do limiar do reranker para encontrar o melhor recall@5 no conjunto rotulado.

    docker compose --profile eval run --rm --no-deps \
      -e SKIP_RERANKER=0 eval python evals/rerank_sweep.py
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
TOP_K = 5


def recall_at_k(predicted: list[str], relevant: list[str], k: int = 5) -> float:
    if not relevant:
        return 1.0
    top = set(predicted[:k])
    return sum(1 for r in relevant if r in top) / len(relevant)


def mrr(predicted: list[str], relevant: list[str]) -> float:
    rel = set(relevant)
    return next((1.0 / i for i, p in enumerate(predicted, start=1) if p in rel), 0.0)


def ndcg(predicted: list[str], relevant: list[str], k: int = 5) -> float:
    rel = set(relevant)
    dcg = sum(1.0 / math.log2(i + 2) for i, p in enumerate(predicted[:k]) if p in rel)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(rel), k)))
    return dcg / ideal if ideal else 0.0


def load_queries() -> list[dict[str, Any]]:
    data = yaml.safe_load((ROOT / "evals" / "retrieval_labeled.yaml").read_text(encoding="utf-8"))
    return list(data["queries"])


def _unique(urls: list[str]) -> list[str]:
    return list(dict.fromkeys(urls))


async def _urls_for(pool: Any, chunk_ids: list[int]) -> list[str]:
    async with pool.connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT c.id, d.url FROM chunks c JOIN documents d ON d.id = c.document_id"
                " WHERE c.id = ANY(%s)",
                (chunk_ids,),
            )
        ).fetchall()
    by_id = {r["id"]: r["url"] for r in rows}
    return _unique([by_id[i] for i in chunk_ids if i in by_id])


async def _run() -> dict[float, dict[str, float]]:
    from app.core.config import get_settings
    from app.db.pool import close_pool, open_pool
    from app.rag import retriever
    from app.rag.retriever import passage

    pool = await open_pool(get_settings().database_url)
    try:
        index = await retriever.bm25_index(pool)
        reranker = retriever.get_reranker()

        # Para cada query, pre-computa top-fused + scores do reranker uma unica vez
        cache: list[tuple[list[tuple[int, float]], list[str]]] = []
        for q in load_queries():
            text, rel = q["text"], q["relevant"]
            dense = await retriever.dense_search(pool, text, retriever.CANDIDATES)
            lexical = index.search(text, retriever.CANDIDATES, None) if index else []
            fused = [doc for doc, _ in retriever.rrf([lexical, dense])]

            # Carrega conteudo dos chunks fundidos
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT c.id, d.title, c.section, c.content, d.url"
                    " FROM chunks c JOIN documents d ON d.id = c.document_id"
                    " WHERE c.id = ANY(%s)",
                    (fused,),
                )
                by_id = {r["id"]: r for r in await cur.fetchall()}
            rows = [by_id[i] for i in fused if i in by_id]

            scored = reranker.rerank(
                text, [passage(r["title"], r["section"], r["content"]) for r in rows]
            )
            # scored = [(local_idx, score)], mapeia pra (chunk_id, score)
            id_scores = [(rows[i]["id"], s) for i, s in scored]
            cache.append((id_scores, rel))

        # Agora varre thresholds
        results: dict[float, dict[str, float]] = {}
        for thr in THRESHOLDS:
            all_metrics = []
            for id_scores, rel in cache:
                kept = [cid for cid, s in id_scores if s >= thr]
                top_ids = sorted(
                    [(cid, s) for cid, s in id_scores if cid in set(kept)],
                    key=lambda t: t[1],
                    reverse=True,
                )[:TOP_K]
                urls = await _urls_for(pool, [cid for cid, _ in top_ids])
                all_metrics.append((recall_at_k(urls, rel), mrr(urls, rel), ndcg(urls, rel)))
            results[thr] = {
                "recall@5": sum(m[0] for m in all_metrics) / len(all_metrics),
                "mrr": sum(m[1] for m in all_metrics) / len(all_metrics),
                "ndcg@5": sum(m[2] for m in all_metrics) / len(all_metrics),
            }
    finally:
        await close_pool()
    return results


def main() -> None:
    report = asyncio.run(_run())
    print(json.dumps(report, indent=2))
    best = max(report.items(), key=lambda kv: kv[1]["recall@5"])
    print(f"\nBEST threshold={best[0]:.2f}  recall@5={best[1]['recall@5']:.3f}")


if __name__ == "__main__":
    main()
