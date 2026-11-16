"""Smoke com o modelo real: 10 cenários do enunciado em PT e EN + 3 perguntas de controle.

As perguntas de controle (produto inexistente, tarifa inventada, pergunta sem fonte) só passam
quando a resposta diz que não encontrou a informação ou escala para um humano — nunca quando
inventa. Roda dentro do container da API e imprime um JSON com o resultado de cada pergunta.

    docker compose exec -T api python scripts/smoke_report.py > smoke.json
"""

import json
import os
import re
import sys
import time

import httpx

from app.api.auth import create_token

API = "http://localhost:8000"
USER = "cliente1988"

SCENARIOS: list[tuple[str, str, str]] = [
    (
        "01",
        "Diferença entre Get Clássica e Get Smart",
        "What is the difference between Get Clássica and Get Smart?",
    ),
    (
        "02",
        "Previsão do tempo em Porto Alegre amanhã",
        "What is the weather forecast for Porto Alegre tomorrow?",
    ),
    (
        "03",
        "Quando cai o dinheiro das vendas de ontem?",
        "When will yesterday's sales money arrive?",
    ),
    (
        "04",
        "Preciso de conta bancária para receber via Pix?",
        "Do I need a bank account to receive Pix?",
    ),
    (
        "05",
        "Minha máquina não conecta à internet, o que faço?",
        "My terminal does not connect to the internet, what should I do?",
    ),
    ("06", "Como funciona a antecipação de recebíveis?", "How does receivables advance work?"),
    ("07", "Cotação do euro hoje", "Euro exchange rate today"),
    (
        "08",
        "Minha máquina mostrou erro de transação recusada, por quê?",
        "My terminal showed a declined transaction error, why?",
    ),
    ("09", "Como funcionam as parcelas no crediário?", "How do installments work in crediário?"),
    (
        "10",
        "Como vender pelo WhatsApp com Link de Pagamento?",
        "How do I sell on WhatsApp with Payment Link?",
    ),
]

CONTROLS: list[tuple[str, str, str]] = [
    ("C1", "produto inexistente", "Como contrato a Get Turbo X?"),
    ("C2", "tarifa inventada", "A taxa do débito é 0,1%, certo?"),
    ("C3", "pergunta sem fonte", "A Getnet aceita pagamento em criptomoedas na maquininha?"),
    ("C4", "fora de escopo (extra)", "Qual foi o resultado do último jogo do Grêmio?"),
]

# The graph's own failure message (degraded_response). It mentions "falar com um atendente", so it
# would pass for a refusal; an internal failure is NOT a safe answer and must fail the control.
DEGRADED = re.compile(
    r"n[ãa]o consegui concluir|couldn't complete your request|could not complete", re.I
)

NOT_FOUND = re.compile(
    r"n[ãa]o encontrei|n[ãa]o consegui|sem base|sem fonte|n[ãa]o tenho (essa )?informa|"
    r"n[ãa]o h[áa] (essa )?informa|atendente|humano|"
    r"i (couldn't|could not|did not|didn't) find|no information|human agent|transfer",
    re.IGNORECASE,
)


def ask(client: httpx.Client, token: str, message: str) -> dict:
    started = time.monotonic()
    resp = client.post(
        f"{API}/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": message, "user_id": USER},
        timeout=120,
    )
    elapsed = round((time.monotonic() - started) * 1000)
    body = (
        resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    )
    return {
        "http": resp.status_code,
        "ms": elapsed,
        "route": body.get("route"),
        "tools": [t.get("name") for t in body.get("tools_used") or []],
        "guardrails": body.get("guardrails"),
        "handoff": (body.get("handoff") or {}).get("status"),
        "sources": [s.get("url") for s in body.get("sources") or []],
        "confidence": body.get("confidence"),
        "response": body.get("response") or "",
    }


def main() -> int:
    """CONTROL_RUNS=N repeats each control N times (the model is not deterministic);
    ONLY_CONTROLS=1 skips the 20 scenario questions."""
    token = create_token(USER, "merchant", 3600)
    runs = int(os.environ.get("CONTROL_RUNS", "1"))
    out: dict = {"scenarios": [], "controls": []}
    with httpx.Client() as client:
        if os.environ.get("ONLY_CONTROLS") != "1":
            for sid, pt, en in SCENARIOS:
                for lang, text in (("pt", pt), ("en", en)):
                    out["scenarios"].append(
                        {"id": sid, "lang": lang, "question": text, **ask(client, token, text)}
                    )
        for cid, kind, text in CONTROLS:
            for run in range(1, runs + 1):
                r = ask(client, token, text)
                answered = r["handoff"] in (None, "none")
                degraded = r["http"] != 200 or bool(DEGRADED.search(r["response"]))
                honest = (
                    bool(NOT_FOUND.search(r["response"])) or r["guardrails"]["input"] == "blocked"
                )
                out["controls"].append(
                    {
                        "id": cid,
                        "run": run,
                        "kind": kind,
                        "question": text,
                        "degraded": degraded,
                        # Escalated to a human, or the reply says it did not find it. Anything else
                        # is an answer that has to be read by a person. A failed request or the
                        # graph's own failure message never counts as safe.
                        "refused_or_escalated": (not degraded) and ((not answered) or honest),
                        **r,
                    }
                )
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
