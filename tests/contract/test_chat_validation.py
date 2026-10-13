import httpx
import pytest

from tests.fakes import FakeLLM, SpyGraph

pytestmark = pytest.mark.req("REQ-API-03")


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": "   \n\t "},
        {"message": "x" * 4001},
        {"message": "olá", "extra": "field"},
        {"message": "olá", "conversation_id": "not-a-uuid"},
        {"message": "olá", "user_id": "u" * 65},
        {},
    ],
    ids=["empty", "whitespace", "too-long", "extra-field", "bad-uuid", "long-user-id", "missing"],
)
async def test_invalid_payload_returns_typed_422_without_llm(
    client: httpx.AsyncClient,
    spy_graph: SpyGraph,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
    body: dict[str, object],
) -> None:
    resp = await client.post("/v1/chat", json=body, headers=auth_headers["cliente1988"])
    assert resp.status_code == 422
    payload = resp.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["trace_id"]
    assert "x" * 50 not in resp.text  # never echoes the input back
    assert spy_graph.calls == 0
    assert fake_llm.calls == []


async def test_message_of_exactly_4000_chars_is_accepted(
    client: httpx.AsyncClient, spy_graph: SpyGraph, auth_headers: dict[str, dict[str, str]]
) -> None:
    resp = await client.post(
        "/v1/chat", json={"message": "a" * 4000}, headers=auth_headers["cliente1988"]
    )
    assert resp.status_code == 200
