# Implementation Plan: Getnet Multi-Agent Support System

**Branch**: `001-multi-agent-support` | **Date**: 2026-10-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-multi-agent-support/spec.md`

## Summary

API FastAPI que recebe mensagens de lojistas Getnet e as processa num grafo LangGraph: guardrail de
entrada → Supervisor em ciclo (planejador LLM + política determinística) → especialistas Knowledge
(RAG híbrido + DuckDuckGo), Support (5 tools sobre dados mock) e Escalation (`interrupt()` +
retomada pelo operador) → síntese → guardrail de saída. Identidade só do JWT, injetada em
`config["configurable"]` e nunca visível ao LLM. Postgres 16 + pgvector guarda vetores,
checkpoints, tickets, auditoria e mock; Redis faz rate limit, idempotência e cache. OpenAI (GPT)
com fallback. Testes determinísticos com LLM fake numa rede sem saída; qualidade medida por
avaliação com modelo real. Observabilidade (OTel → Langfuse, Prometheus, Grafana) atrás do profile
`obs`. Decisões em [research.md](./research.md) e [docs/adr/](../../docs/adr/).

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI, Pydantic v2 + pydantic-settings, Uvicorn, LangGraph,
langgraph-checkpoint-postgres, langchain-core, langchain-openai, ddgs, psycopg 3 (+ psycopg-pool),
pgvector, redis-py (async), PyJWT, tenacity, bm25s, FlashRank, httpx, trafilatura, pypdf, structlog,
opentelemetry-sdk + exporter OTLP + instrumentation-openai-v2, prometheus-client, sse-starlette (P2)

**Storage**: PostgreSQL 16 + pgvector (dados, vetores, checkpoints); índice BM25 em memória na API
(`bm25s`, montado a partir de `chunks`); Redis 7 (efêmero)

**Testing**: pytest, pytest-asyncio, pytest-cov, schemathesis, LLM/embeddings/reranker fakes;
avaliação com RAGAS + scripts próprios; k6 (carga). Ferramentas de qualidade: ruff, mypy (strict
em `src/`), gitleaks, Trivy

**Target Platform**: Containers Linux (Docker Compose); desenvolvimento em Windows/macOS/Linux

**Project Type**: Web service (API); frontend fica na feature 002

**Performance Goals**: p95 ≤ 8 s (simples) e ≤ 15 s (compostas/replanejamento) com 20 usuários
simultâneos; mensagem final ≤ 5 s após resposta do operador

**Constraints**: 6 passos e 20.000 tokens por execução; 4.000 caracteres por mensagem; 30 req/min
por usuário; timeouts LLM 20 s / web 5 s / tools 2 s; suíte de testes sem rede externa; container
sem root; nenhum artefato gerado no repositório ou na imagem

**Scale/Scope**: Desafio técnico: dezenas de usuários simultâneos, milhares de trechos na base,
seed com 3 lojistas e 1 operador; 65 requisitos (28 P0, 25 P1, 12 P2)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Princípio | Como o plano atende | Pré | Pós |
| --- | --- | --- | --- | --- |
| I | Identidade só do servidor | `sub` do JWT; divergência → 403 sem agentes; `user_id` em `config`, tools com `RunnableConfig` injetado; `thread_id` prefixado (ADR 0005) | ✅ | ✅ |
| II | Nenhum segredo | `.env.example` apenas; gitleaks pre-commit + CI; segredos via pydantic-settings | ✅ | ✅ |
| III | Resposta factual com fonte | `sources` obrigatório no Knowledge; limiar 0,30; grounding na saída | ✅ | ✅ |
| IV | Menor privilégio | Allowlist por agente ([tools.md](./contracts/tools.md)); `open_dispute` só após `approve`; contexto em `<untrusted_context>` | ✅ | ✅ |
| V | Requisito com teste | `@pytest.mark.req` + `scripts/check_traceability.py` na CI | ✅ | ✅ |
| VI | Determinismo | LLM, embeddings e reranker fakes; rede `internal: true` (ADR 0006) | ✅ | ✅ |
| VII | Observável | `trace_id` em toda resposta e log; spans OTel por nó/tool/LLM; máscara de PII no structlog | ✅ | ✅ |
| VIII | Falha segura | Timeouts, tenacity, breaker, fallback de modelo, `max_steps`, orçamento → `degraded_response`/escalonamento | ✅ | ✅ |
| IX | Um comando | `make up` / `docker compose up`; `make test` no container; observabilidade em `--profile obs` | ✅ | ✅ |
| X | LGPD | Máscara antes do LLM e dos sinks; retenção por tipo; `DELETE /v1/me/data`; auditoria pseudonimizada | ✅ | ✅ |
| XI | Sem artefatos gerados | `.gitignore`/`.dockerignore`; modelo do reranker em volume; índice e seed recriados por comando; checagem na CI | ✅ | ✅ |
| XII | Simplicidade (Ponytail) | psycopg + SQL sem ORM; breaker próprio de ~30 linhas; tarefa periódica no lifespan; sem fila/worker; ver Complexity Tracking | ✅ | ✅ |
| XIII | Excelência de interface | Fora desta feature; a 002 consome este contrato e segue Impeccable + Playwright | N/A | N/A |

**Stack (seção da constitution)**: Python 3.12, FastAPI, LangGraph, OpenAI (GPT) com fallback,
DuckDuckGo com cache/timeout/breaker, Postgres + pgvector, Redis, resposta no idioma do usuário,
container multi-stage sem root, threat model OWASP LLM ([threat-model.md](./threat-model.md)). ✅

**Resultado**: sem violações. Os itens de maior custo estão justificados em Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-multi-agent-support/
├── spec.md              # /speckit-specify + /speckit-clarify
├── plan.md              # este arquivo
├── research.md          # decisões R-01..R-21
├── data-model.md        # tabelas, estado do grafo, transições, retenção
├── threat-model.md      # OWASP LLM Top 10 + riscos de API
├── quickstart.md        # guia de validação ponta a ponta
├── contracts/
│   ├── openapi.yaml     # contrato HTTP
│   ├── tools.md         # tools e allowlists dos agentes
│   └── events.md        # eventos SSE (P2)
├── checklists/
│   ├── requirements.md
│   └── block-review.md  # checklists do revisor de fim de bloco (segurança + orquestração)
└── tasks.md             # /speckit-tasks (ainda não criado)

docs/
├── adr/0001..0010-*.md  # decisões arquiteturais
└── architecture.drawio  # diagramas (arquitetura, grafo, RAG)
```

