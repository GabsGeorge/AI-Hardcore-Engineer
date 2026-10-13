# ADR 0007: Langfuse self-hosted + OpenTelemetry

- **Status**: Aceito · **Data**: 2026-10-13 · **Requisitos**: REQ-OBS-01..04

## Contexto

Precisamos de tracing por agente e de alertas. Traces podem conter conteúdo de clientes,
mesmo mascarado.

## Decisão

Spans OpenTelemetry (convenções GenAI) por guardrail, nó, tool, retrieval e chamada de LLM,
exportados via OTLP para o Langfuse v3 self-hosted. `structlog` JSON com máscara de PII. Métricas
com `prometheus_client`, Prometheus com regras de alerta e Grafana provisionado. Toda essa stack
fica no profile `obs` do compose.

## Alternativas

- **Langfuse/LangSmith SaaS**: menos containers, mas os dados saem do ambiente.
- **Callback nativo do Langfuse**: acopla o código ao fornecedor.

## Consequências

- (+) O `trace_id` da resposta abre a árvore completa; os dados ficam locais.
- (−) Vários containers extras (Langfuse v3 com ClickHouse, Redis e storage), por isso atrás de
  profile.
