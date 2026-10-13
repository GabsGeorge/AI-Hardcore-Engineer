import httpx
import pytest

from app.api.auth import create_token
from tests.fakes import SpyGraph

pytestmark = pytest.mark.req("REQ-SEC-01")

BODY = {"message": "Quando cai o dinheiro das vendas de ontem?"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Basic Y2xpZW50ZTE5ODg6eA=="},
        {"Authorization": f"Bearer {create_token('ghost-user', 'merchant')}"},
        {"Authorization": f"Bearer {create_token('cliente1988', 'operator')}"},
    ],
    ids=["missing", "malformed", "wrong-scheme", "unknown-sub", "role-mismatch"],
)
async def test_unauthenticated_requests_get_401_without_running_agents(
    client: httpx.AsyncClient, spy_graph: SpyGraph, headers: dict[str, str]
) -> None:
    resp = await client.post("/v1/chat", json=BODY, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
    assert resp.json()["trace_id"]
    assert spy_graph.calls == 0
