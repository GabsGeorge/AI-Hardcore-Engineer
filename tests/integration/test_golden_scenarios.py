"""Suíte do golden set: executa um subconjunto dos cenários via API (REQ-ORC-01).

Para cada cenário cobremos o essencial: rota tomada, handoff aberto quando esperado e
guardrail bloqueando quando o cenário é fora de escopo/injeção.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from tests.fakes import FakeLLM, make_plan
from tests.fixtures.kb import fresh_retriever, rewrite  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent.parent


def _scenarios() -> list[dict[str, Any]]:
    data = yaml.safe_load((ROOT / "evals" / "golden_set.yaml").read_text(encoding="utf-8"))
    return list(data["scenarios"])


@pytest.mark.req("REQ-ORC-01", "REQ-OBS-06")
def test_golden_set_meets_minimum_coverage() -> None:
    scenarios = _scenarios()
    assert len(scenarios) >= 21
    languages = {s["language"] for s in scenarios}
    assert "pt" in languages and "en" in languages
    assert any("credi" in s["message"].lower() for s in scenarios), (
        "golden set deve cobrir crediário (produto BR relevante do catálogo)"
    )


_SAMPLE_IDS = {
    "sc-01-knowledge-antecipacao": ("knowledge", "Como funciona a antecipação de recebíveis?"),
    "sc-07-explicit-human": ("escalation", "Quero falar com um atendente humano agora."),
    "sc-10-out-of-scope": ("safe_response", "Escreva um poema sobre o pôr do sol."),
}


@pytest.mark.req("REQ-ORC-01")
@pytest.mark.usefixtures("fresh_retriever")
@pytest.mark.parametrize("scenario_id", list(_SAMPLE_IDS.keys()))
async def test_golden_route_matches_expected(
    client: httpx.AsyncClient,
    fake_llm: FakeLLM,
    auth_headers: dict[str, dict[str, str]],
    scenario_id: str,
) -> None:
    expected_node, message = _SAMPLE_IDS[scenario_id]
    if expected_node == "knowledge":
        fake_llm.script(supervisor=[make_plan("knowledge")], knowledge_rewrite=[rewrite()])
    elif expected_node == "escalation":
        fake_llm.script(
            supervisor=[make_plan("escalation", query="humano")],
            escalation=["Lojista pede atendente."],
        )
    elif expected_node == "safe_response":
        # Pedido fora de escopo (poema) passa pelas heurísticas; o classificador LLM é quem decide.
        fake_llm.script(input_guard=[{"classification": "out_of_scope"}])

    resp = await client.post(
        "/v1/chat", json={"message": message}, headers=auth_headers["cliente1988"]
    )
    assert resp.status_code == 200
    body = resp.json()
    if expected_node == "safe_response":
        assert body["guardrails"]["input"] == "blocked"
    elif expected_node == "escalation":
        assert body["handoff"]["status"] == "awaiting_human"
    else:
        assert expected_node in body["route"]
