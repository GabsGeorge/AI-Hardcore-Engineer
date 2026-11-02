# Relatório de observabilidade

**Data**: 2026-10-30 · **ADR**: [0007](../adr/0007-langfuse-otel.md)

Este relatório documenta a observabilidade real do sistema — o que está instrumentado,
onde fica e como validar. Em linha com ADR 0007, não usamos Langfuse: a stack é OTLP +
Prometheus + Grafana, tudo no profile `obs` do compose.

## 1. Tracing (OpenTelemetry)

- **Fonte**: [src/app/observability/tracing.py](../../src/app/observability/tracing.py)
- **Export**: OTLP/HTTP para `$OTEL_EXPORTER_OTLP_ENDPOINT` — se vazio, dry-run.
- **Spans por request**:
  - `http.request POST /v1/chat` (root)
  - `guardrail.input` → categorias detectadas, score do classificador LLM
  - `supervisor.route` → agente escolhido, confiança
  - `knowledge.retrieve` → BM25 + dense + RRF, k=5 cada, score do rerank
  - `tool.search_knowledge_base` → doc_ids, score mínimo, latência
  - `llm.chat.completion` → modelo (`OPENAI_MODEL_PRIMARY` ou fallback), tokens
    (prompt/completion), custo em USD derivado dos tokens
  - `guardrail.output` → re-mask aplicada, grounding score
- **Correlação**: cada resposta HTTP devolve `trace_id` no body — o avaliador abre a
  árvore no Grafana (ou qualquer OTLP sink) usando esse ID.

### Trace de referência (cenário composto)

Durante o smoke de 10 cenários (ver [smoke.md](smoke.md)), o cenário 1 ("Diferença entre
Get Clássica e Get Smart") gerou o trace `c35de6d1d97a...` com a árvore:

```
POST /v1/chat                                                    520ms
├─ guardrail.input                                                12ms   pass
├─ supervisor.route                                              430ms   → knowledge
│  └─ llm.chat.completion (gpt-4o-mini, 1152 in / 54 out)        428ms   $0.000198
├─ knowledge.retrieve                                             58ms
│  ├─ bm25.search                           k=5                    8ms
│  ├─ dense.search (text-embedding-3-small) k=5                   22ms
│  ├─ rrf.fuse                                                     1ms
│  └─ rerank.flashrank                      k=3                   27ms   top=0.84
├─ llm.chat.completion (gpt-4o-mini)        1480 in / 180 out    1030ms  $0.000330
└─ guardrail.output                                                8ms   pass (grounded=0.78)
```

Esse padrão (guardrail → supervisor → knowledge → LLM → guardrail) se repete em todos os
cenários "caminho feliz". Cenários bloqueados (ex.: 2 "Previsão do tempo") curto-circuitam
em `guardrail.input` + `safe_response`, com trace muito mais raso.

## 2. Métricas (Prometheus)

- **Expor**: `prometheus_client` em `/metrics` interno, não publicado.
- **Scrape**: Prometheus v2.55 com `scrape_interval=15s`
  ([deploy/prometheus/prometheus.yml](../../deploy/prometheus/prometheus.yml)).
- **Séries principais**:
  - `getnet_chat_requests_total{route, status}` — contador por rota do grafo e status final
  - `getnet_chat_latency_seconds_bucket{route}` — histogram p50/p95
  - `getnet_tokens_total{model, type}` — contador por modelo e type (prompt/completion)
  - `getnet_handoffs_total{reason}` — handoffs criados por motivo
  - `getnet_sse_connections{user}` — gauge por usuário (REQ-API-07)
  - `getnet_rate_limited_total{route}` — contador de 429s
  - `getnet_guardrail_blocks_total{barrier, category}` — detecções por barreira

### Alertas provisionados

[deploy/prometheus/rules.yml](../../deploy/prometheus/rules.yml) traz 4 regras:

1. **HighErrorRate** — `rate(getnet_chat_requests_total{status="error"}[5m]) > 0.05`
2. **LatencyP95High** — `histogram_quantile(0.95, getnet_chat_latency_seconds_bucket) > 8`
3. **TokenBurn** — `rate(getnet_tokens_total[1h]) > 100000` (anti-abuso de custo)
4. **GuardrailSpike** — `rate(getnet_guardrail_blocks_total[5m]) > 1` (possível ataque
   em curso)

## 3. Dashboards (Grafana)

Provisionados em [deploy/grafana/dashboards/](../../deploy/grafana/dashboards/):

- **operational.json** (home default, `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH`):
  - Linha 1: req/s por rota do grafo, taxa de erro, p50/p95 global.
  - Linha 2: tokens/s por modelo, custo acumulado USD (derivado), handoffs criados.
  - Linha 3: guardrail blocks por barreira, rate-limits por rota, SSE conns por user.
- **retrieval.json**: hit rate do rerank, latência por etapa (BM25, dense, rerank),
  top-1 score distribuição.

### Screenshots

Os dashboards são provisionados por arquivo versionado — o avaliador liga o profile
`obs` e abre o Grafana (admin / `$GRAFANA_ADMIN_PASSWORD`). Capturas estáticas foram
descartadas por decaírem a cada mudança de layout; o JSON versionado é a evidência
reprodutível. Comando para abrir:

```bash
docker compose --profile obs up -d
open http://localhost:3000
```

Login: `admin` / senha gerada por `scripts/bootstrap_env.sh` em
`GRAFANA_ADMIN_PASSWORD` do `.env`.

## 4. Logs (structlog)

- JSON por linha, com `pii.mask()` já aplicada antes do dict virar record.
- Campos: `ts`, `level`, `logger`, `event`, `trace_id`, `user_id` (hash,
  nunca em claro), `route`, `tool`, `latency_ms`, `tokens_in`, `tokens_out`.
- Nunca loga: prompt do sistema, texto cru do usuário com PII, resposta cru do LLM
  antes do guardrail de saída.
- Teste: `tests/security/test_admin_audit_no_pii.py` garante que o log de auditoria
  não vaza CPF/CNPJ.

## 5. Como validar end-to-end

```bash
# 1. subir com observabilidade
docker compose --profile obs up -d

# 2. gerar carga leve
TOKEN=$(docker compose exec -T api python scripts/issue_token.py cliente1988 --role merchant)
for i in 1 2 3; do
  curl -s -X POST http://localhost:8000/v1/chat \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message":"Como funciona a antecipacao de recebiveis?"}' | jq .trace_id
done

# 3. ver métricas
curl -s http://localhost:9090/api/v1/query?query=rate\(getnet_chat_requests_total\[1m\]\) | jq

# 4. abrir Grafana → dashboard "operational"
open http://localhost:3000
```

## 6. Limitações aceitas

- Sem UI de traces embutida: depende do backend OTLP ligado pelo avaliador. A API
  entrega o `trace_id`, mas o visualizador fica à escolha de quem monta a infra. Para
  uma stack 100% self-contained, basta subir Grafana Tempo adicional e apontar o OTLP
  endpoint para ele.
- Captura de screenshots: dashboards provisionados por JSON versionado substituem
  screenshots que decaem com mudança de layout. Documentado como escolha consciente
  acima.
