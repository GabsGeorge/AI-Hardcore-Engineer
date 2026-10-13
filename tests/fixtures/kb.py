"""Knowledge-base rows for retrieval tests, embedded with the deterministic fake embeddings."""

from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig

from app.agents.knowledge import knowledge_node
from app.db.pool import Pool
from app.graph.state import SpecialistInput
from app.rag import retriever
from app.rag.chunking import passage
from tests.fakes import FakeReranker, fake_embeddings

SMART_URL = "https://site.getnet.com.br/maquininhas/"
ADVANCE_EN_URL = "https://site.getnet.com.br/en/receivables-advance/"

MAQUININHAS = [
    (
        "Maquininhas Getnet > Get Smart",
        "A Get Smart é a maquininha inteligente com Android, tela touch, Wi-Fi e chip 4G.",
    ),
    (
        "Maquininhas Getnet > Get Clássica",
        "A Get Clássica é a maquininha tradicional com teclado físico e conexão por chip.",
    ),
    (
        "Maquininhas Getnet > Dúvidas frequentes",
        "O código de recusa 51 indica saldo insuficiente no cartão do comprador.",
    ),
]
ADVANCE_EN = [
    (
        "Receivables Advance > How it works",
        "Receivables advance lets merchants receive card sales early for an advance fee .",
    ),
]


async def add_document(
    pool: Pool, url: str, title: str, lang: str, sections: list[tuple[str, str]]
) -> list[int]:
    emb = fake_embeddings()
    async with pool.connection() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO documents (url, title, lang, source_type, content_hash, fetched_at)"
                " VALUES (%s, %s, %s, 'page', md5(%s), '2026-10-01T12:00:00Z') RETURNING id",
                (url, title, lang, url),
            )
        ).fetchone()
        assert row is not None
        ids = []
        for ord_, (section, content) in enumerate(sections):
            vector = emb.embed_query(passage(title, section, content))
            chunk = await (
                await conn.execute(
                    "INSERT INTO chunks (document_id, ord, section, content, lang, embedding)"
                    " VALUES (%s, %s, %s, %s, %s, %s::vector) RETURNING id",
                    (row["id"], ord_, section, content, lang, str([float(x) for x in vector])),
                )
            ).fetchone()
            assert chunk is not None
            ids.append(chunk["id"])
    return ids


async def seed_kb(pool: Pool) -> None:
    await add_document(pool, SMART_URL, "Maquininhas Getnet", "pt", MAQUININHAS)
    await add_document(pool, ADVANCE_EN_URL, "Receivables Advance", "en", ADVANCE_EN)


@pytest.fixture
def fresh_retriever(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fake reranker and an empty BM25 cache: tests truncate `chunks`, so ids restart."""
    monkeypatch.setattr(retriever, "_cache", retriever.IndexCache())
    retriever.set_reranker(FakeReranker())
    yield
    retriever.set_reranker(None)


async def run_knowledge(query: str, language: str = "pt") -> dict[str, Any]:
    """Runs the Knowledge node as the Supervisor's `Send` would, as merchant cliente1988."""
    config: RunnableConfig = {
        "configurable": {"user_id": "cliente1988", "user_role": "merchant", "trace_id": "0" * 32}
    }
    state: SpecialistInput = {
        "subtask": {"id": "s1", "agent": "knowledge", "query": query},
        "language": language,
    }
    return await knowledge_node(state, config)


def rewrite(*variants: tuple[str, str], general: bool = False) -> dict[str, Any]:
    """Scripted reply of the `knowledge_rewrite` role."""
    return {"variants": [{"query": q, "lang": lang} for q, lang in variants], "general": general}


def answer(text: str, confidence: float = 0.9, cited: tuple[int, ...] = (1,)) -> dict[str, Any]:
    """Scripted reply of the `knowledge` role."""
    return {"answer": text, "confidence": confidence, "cited": list(cited)}