### Source Code (repository root)

```text
src/app/
├── main.py                  # FastAPI app, lifespan (pool, grafo, tarefa periódica)
├── api/
│   ├── auth.py              # JWT, papéis, checagem de user_id divergente
│   ├── deps.py              # dependências (usuário atual, pool, redis)
│   ├── schemas.py           # modelos do openapi.yaml
│   ├── chat.py              # /v1/chat, /v1/chat/stream
│   ├── conversations.py     # /v1/conversations/{id}[/events]
│   ├── handoffs.py          # /v1/handoffs, /reply
│   ├── me.py                # /v1/me/data, /v1/feedback
│   ├── health.py            # /healthz, /readyz
│   └── limits.py            # rate limit + idempotência (Redis)
├── graph/
│   ├── state.py             # AgentState, Plan, AgentResult
│   ├── builder.py           # montagem do StateGraph + checkpointer
│   ├── supervisor.py        # planejador LLM + política determinística
│   ├── synthesize.py        # síntese, degraded_response, safe_response
│   └── memory.py            # nó summarize (stub no grafo base; corpo na US7)
├── agents/
│   ├── common.py            # execução com allowlist, montagem de AgentResult
│   ├── knowledge.py         # stub no grafo base; corpo na US1
│   ├── support.py           # stub no grafo base; corpo na US2
│   └── escalation.py        # stub no grafo base; corpo na US5
├── tools/
│   ├── interfaces.py        # CONGELADO: modelos de entrada/saída das 9 tools + allowlists
│   ├── support_tools.py     # 5 tools (user_id via RunnableConfig)
│   ├── knowledge_tools.py   # search_knowledge_base, web_search
│   └── escalation_tools.py  # create_ticket, request_action_approval
├── guardrails/
│   ├── pii.py               # regex + Luhn + dígitos verificadores
│   ├── input.py
│   └── output.py
├── rag/
│   ├── sources.yaml         # allowlist de domínios + URLs semente
│   ├── crawler.py           # sitemap, robots.txt, HTML/PDF
│   ├── chunking.py
│   ├── ingest.py            # CLI do job de ingestão (idempotente)
│   └── retriever.py         # multi-query, BM25 (bm25s em memória) + densa, RRF, rerank
├── db/
│   ├── pool.py
│   ├── migrate.py           # runner de migrações .sql
│   ├── migrations/0001_init.sql ...
│   ├── seed.sql             # dados mock determinísticos
│   ├── repo.py              # consultas SQL parametrizadas (usuários, conversas, auditoria, handoffs)
│   └── support_repo.py      # consultas do Support (recebíveis, terminais, transações, recusa, perfil)
├── ops/
│   └── scheduler.py         # SLA, expiração, expurgo (advisory lock)
├── observability/
│   ├── logging.py           # structlog + máscara de PII
│   ├── tracing.py           # OTel
│   └── metrics.py           # prometheus_client
└── core/
    ├── config.py            # pydantic-settings
    ├── errors.py            # erros tipados → Error do contrato
    ├── llm.py               # get_model(role) com fallback; ponto de injeção do fake
    └── resilience.py        # retry (tenacity) + circuit breaker

prompts/                     # supervisor.md, knowledge.md, support.md, escalation.md,
                             # input_guard.md, grounding.md, synthesize.md, summarize.md
scripts/
├── issue_token.py
└── check_traceability.py
tests/
├── conftest.py              # app, tokens, fake_llm, banco limpo por teste
├── fakes.py                 # FakeChatModel roteirizado, embeddings e reranker fakes
├── unit/                    # pii, guardrails, chunking, rrf, política do supervisor, tools
├── contract/                # schemathesis + schema de resposta
├── integration/             # grafo: rotas, paralelo, replanejamento, limites, interrupt/resume, memória
├── security/                # idor, injeção direta/indireta, pii, rate limit, papéis
└── fixtures/                # HTML/PDF pequenos para ingestão offline
evals/
├── golden_set.yaml          # 10 cenários PT/EN + extras + estendido (≥ 50)
├── retrieval_labeled.yaml
├── run_eval.py              # rota, tools, RAGAS
└── retrieval_compare.py     # densa vs híbrida vs híbrida + rerank
deploy/
├── prometheus/ (prometheus.yml, alerts.yml)
├── grafana/ (provisioning/, dashboards/)
└── k6/chat.js
Dockerfile                   # multi-stage, uv, USER app, HEALTHCHECK
docker-compose.yml           # api, postgres, redis, ingest; profiles obs, load, eval
docker-compose.test.yml      # serviços tests e lint numa rede internal: true (sem Python nem make no host)
Makefile
pyproject.toml / uv.lock
.env.example / .gitignore / .dockerignore / .gitattributes (eol=lf) / .pre-commit-config.yaml (gitleaks-docker)
.github/workflows/ci.yml     # lint, types, test, traceability, gitleaks, trivy, build, eval
README.md
```

