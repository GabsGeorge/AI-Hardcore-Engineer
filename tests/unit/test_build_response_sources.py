"""When the output guard replaces the reply (blocked as ungrounded, or a promise rewritten), the
API must not list the consulted pages as its sources: the new text does not rest on them."""

from uuid import uuid4

import pytest

from app.api.chat import build_response

pytestmark = pytest.mark.req("REQ-API-01")

SOURCE = {"title": "Get Tap", "url": "https://site.getnet.com.br/get-tap/", "kind": "kb"}


def _state(output_flag: str) -> dict:
    return {
        "final_response": "texto",
        "results": [{"agent": "knowledge", "error": None, "confidence": 0.8, "sources": [SOURCE]}],
        "guardrail_flags": ["input:pass", output_flag],
        "route_trace": [],
    }


@pytest.mark.parametrize("flag", ["output:blocked", "output:rewritten"])
def test_replaced_reply_carries_no_sources(flag: str) -> None:
    assert build_response(_state(flag), uuid4(), "0" * 32).sources == []


def test_passed_reply_keeps_its_sources() -> None:
    body = build_response(_state("output:pass"), uuid4(), "0" * 32)
    assert [s.url for s in body.sources] == [SOURCE["url"]]
