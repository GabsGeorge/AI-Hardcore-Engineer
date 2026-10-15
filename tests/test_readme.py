"""O README traz as seções exigidas pelo enunciado (REQ-INF-06).

Lemos o markdown e checamos que os cabeçalhos esperados estão presentes. O conteúdo mais
granular (comandos exatos de `docker compose`, por exemplo) é verificado via regex sobre
blocos de código.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

README = Path(__file__).resolve().parent.parent / "README.md"


@pytest.mark.req("REQ-INF-06")
def test_readme_exists_and_is_non_empty() -> None:
    assert README.exists(), "README.md ausente na raiz"
    assert len(README.read_text(encoding="utf-8")) > 1000


@pytest.mark.req("REQ-INF-06")
def test_readme_has_required_sections() -> None:
    text = README.read_text(encoding="utf-8")
    required = (
        "Como executar",  # build/configuração/execução
        "Como testar",  # testes
        "Arquitetura",  # arquitetura
        "pipeline RAG",  # pipeline RAG (case-insensitive)
        "Guardrails",  # guardrails
        "Segurança",  # segurança
        "HITL",  # HITL
        "Como este projeto foi construído",  # fluxo Spec Kit (T172)
        "Como avaliar",  # curls prontos (T173)
    )
    missing = [name for name in required if name.lower() not in text.lower()]
    assert not missing, f"seções faltando no README: {missing}"


@pytest.mark.req("REQ-INF-06")
def test_readme_mentions_docker_compose_commands() -> None:
    text = README.read_text(encoding="utf-8")
    assert "docker compose up -d --build" in text, "falta o comando de subida da stack"
    assert "docker compose -f docker-compose.yml -f docker-compose.test.yml" in text, (
        "falta o comando canônico da suíte de testes"
    )


@pytest.mark.req("REQ-INF-06")
def test_readme_links_to_specs_and_adrs() -> None:
    text = README.read_text(encoding="utf-8")
    assert re.search(r"specs/001-multi-agent-support", text), "falta link para a spec"
    assert re.search(r"docs/adr/", text), "falta link para os ADRs"
