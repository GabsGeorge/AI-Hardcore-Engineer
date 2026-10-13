# Research: Getnet Multi-Agent Support System

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Date**: 2026-10-13

Cada decisão segue o formato Decision / Rationale / Alternatives. As decisões de maior impacto
também viram ADR em [docs/adr/](../../docs/adr/).

## R-01 Provedor de LLM

- **Decision**: API da OpenAI direta (não Azure), com modelos GPT: principal de tier "mini" e
  fallback de outro modelo GPT, ambos definidos por variável de ambiente (`OPENAI_MODEL_PRIMARY`,
  `OPENAI_MODEL_FALLBACK`). Embeddings `text-embedding-3-small` (1536 dimensões). Uma única chave
  (`OPENAI_API_KEY`).
- **Rationale**: Confirmado pelo usuário em 2026-10-13 ("apenas a OpenAI, com o GPT") e fixado na
  constitution. O tier "mini" atende latência (p95 ≤ 8 s) e custo; o fallback cobre REQ-REL-02.
  Nomes de modelo ficam fora do código para acompanhar o catálogo vigente.
- **Alternatives**: Azure OpenAI (descartado pelo usuário, ADR 0010);
  Anthropic/Gemini (fora da decisão do usuário).

## R-02 Web search

- **Decision**: DuckDuckGo via pacote `ddgs` (LangChain `DuckDuckGoSearchResults`), com cache Redis
  (TTL 15 min para câmbio e clima, 6 h para o resto), timeout de 5 s, retry e circuit breaker.
- **Rationale**: Escolha do usuário; sem chave. Não tem SLA e bloqueia rajadas, por isso cache e
  breaker são obrigatórios (REQ-REL-01/03). Resultados entram no prompt como dado não confiável.
- **Alternatives**: Tavily (exige chave; descartado pelo usuário); SerpAPI (pago).

## R-03 Busca lexical (BM25)

- **Decision**: BM25 real com **`bm25s`** em memória, montado a partir da tabela `chunks`. A
  tokenização faz minúsculas, remove acentos e stopwords PT ∪ EN, sem stemming (a reescrita
  PT↔EN de R-05 cobre variações). O índice é construído no startup da API e reconstruído quando a
  impressão digital `(count(*), max(id))` de `chunks` muda, checada pelo próprio retriever no
  máximo a cada 60 s (sem depender da tarefa periódica). No compose, a API sobe depois do job
  `ingest` concluir (`service_completed_successfully`).
- **Rationale**: BM25 de verdade, exigido pelo usuário para a entrega final, sem trocar a imagem do
  Postgres. O corpus é pequeno (milhares de trechos), então montar o índice leva segundos e cabe em
  memória.
- **Trade-offs aceitos**: reconstrução do índice a cada ingestão; uma cópia do índice por réplica
  da API; janela de até 60 s entre a ingestão e o índice atualizado numa API já em execução.
- **Alternatives**: FTS do Postgres (`tsvector` + `ts_rank_cd`, não é BM25); `rank_bm25` (mais
  lento que `bm25s`); **ParadeDB `pg_search`** (BM25 nativo no banco, sem cópia por réplica — é o
  caminho de produção, ADR 0003).

## R-04 Fusão e reranker

- **Decision**: RRF (`k = 60`) sobre top-20 BM25 + top-20 densa por variação de consulta;
  reranker cross-encoder **FlashRank** com modelo multilíngue `ms-marco-MultiBERT-L-12` (~150 MB),
  CPU, aplicado ao top-30 fundido → top-5.
- **Rationale**: Cross-encoder pedido pelo usuário, multilíngue (PT/EN) e leve o bastante para CPU
  (~100–300 ms). `bge-reranker-v2-m3` (~2,2 GB) deixaria a imagem e a latência inviáveis.
  O modelo é baixado no primeiro uso para um volume (`models-cache`), nunca para o repositório ou a
  imagem (constitution XI).
