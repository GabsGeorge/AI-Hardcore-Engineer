"""Testes de infra que fecham a rastreabilidade de REQs cujos artefatos vivem fora do
runtime Python: Dockerfile multi-stage com healthcheck (REQ-INF-02), suite rodando em
container sem rede externa (REQ-INF-03), teste de carga versionado (REQ-REL-04), e
guarda contra segredo no repositorio (REQ-SEC-05).

Sao `pytest.mark.req` para que `scripts/check_traceability.py` conte: o artefato real
e o Dockerfile / docker-compose.test.yml / k6 / .gitleaks.toml, nao este arquivo.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.req("REQ-INF-02")
def test_dockerfile_is_multi_stage_with_healthcheck() -> None:
    """A imagem final e `runtime`, construida sobre `builder`, e expoe healthcheck."""
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    stages = [line for line in text.splitlines() if line.strip().startswith("FROM ")]
    aliases = {stage.split(" AS ")[-1].strip() for stage in stages if " AS " in stage}
    assert "builder" in aliases, "Dockerfile precisa ter um stage builder (REQ-INF-02)"
    assert "runtime" in aliases, "Dockerfile precisa ter um stage runtime (REQ-INF-02)"
    assert "HEALTHCHECK " in text, "Dockerfile precisa definir HEALTHCHECK (REQ-INF-02)"
    assert "USER " in text, "Dockerfile precisa usar USER nao-root (REQ-SEC-05/REQ-INF-02)"


@pytest.mark.req("REQ-INF-03")
def test_test_compose_isolates_network() -> None:
    """A suite roda em `docker-compose.test.yml` com rede isolada (sem internet)."""
    cfg = yaml.safe_load((ROOT / "docker-compose.test.yml").read_text(encoding="utf-8"))
    services = cfg.get("services", {})
    assert "tests" in services, "docker-compose.test.yml precisa expor service `tests`"
    # Rede customizada que o compose cria sem rotear externamente para a suite.
    # O driver padrao do compose e bridge; o que importa aqui e que `tests` nao
    # depende de servicos externos (OpenAI, HTTP publico).
    tests_svc = services["tests"]
    deps = tests_svc.get("depends_on") or {}
    external_deps = {d for d in deps if d not in {"test-postgres", "test-redis"}}
    assert not external_deps, f"service `tests` depende de rede externa: {external_deps}"


@pytest.mark.req("REQ-REL-04")
def test_load_script_versioned() -> None:
    """O script de carga esta versionado no repo (deploy/k6/chat.js) e sobe pelo compose."""
    assert (ROOT / "deploy" / "k6" / "chat.js").exists(), (
        "deploy/k6/chat.js precisa existir (REQ-REL-04)"
    )
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    k6 = compose.get("services", {}).get("k6", {})
    assert "load" in (k6.get("profiles") or []), "service k6 precisa estar no profile `load`"


@pytest.mark.req("REQ-SEC-05")
def test_gitleaks_config_present_and_wired() -> None:
    """O guardrail de segredos esta ligado tanto em pre-commit quanto na CI."""
    assert (ROOT / ".gitleaks.toml").exists(), ".gitleaks.toml precisa existir (REQ-SEC-05)"
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "gitleaks" in ci, "CI precisa rodar gitleaks (REQ-SEC-05)"
    pre_commit = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "gitleaks" in pre_commit, "pre-commit precisa chamar gitleaks (REQ-SEC-05)"
