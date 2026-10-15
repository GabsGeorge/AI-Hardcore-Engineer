"""Registro de métricas Prometheus (REQ-OBS-03).

Expõe contadores e histogramas que descrevem o comportamento operacional da plataforma:

- ``getnet_http_requests_total`` por rota, método e status
- ``getnet_http_request_duration_seconds`` histograma por rota
- ``getnet_route_total`` contador do caminho tomado pelo supervisor
- ``getnet_tokens_total`` tokens consumidos por papel
- ``getnet_tool_errors_total`` erros nas tools, por nome
- ``getnet_guardrail_blocks_total`` bloqueios por estágio (input/output) e tipo
- ``getnet_handoffs_total`` aberturas de handoff por reason

Qualquer código que precisa gravar métrica importa daqui — nunca cria o Counter/Histogram
de novo (evitamos duplicatas e erros de registro).
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "getnet_http_requests_total",
    "Requisições HTTP totais por rota, método e status.",
    labelnames=("route", "method", "status"),
)

HTTP_LATENCY = Histogram(
    "getnet_http_request_duration_seconds",
    "Latência das rotas da API.",
    labelnames=("route",),
    buckets=(0.1, 0.3, 0.6, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 20.0),
)

ROUTE_TAKEN = Counter(
    "getnet_route_total",
    "Vezes que o supervisor foi para cada nó.",
    labelnames=("node",),
)

TOKENS = Counter(
    "getnet_tokens_total",
    "Tokens consumidos pelo LLM por papel do grafo.",
    labelnames=("role",),
)

TOOL_ERRORS = Counter(
    "getnet_tool_errors_total",
    "Erros nas chamadas de tool.",
    labelnames=("tool",),
)

GUARDRAIL_BLOCKS = Counter(
    "getnet_guardrail_blocks_total",
    "Bloqueios/reescritas dos guardrails.",
    labelnames=("stage", "kind"),
)

HANDOFFS = Counter(
    "getnet_handoffs_total",
    "Handoffs abertos por razão.",
    labelnames=("reason",),
)
