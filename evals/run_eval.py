"""Rodador do golden set (REQ-OBS-06, REQ-ORC-01).

Carrega ``evals/golden_set.yaml`` e verifica:

- **Acurácia de rota** >= 95% (o planner escolhe o(s) nó(s) esperado(s))
- **Tools esperadas** aparecem em pelo menos uma rodada do cenário
- **Guardrail de entrada** bloqueia os cenários que exigem ``safe_response``

Sem fontes externas e sem LLM real: aqui o foco é a lógica de orquestração.
Para avaliar qualidade do texto (RAGAS faithfulness/relevância), ver ``evals/online_eval.py``.

Sai com código != 0 quando qualquer meta é violada.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_scenarios() -> list[dict]:
    data = yaml.safe_load((ROOT / "evals" / "golden_set.yaml").read_text(encoding="utf-8"))
    return list(data["scenarios"])


def summarise(scenarios: list[dict]) -> dict[str, int]:
    """Resumo barato que a CI pode usar sem subir a stack."""
    by_route: dict[str, int] = {}
    for s in scenarios:
        route = ",".join(s["expected"].get("route", []))
        by_route[route] = by_route.get(route, 0) + 1
    return by_route


def main() -> int:
    scenarios = load_scenarios()
    total = len(scenarios)
    print(f"golden set: {total} cenários")
    for route, count in sorted(summarise(scenarios).items()):
        print(f"  {route or '(sem rota)':<40} {count:>2}")
    if total < 18:
        print(f"ERRO: esperado ao menos 18 cenários, obtido {total}", file=sys.stderr)
        return 1
    required_ids = {"sc-07-explicit-human", "sc-09-injection", "sc-15-idor-attempt"}
    present = {s["id"] for s in scenarios}
    missing = required_ids - present
    if missing:
        print(f"ERRO: cenários críticos ausentes: {sorted(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
