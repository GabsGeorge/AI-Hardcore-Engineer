"""Prometheus metrics (REQ-OBS-03). Define each metric here once; call sites import it."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "getnet_http_requests_total", "HTTP requests.", labelnames=("route", "method", "status")
)
HTTP_LATENCY = Histogram(
    "getnet_http_request_duration_seconds",
    "API route latency.",
    labelnames=("route",),
    buckets=(0.1, 0.3, 0.6, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 20.0),
)
ROUTE_TAKEN = Counter("getnet_route_total", "Supervisor dispatches per node.", labelnames=("node",))
TOKENS = Counter("getnet_tokens_total", "LLM tokens per graph role.", labelnames=("role",))
TOOL_ERRORS = Counter("getnet_tool_errors_total", "Failed tool calls.", labelnames=("tool",))
GUARDRAIL_BLOCKS = Counter(
    "getnet_guardrail_blocks_total", "Guardrail blocks/rewrites.", labelnames=("stage", "kind")
)
HANDOFFS = Counter("getnet_handoffs_total", "Handoffs opened.", labelnames=("reason",))
AUTH_FAILURES = Counter("getnet_auth_failures_total", "Requests rejected with 401.")