**Structure Decision**: Projeto único de backend em `src/app`, organizado por responsabilidade
(api, grafo, agentes, tools, guardrails, rag, db, ops, observabilidade). O frontend (chat e
console do operador) entra como `web/` na feature 002, consumindo [openapi.yaml](./contracts/openapi.yaml).

## Fluxo de uma mensagem

1. `POST /v1/chat` → valida JWT (401), compara `user_id` (403 + auditoria), valida corpo (422),
   rate limit (429), idempotência (409/replay).
2. Resolve ou cria `conversation_id` do dono (404 se de outro usuário).
3. `graph.ainvoke` com `thread_id = "{user}:{conversation}"` e `user_id` em `configurable`.
4. `input_guardrail`: máscara de PII → heurísticas → classificador. Bloqueio → `safe_response`.
5. `supervisor`: `Plan` estruturado; `Send` para cada subtarefa (em paralelo).
6. Especialistas devolvem `AgentResult`; política decide: sintetizar, replanejar (< 0,70),
   escalar (2× < 0,70, 1× < 0,40, pedido humano, tema sensível, 3 falhas, ação com efeito) ou
   degradar (6 passos / 20k tokens).
7. `escalation` → ticket + `interrupt()` → resposta `awaiting_human`. Retomada via operador.
8. `synthesize` (no idioma do usuário) → `output_guardrail` → resposta com `trace_id`.

## Entrega por prioridade