- **Alternatives**: `bge-reranker-v2-m3` (qualidade maior, custo alto); rerank por LLM (caro e
  lento); sem rerank (perde precisão no top-5).

## R-05 Limiar de relevância do Knowledge (pendente do clarify)

- **Decision**: Score do reranker (0–1) com limiar inicial **0,30**; abaixo dele em todas as
  variações, o Knowledge declara falta de informação ou pede web search/escalonamento (REQ-RAG-07).
  O valor é calibrado no conjunto rotulado e fica em `RAG_RELEVANCE_THRESHOLD`.
- **Rationale**: Score de cross-encoder é mais estável que similaridade de cosseno; calibração com
  produto inexistente e perguntas reais define o ponto de corte.
- **Alternatives**: Limiar por cosseno (sensível ao modelo de embedding); sem limiar (alucina).

## R-06 Orçamento de tokens (pendente do clarify)

- **Decision**: **20.000 tokens por execução** (entrada + saída, somados do `usage_metadata` de
  cada chamada), configurável em `TOKEN_BUDGET_PER_RUN`. Ao estourar → `degraded_response`
  (REQ-ORC-04).
- **Rationale**: Cobre pergunta composta com replanejamento e contexto de 5 trechos com folga
  (~4–8k típicos) e corta loops caros.
- **Alternatives**: Orçamento em custo (USD) — depende de tabela de preço; fica como métrica.

## R-07 Confiança dos especialistas

- **Decision**: Confiança = `min(autoavaliação do modelo, sinal objetivo)`. Knowledge: sinal = score
  do melhor trecho reranqueado (ou presença de resultado web). Support: 1,0 se todas as consultas
  retornaram ok, 0,5 se parcial, 0,0 se falharam. Limiares do clarify: replaneja < 0,70; escala após
  2 tentativas < 0,70 ou 1 < 0,40.
- **Rationale**: A confiança autodeclarada por LLM é mal calibrada; o mínimo com um sinal objetivo
  evita respostas confiantes sem base.
- **Alternatives**: Só autoavaliação (mal calibrada); logprobs (não disponível com saída
  estruturada em todos os modelos).

## R-08 Desenho do Supervisor

- **Decision**: Supervisor = **planejador LLM + política determinística**. A chamada LLM produz o
  `Plan` estruturado (rota, subtarefas, idioma, intenção sensível, confiança, justificativa). Depois
  de cada rodada, uma função pura avalia `results` contra os limiares e decide: sintetizar,
  replanejar (nova chamada LLM com o histórico de tentativas), escalar ou degradar. Fan-out via
  `Send`; transições via `Command(goto=...)`.
- **Rationale**: Corta uma chamada LLM por rodada, torna replanejamento e escalonamento testáveis
  sem modelo e garante término (`max_steps = 6`).
- **Alternatives**: Supervisor LLM a cada passo (mais caro e não determinístico); router de uma
  passada (ADR 0001).

## R-09 Identidade dentro do grafo

- **Decision**: A API resolve `user_id` do JWT e invoca o grafo com
  `config = {"configurable": {"thread_id": f"{user_id}:{conversation_id}", "user_id": user_id}}`.
  As tools de Support recebem `config: RunnableConfig` (injetado pelo LangChain e invisível ao
  schema da tool) e leem `user_id` dali.
- **Rationale**: Atende constitution I e REQ-SEC-03 por construção; o `thread_id` prefixado pelo
  usuário é uma segunda barreira contra acesso cruzado de checkpoints.
- **Alternatives**: `user_id` no estado (visível ao LLM); `InjectedToolArg` (equivalente, mais
  verboso).

## R-10 HITL e retomada

- **Decision**: Nó `escalation` cria o ticket e chama `interrupt({...})`; a API responde
  `awaiting_human`. `POST /v1/handoffs/{id}/reply` (papel `operator`) carrega o dono do ticket do
  banco e chama `graph.ainvoke(Command(resume={"reply", "action_decision"}), config)` de forma
  síncrona; a mensagem final fica no estado e a conversa passa a `resolved`. Entrega ao lojista por
  polling de `GET /v1/conversations/{id}` (P1) e SSE (P2).
