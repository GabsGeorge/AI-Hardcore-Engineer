"""Rate limit por janela fixa de 60 s (REQ-SEC-08).

A 31ª requisição no mesmo minuto deve retornar 429 com Retry-After.
"""

from __future__ import annotations

import httpx
import pytest

from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401


@pytest.mark.req("REQ-SEC-08")
@pytest.mark.usefixtures("fresh_retriever")
async def test_rate_limit_429(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    """A 31ª chamada do mesmo lojista no minuto corrente leva 429 + Retry-After."""
    fake_llm.script(
        supervisor=[make_plan("knowledge") for _ in range(40)],
        knowledge_rewrite=[rewrite() for _ in range(40)],
    )
    headers = auth_headers["cliente2024"]  # user "limpo" para não interferir em outros testes
    # 30 permitidas
    for i in range(30):
        resp = await client.post("/v1/chat", json={"message": f"q{i}"}, headers=headers)
        assert resp.status_code == 200, f"iteração {i} caiu para {resp.status_code}"
    # 31ª bloqueia
    blocked = await client.post("/v1/chat", json={"message": "q31"}, headers=headers)
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after")
    assert blocked.json()["error"]["code"] == "rate_limited"