| Fatia | Histórias | Requisitos | Critério de pronto |
| --- | --- | --- | --- |
| **P0 · core (≤ 60 min de tela)** | US1, US2, US3 | 28 P0 | `docker compose up` + golden set básico respondendo; IDOR 403; PII mascarada; README mínimo |
| **P1 · diferenciais** | US4, US5, US6, US7 | 25 P1 | Grafo com replanejamento, HITL com retomada, guardrails completos, memória, testes com LLM fake, golden set com gate |
| **P2 · plataforma** | US8, US9 | 12 P2 | Langfuse/Prometheus/Grafana, avaliação online, fallback, breaker, LGPD, CI completa, k6 |

Dentro do P0, a ordem é a do caminho crítico da demo: esqueleto + config + compose → auth →
grafo base com contratos congelados → US2, US1 e US3 em paralelo → README. Na US1 o retriever pode
começar só com a perna densa; **BM25 + RRF + rerank são obrigatórios na entrega final**.

No core, REQ-ORC-01 é verificado de forma estrutural (o `Plan` é válido e roteia); a meta de
acurácia de rota ≥ 95% é medida com modelo real na avaliação da Fase 3.

## Modo de execução (agentes)

1. **Fase 0 + grafo base**: um único agente, em sequência, na branch `001-multi-agent-support`.
   Ao final, ficam **congelados** `src/app/graph/state.py`, `src/app/api/schemas.py` e
   `src/app/tools/interfaces.py`, além do registro de nós em `src/app/graph/builder.py`.
2. **Blocos paralelos**: no máximo 3 subagentes, um por user story, cada um em sua worktree
   (`001-usN`). Um subagente só edita os arquivos das suas tasks; se precisar mudar um contrato
   congelado, para e devolve o pedido ao agente principal.
3. **Fim de cada bloco**: integrar as branches, rodar a suíte completa via `docker compose`,
   commitar por task (`feat(T049): descrição [REQ-...]`) e acionar **um revisor somente leitura**
   no diff integrado com os dois checklists de
   [checklists/block-review.md](./checklists/block-review.md): segurança (identidade/IDOR, PII,
   segredos, injeção) e orquestração (rotas, término e `max_steps`, allowlist por agente, uso do
   estado). O próximo bloco só começa com o revisor sem achados bloqueantes. Esse revisor cumpre a
   revisão obrigatória de orquestração e de segurança da constitution.

## Responsáveis (equipe de agentes)

| Papel | Módulos | Revisão obrigatória |
| --- | --- | --- |
| PO | `tasks.md`, aceite por requisito, README | — |
| Especialista em orquestração | `graph/`, `agents/`, `prompts/`, `core/llm.py` | Toda mudança em `graph/` e `agents/` (checklist de orquestração do revisor de bloco) |
| Backend/agents | `api/`, `tools/`, `rag/`, `db/`, `ops/`, `core/` | — |
| QA | `tests/`, `evals/`, `deploy/k6`, `scripts/check_traceability.py` | Cobertura e rastreabilidade |
| Segurança | `api/auth.py`, `api/limits.py`, `guardrails/`, `tools/`, threat model, CI de scans | Toda mudança em auth, tools, guardrails e PII (checklist de segurança do revisor de bloco) |
| Frontend/design system | `web/` (feature 002) | — |

## Complexity Tracking

> Sem violações da constitution. Itens de custo maior, com justificativa (princípio XII):

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
| --- | --- | --- |
| Supervisor em ciclo (vs router) | REQ-ORC-02/03 | Router de uma passada não replaneja nem decompõe |
| Reranker cross-encoder (~150 MB) | REQ-RAG-04; precisão do top-5 | Sem rerank o recall@5 ≥ 0,90 fica em risco; modelos maiores são inviáveis em CPU |
| Índice BM25 em memória (`bm25s`), uma cópia por réplica | BM25 obrigatório na entrega final | FTS do Postgres não é BM25; ParadeDB troca a imagem do banco (fica como caminho de produção, ADR 0003) |
| Stack de observabilidade (Langfuse v3, Prometheus, Grafana) | REQ-OBS-02/03; bônus do desafio | Só logs não permitem trace por agente nem alertas; fica atrás do profile `obs` |
| Tarefa periódica no lifespan | REQ-HITL-05, REQ-SEC-09 | Worker/scheduler externo adiciona containers sem ganho |
| Circuit breaker próprio | REQ-REL-03 com async | Bibliotecas disponíveis são síncronas |