- **Rationale**: Retomada da mesma execução (REQ-HITL-03) com o checkpointer; síncrono é mais
  simples e cabe nos 5 s (uma chamada LLM).
- **Alternatives**: Retomada em fila/worker (mais peças); ticket sem retomada (a resposta humana não volta à conversa).

## R-11 Tarefas periódicas (SLA, expiração, expurgo)

- **Decision**: Uma tarefa `asyncio` no lifespan da API, a cada 60 s, protegida por
  `pg_try_advisory_lock` para rodar em uma réplica só: avisa SLA (15 min), expira (24 h) e, uma vez
  por dia, expurga por prazo (90 d / 30 d / 1 ano).
- **Rationale**: Sem worker nem scheduler extra; o lock evita execução duplicada com réplicas.
- **Alternatives**: Celery/Arq + beat (mais containers); cron no host (fora do compose).

## R-12 Acesso a dados e migrações

- **Decision**: `psycopg` 3 (async, pool compartilhado com o checkpointer), SQL explícito em
  funções de repositório pequenas, migrações em arquivos `.sql` numerados aplicados no startup por
  um runner de ~30 linhas com tabela `schema_migrations`.
- **Rationale**: ~12 tabelas e consultas simples; ORM e Alembic adicionam camada sem necessidade
  (constitution XII). `pgvector` é mais direto em SQL.
- **Alternatives**: SQLAlchemy 2 + Alembic (mais boilerplate); SQLModel (mesma camada).

## R-13 Guardrails

- **Decision**: Entrada: (1) mascaramento de PII por regex + Luhn (CPF/CNPJ com dígito
  verificador), (2) heurísticas de injeção (padrões conhecidos), (3) classificador LLM com saída
  estruturada (`safe | injection | out_of_scope | sensitive | human_request`). Saída: re-máscara de
  PII, padrões de promessa financeira ("vou estornar", "garanto"), verificação de grounding por LLM
  só quando a resposta veio do Knowledge. Conteúdo recuperado vai delimitado em
  `<untrusted_context>` com instrução explícita de não obedecer.
- **Rationale**: Cobre REQ-GR-01..05 com poucas dependências; regex primeiro garante PII fora do
  LLM antes de qualquer chamada.
- **Alternatives**: Presidio (modelos spaCy pesados; PT fraco), NeMo Guardrails / LLM Guard
  (dependências e modelos grandes).

## R-14 Resiliência

- **Decision**: `tenacity` para retry com backoff exponencial e jitter; circuit breaker próprio
  (~30 linhas, estado em memória por processo) para OpenAI, DuckDuckGo e reranker; timeouts por
  chamada (LLM 20 s, web 5 s, tools 2 s); fallback de modelo via `with_fallbacks`.
- **Rationale**: `tenacity` é padrão e async; bibliotecas de breaker existentes são síncronas.
  Estado por processo é aceitável aqui (`shortcut:` documentado).
- **Alternatives**: `pybreaker` (sync), breaker em Redis (compartilhado, mais complexo).

## R-15 Rate limit e idempotência

- **Decision**: Redis. Rate limit por janela fixa de 60 s (`INCR` + `EXPIRE`), 30 req/min →
  429 + `Retry-After`. Idempotência: chave `idem:{user}:{key}` guarda hash do corpo + resposta por
  24 h; corpo diferente → 409.
- **Rationale**: Simples e suficiente; janela fixa permite rajada na virada do minuto
  (`shortcut:` documentado).
- **Alternatives**: Sliding window/token bucket em Lua (mais preciso, mais código).

## R-16 Autenticação

- **Decision**: JWT HS256 (`PyJWT`), claims `sub`, `role`, `exp` (1 h), `iss`, `aud`; segredo em
  `JWT_SECRET`. Tokens emitidos por `scripts/issue_token.py` para usuários do seed; não há endpoint
  de login.
