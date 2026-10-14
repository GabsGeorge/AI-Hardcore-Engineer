"""Out-of-scope requests get a polite refusal with the supported topics (T116, REQ-GR-03).

The input guardrail classifies "write me a poem" as ``out_of_scope`` and the graph flows into
``safe_response``, whose reply names the topics the system does cover.
"""

import httpx
import pytest

from tests.fakes import FakeLLM

pytestmark = pytest.mark.req("REQ-GR-03")


async def test_out_of_scope_refusal_with_supported_topics(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(
        input_guard=[
            {"classification": "out_of_scope", "reason": "creative writing is not supported"},
        ],
    )
    resp = await client.post(
        "/v1/chat",
        json={"message": "Escreva um poema sobre o mar e a lua."},
        headers=auth_headers["cliente1988"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["guardrails"]["input"] == "blocked"
    assert body["route"] == ["input_guardrail", "safe_response"]
    # Supported topics appear in the SAFE text (synthesize.SAFE["pt"]).
    answer = body["response"].lower()
    assert "getnet" in answer
    assert "maquininhas" in answer
    assert "pix" in answer


async def test_out_of_scope_in_english_also_refuses(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    fake_llm.script(
        input_guard=[{"classification": "out_of_scope", "reason": "poem"}],
    )
    resp = await client.post(
        "/v1/chat",
        json={"message": "Please write a short poem about the sea."},
        headers=auth_headers["cliente1988"],
    )
    body = resp.json()
    assert body["guardrails"]["input"] == "blocked"
    answer = body["response"].lower()
    assert "getnet" in answer
    assert "card machines" in answer or "payment link" in answer
