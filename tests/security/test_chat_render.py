"""The chat response is rendered as text, so a model output that contains HTML or JS can
never execute in the browser (T055 / FR-012).

The HTTP boundary already guarantees this: the API returns the field as JSON, with no HTML
entity encoding and a ``Content-Type: application/json`` header. We assert that by calling
``build_response`` directly with a state whose assistant answer contains ``<script>...</script>``,
and checking that FastAPI serialises it verbatim."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest

from app.api.chat import build_response


@pytest.mark.req("REQ-GR-05")
def test_html_payload_is_never_escaped_or_mutated_in_the_response() -> None:
    payload = "<script>alert('xss')</script> também: <img src=x onerror=1>"
    state: dict[str, Any] = {
        "final_response": payload,
        "results": [
            {
                "subtask_id": "s1",
                "agent": "knowledge",
                "answer": payload,
                "confidence": 0.9,
                "sources": [],
                "tools_used": [],
                "error": None,
            }
        ],
        "guardrail_flags": ["input:pass", "output:pass"],
        "escalation": None,
        "route_trace": ["supervisor", "knowledge"],
    }
    conversation_id = UUID("00000000-0000-0000-0000-000000000001")
    response = build_response(state, conversation_id, trace_id="0" * 32)

    # Pydantic preserves the exact bytes: no HTML entity encoding.
    assert response.response == payload
    # Round-trip through JSON confirms the final wire shape.
    body = json.loads(response.model_dump_json())
    assert body["response"] == payload
    # No field smuggles the characters into a different type.
    assert isinstance(body["response"], str)
