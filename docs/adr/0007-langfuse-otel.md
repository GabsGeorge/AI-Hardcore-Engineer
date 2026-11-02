# ADR 0007: OpenTelemetry + Prometheus + Grafana (sem Langfuse)

- **Status**: Aceito · **Data**: 2026-10-13 · **Revisado**: 2026-10-30 · **Requisitos**: REQ-OBS-01..04

## Contexto

Precisamos de três coisas de observabilidade: (1) tracing por agente para explicar
"o que o grafo decidiu", (2) métricas para alertas (latência, custo, taxa de erro), (3)
nada que mande dados do cliente para fora do ambiente. Traces podem conter conteúdo
mascarado, mas ainda sensível.

## Decisão

Observabilidade **sem dependência de SaaS**, com três componentes locais:

1. **Tracing**: spans OpenTelemetry (convenções GenAI) emitidos por guardrail, nó,
   tool, retrieval e chamada de LLM. Exportação OTLP/HTTP via
   `OTEL_EXPORTER_OTLP_ENDPOINT` — se a variável não estiver setada, o tracer provider
   fica em dry-run (sem exportar). Fonte: [src/app/observability/tracing.py](../../src/app/observability/tracing.py).
2. **Métricas**: `prometheus_client` expõe `/metrics` em porta interna; Prometheus v2.55
   coleta com `scrape_interval=15s`. Dashboards Grafana provisionados em
   [deploy/grafana/dashboards/](../../deploy/grafana/dashboards/) (dashboard
   operacional como home default).
3. **Logs**: `structlog` em JSON com `pii.mask()` aplicado antes de qualquer sink —
   `trace_id` carregado no record para cruzar com os spans.

A stack `prometheus + grafana + collector OTLP` fica **inteira no profile `obs`** do
compose: `docker compose --profile obs up -d`. Sem o profile, a API sobe sozinha e o
exporter OTLP vira no-op — perfeito para o avaliador que só quer testar o fluxo
funcional.

### Por que não Langfuse

A versão anterior deste ADR previa Langfuse v3 self-hosted. Durante a implementação,
avaliamos o custo real: Langfuse v3 exige ClickHouse + Redis separado + MinIO/S3 +
pelo menos 3 containers do próprio Langfuse (web, worker, server), ou seja, 6 containers
extras só para ler traces. OpenTelemetry puro + Grafana Tempo (ou mesmo os próprios
spans serializados em arquivo via `ConsoleSpanExporter` em dev) resolve o mesmo
problema com um décimo da superfície. Mantivemos OTLP padrão para que, se um dia
quisermos plugar Langfuse (ou qualquer outro backend), seja só mudar o endpoint — o
código não acopla.

## Alternativas consideradas

- **Langfuse SaaS**: dados saem do ambiente. Rejeitado por LGPD.
- **Langfuse self-hosted**: 6 containers extras para o mesmo valor que OTEL + Grafana
  dão com 2. Rejeitado por custo operacional desproporcional.
- **Callback nativo do Langfuse SDK** no código Python: acopla o código ao
  fornecedor; a troca por outro backend viraria um refactor. Rejeitado.
- **Datadog APM**: SaaS pago, dados saem. Rejeitado.
- **Só logs estruturados, sem tracing**: funciona para erros, mas não explica roteamento
  entre agentes. Rejeitado.

## Consequências

- (+) Zero dependências de SaaS; dados ficam locais.
- (+) `trace_id` da resposta HTTP abre a árvore completa no backend OTLP que o avaliador
  escolher.
- (+) Dashboards Grafana versionados no repo (`deploy/grafana/provisioning/`), reprodutíveis.
- (+) Profile `obs` permite rodar a stack mínima sem observabilidade — mais rápido para
  avaliar o fluxo funcional.
- (−) Correlação visual entre spans e métricas exige o Grafana aberto + um backend de
  traces (Tempo, Jaeger, qualquer OTLP sink). O avaliador que não ligar o profile `obs`
  perde o visual, mas o `trace_id` e os logs JSON ainda bastam para auditar.
- (−) Sem UI de traces nativa — depende do backend configurado via OTLP endpoint.

## Como validar

```bash
# subir com observabilidade
docker compose --profile obs up -d

# ver que o /metrics está sendo scraped
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[].labels.job'

# abrir Grafana (admin / $GRAFANA_ADMIN_PASSWORD do .env)
open http://localhost:3000

# gerar tráfego e pegar o trace_id da resposta
curl -s -X POST http://localhost:8000/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"Diferença entre Clássica e Smart"}' | jq .trace_id
```

Evidência estruturada em [docs/reports/observability.md](../reports/observability.md).