- **Rationale**: Sem IdP real (assumption da spec); um script local não expõe superfície de ataque.
- **Alternatives**: RS256 com JWKS (adequado com IdP real; registrado como evolução).

## R-17 Ingestão

- **Decision**: `httpx` + `urllib.robotparser` (stdlib) + sitemap XML (stdlib) + `trafilatura`
  (extração e remoção de boilerplate) + `pypdf`. Allowlist de domínios e lista curada de URLs
  semente em `rag/sources.yaml`. Chunking por títulos, 400–800 tokens, overlap 80, tabelas inteiras.
- **Rationale**: Sites da Getnet podem ter partes renderizadas por JS e sitemap incompleto; a lista
  curada garante cobertura dos 10 cenários. Idempotência por `sha256` do texto limpo.
- **Alternatives**: Playwright para renderização (pesado no job; reservado se o conteúdo exigir);
  `unstructured` (dependências grandes).

## R-18 Observabilidade

- **Decision**: OpenTelemetry SDK com spans manuais por nó/tool/retrieval e
  `opentelemetry-instrumentation-openai-v2` (convenções GenAI) exportando OTLP para o Langfuse v3
  self-hosted (profile `obs`). `structlog` JSON em stdout com processador de máscara de PII.
  `prometheus_client` em `/metrics` (porta interna), Prometheus com regras de alerta e Grafana com
  datasource e dashboards provisionados.
- **Rationale**: Um único pipeline de traces; sem o profile `obs` o exporter fica desligado e nada
  quebra. Alertas visíveis em Prometheus/Grafana.
- **Alternatives**: Callback nativo do Langfuse (acopla código ao fornecedor); Alertmanager
  (entrega de alertas fica como evolução).

## R-19 Testes e avaliação

- **Decision**: `pytest` + `pytest-asyncio`; LLM fake roteirizado por nó (implementa
  `ainvoke`/`with_structured_output`) injetado via `app.core.llm.get_model(role)`; embeddings fake
  determinísticas; reranker fake. Postgres/Redis reais em compose `test` numa rede `internal: true`
  (sem saída externa). `schemathesis` contra o OpenAPI. Avaliação com modelo real: script próprio
  para rota, tools, recall@5/MRR/nDCG + **RAGAS** para faithfulness e answer relevancy. `k6` no
  profile `load`. Marcador `@pytest.mark.req("REQ-...")` + `scripts/check_traceability.py` gera a
  matriz e falha se um requisito entregue ficar sem teste.
- **Rationale**: Determinismo (constitution VI) e rastreabilidade (V). RAGAS cobre as métricas de
  RAG; DeepEval duplicaria.
- **Alternatives**: DeepEval (equivalente; uma ferramenta basta); Testcontainers (mais lento no
  Windows/CI que compose).

## R-20 Prompts versionados

- **Decision**: Um arquivo Markdown por prompt em `prompts/`, carregado no startup; `sha256[:12]`
  do conteúdo vai como atributo `prompt.version` em cada span de LLM.
- **Rationale**: Diffs legíveis, rastreio de regressão por versão de prompt (ADR 0009).

## R-21 Execução local no Windows

- **Decision**: Todos os comandos de teste, lint e tipos rodam via `docker compose` (serviços
  `tests` e `lint` em `docker-compose.test.yml`); o `Makefile` é só um atalho para quem tem `make`
  (Linux/macOS/CI) e o README documenta o comando `docker compose` equivalente de cada alvo.
  `.gitattributes` com `* text=auto eol=lf` evita CRLF em scripts que rodam em container Linux.
  O hook de pre-commit usa `gitleaks-docker` e é instalado com `uvx pre-commit install` (o `uv` já
  existe no host e traz o próprio Python).
- **Rationale**: A máquina de desenvolvimento (Windows) não tem Python nem `make`; o avaliador pode
  estar em qualquer SO.
