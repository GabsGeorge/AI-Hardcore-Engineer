"""Contrato do OpenAPI auto-gerado (REQ-API-02).

- O schema está publicado em ``/openapi.json`` com rotas e componentes esperados.
- Fuzz leve com payloads malformados: nenhuma rota pode responder 500 — erro interno é
  defeito; esperamos 4xx (401/403/404/422).
"""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.req("REQ-API-02")
async def test_openapi_schema_is_fetchable(client: httpx.AsyncClient) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["openapi"].startswith("3.")
    paths = schema.get("paths", {})
    for required in ("/v1/chat", "/v1/handoffs", "/v1/conversations/{conversation_id}"):
        assert required in paths, f"rota {required} ausente do OpenAPI"


_MALFORMED_PAYLOADS: list[dict] = [
    {},  # faltam campos obrigatórios
    {"message": None},
    {"message": "oi", "user_id": 123},  # tipo errado
    {"message": "oi", "conversation_id": "not-a-uuid"},
    {"message": "x" * 50_000},  # muito grande
    {"message": "oi", "extra_field": "oops"},  # extra forbid
]


@pytest.mark.req("REQ-API-02")
@pytest.mark.parametrize("payload", _MALFORMED_PAYLOADS, ids=lambda p: str(sorted(p.items()))[:40])
async def test_malformed_payloads_never_return_500(
    client: httpx.AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    payload: dict,
) -> None:
    """Payloads malformados devolvem 4xx bem definidos — nunca 500."""
    resp = await client.post("/v1/chat", json=payload, headers=auth_headers["cliente1988"])
    assert resp.status_code < 500, f"{payload=} → {resp.status_code}: {resp.text[:200]}"
    assert resp.status_code in (400, 403, 404, 422)


@pytest.mark.req("REQ-API-02")
async def test_unauth_requests_never_return_500(client: httpx.AsyncClient) -> None:
    """Qualquer rota protegida respondida sem token: 401 ou 404, nunca 500."""
    for method, path, body in (
        ("POST", "/v1/chat", {"message": "oi"}),
        ("GET", "/v1/handoffs", None),
        ("GET", "/v1/conversations/00000000-0000-0000-0000-000000000001", None),
        ("POST", "/v1/feedback", {"trace_id": "0" * 32, "rating": 1}),
    ):
        resp = await client.request(method, path, json=body)
        assert resp.status_code < 500, f"{method} {path} → {resp.status_code}"
        assert resp.status_code in (401, 403, 404, 422)
