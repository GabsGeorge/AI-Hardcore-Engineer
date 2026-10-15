"""Dense vs hybrid (BM25+dense+RRF) vs hybrid+rerank on evals/retrieval_labeled.yaml
(REQ-RAG-04). Needs an ingested index and a real embeddings key. Exits 1 when the shipped
strategy (hybrid+rerank) has recall@5 < 0.90.

    docker compose --profile eval run --rm eval python evals/retrieval_compare.py
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
TARGET_RECALL = 0.90


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
    return list(dict.fromkeys(urls))  # several chunks of one page count once, in rank order


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


async def _run() -> dict[str, dict[str, float]]:
    from app.core.config import get_settings
    from app.db.pool import close_pool, open_pool
    from app.rag import retriever

    pool = await open_pool(get_settings().database_url)
    try:
        index = await retriever.bm25_index(pool)
        scores: dict[str, list[tuple[float, float, float]]] = {
            "dense": [],
            "hybrid": [],
            "hybrid+rerank": [],
        }
        for q in load_queries():
            text, rel = q["text"], q["relevant"]
            dense = await retriever.dense_search(pool, text, retriever.CANDIDATES)
            lexical = index.search(text, retriever.CANDIDATES, None) if index else []
            fused = [doc for doc, _ in retriever.rrf([lexical, dense])]
            reranked = _unique([h.url for h in await retriever.search(text)])
            for name, urls in (
                ("dense", await _urls_for(pool, dense)),
                ("hybrid", await _urls_for(pool, fused)),
                ("hybrid+rerank", reranked),
            ):
                scores[name].append((recall_at_k(urls, rel), mrr(urls, rel), ndcg(urls, rel)))
    finally:
        await close_pool()
    return {
        name: {
            "recall@5": sum(s[0] for s in rows) / len(rows),
            "mrr": sum(s[1] for s in rows) / len(rows),
            "ndcg@5": sum(s[2] for s in rows) / len(rows),
        }
        for name, rows in scores.items()
    }


def main() -> int:
    report = asyncio.run(_run())
    print(json.dumps(report, indent=2))
    recall = report["hybrid+rerank"]["recall@5"]
    if recall < TARGET_RECALL:
        print(f"FAIL: hybrid+rerank recall@5 {recall:.2f} < {TARGET_RECALL}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
