"""LLM-as-judge offline sobre o golden set (REQ-OBS-04 — versão batch).

Reutiliza a maquinaria do juiz online (`src/app/ops/online_eval.py`) e aplica em cada
cenário do golden set, agregando faithfulness/relevance e emitindo matriz de confusão
rota-esperada × rota-real.

    docker compose --profile eval run --rm eval python evals/judge_batch.py

Saída: JSON em stdout + arquivo `/tmp/judge_report.json`. Cobra `faithfulness` e
`relevance` médios por tipo de cenário (knowledge, support, escalation, safe_response);
registra tokens e custo acumulado.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent


OPENAI_COSTS_PER_1K_TOKENS = {  # gpt-4o-mini, USD, outubro 2026
    "input": 0.00015,
    "output": 0.0006,
}


def load_scenarios() -> list[dict[str, Any]]:
    data = yaml.safe_load((ROOT / "evals" / "golden_set.yaml").read_text(encoding="utf-8"))
    return list(data["scenarios"])


def _format_sources(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "(no sources)"
    return "\n".join(f"- {s.get('url', '?')}: {s.get('snippet', '')[:200]}" for s in sources)


def _expected_route(expected: dict[str, Any]) -> str:
    route = expected.get("route", [])
    if route == ["safe_response"]:
        return "safe_response"
    if "escalation" in route:
        return "escalation"
    if "knowledge" in route:
        return "knowledge"
    if "support" in route:
        return "support"
    return "other"


def _observed_route(body: dict[str, Any]) -> str:
    route = body.get("route", [])
    if body.get("guardrails", {}).get("input") == "blocked":
        return "safe_response"
    if body.get("handoff", {}).get("status") == "awaiting_human":
        return "escalation"
    if "knowledge" in route:
        return "knowledge"
    if "support" in route:
        return "support"
    return "other"


async def _run() -> dict[str, Any]:
    from app.api.auth import create_token
    from app.ops.online_eval import _judge  # noqa: PLC2701 — reuso proposital

    base_url = os.environ.get("EVAL_BASE_URL", "http://api:8000")
    token = create_token(os.environ.get("EVAL_USER", "cliente1988"), "merchant")

    cm: dict[tuple[str, str], int] = defaultdict(int)
    scores_by_bucket: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"faithfulness": [], "relevance": []}
    )
    totals: dict[str, int] = defaultdict(int)

    async with httpx.AsyncClient(
        base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=60
    ) as client:
        for sc in load_scenarios():
            payload: dict[str, Any] = {"message": sc["message"]}
            if "context_message" in sc:
                boot = await client.post("/v1/chat", json={"message": sc["context_message"]})
                payload["conversation_id"] = boot.json()["conversation_id"]
            resp = await client.post("/v1/chat", json=payload)
            if resp.status_code == 429:
                await asyncio.sleep(int(resp.headers.get("Retry-After", "60")))
                resp = await client.post("/v1/chat", json=payload)
            body = resp.json()

            exp = _expected_route(sc["expected"])
            obs = _observed_route(body)
            cm[(exp, obs)] += 1
            totals["requests"] += 1
            # tokens: coleta best-effort (não é obrigatório na response pública)
            totals["tokens_in"] += int(body.get("usage", {}).get("prompt_tokens", 0))
            totals["tokens_out"] += int(body.get("usage", {}).get("completion_tokens", 0))

            # LLM-as-judge: só avalia caminhos de resposta (não safe_response/escalation)
            if obs in {"knowledge", "support", "other"} and body.get("response"):
                verdict = await _judge(
                    sc["message"], body["response"], _format_sources(body.get("sources", []))
                )
                if verdict:
                    bucket = scores_by_bucket[exp]
                    bucket["faithfulness"].append(verdict.faithfulness)
                    bucket["relevance"].append(verdict.relevance)

    cost_usd = (
        totals["tokens_in"] / 1000 * OPENAI_COSTS_PER_1K_TOKENS["input"]
        + totals["tokens_out"] / 1000 * OPENAI_COSTS_PER_1K_TOKENS["output"]
    )

    return {
        "confusion_matrix": {f"{e}->{o}": n for (e, o), n in sorted(cm.items())},
        "faithfulness_mean_by_bucket": {
            b: round(sum(v["faithfulness"]) / len(v["faithfulness"]), 3)
            for b, v in scores_by_bucket.items()
            if v["faithfulness"]
        },
        "relevance_mean_by_bucket": {
            b: round(sum(v["relevance"]) / len(v["relevance"]), 3)
            for b, v in scores_by_bucket.items()
            if v["relevance"]
        },
        "totals": {
            "requests": totals["requests"],
            "tokens_in": totals["tokens_in"],
            "tokens_out": totals["tokens_out"],
            "cost_usd": round(cost_usd, 4),
        },
    }


def main() -> int:
    report = asyncio.run(_run())
    out = Path(tempfile.gettempdir()) / "judge_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
