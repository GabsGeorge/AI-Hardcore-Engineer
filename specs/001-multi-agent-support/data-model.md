# Data Model: Getnet Multi-Agent Support System

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Date**: 2026-10-13

Um único Postgres 16 com `pgvector` (ADR 0002). Migrações em `src/app/db/migrations/*.sql`
(research R-12). Dados de cliente são fictícios e vêm de `src/app/db/seed.sql`. Valores monetários
em centavos (`bigint`); datas em `timestamptz` UTC.

## 1. Identidade

### `users`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | `text` PK | ex.: `cliente1988`, `operador01` |
| `role` | `text` | `merchant` \| `operator` \| `admin` (CHECK) |
| `display_name` | `text` | |
| `created_at` | `timestamptz` | default `now()` |

O JWT carrega `sub = users.id` e `role`; a API recusa tokens cujo `sub` não exista (REQ-SEC-01).

## 2. Dados mock do Support (seed determinístico, REQ-SUP-02)

### `merchants`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `user_id` | `text` PK → `users.id` | só `role = merchant` |
| `trade_name` | `text` | |
| `document_masked` | `text` | CNPJ já mascarado (`**.***.***/0001-**`) |
| `plan` | `text` | ex.: `Get Smart`, `Get Clássica` |
| `settlement_days` | `int` | prazo de liquidação (D+1, D+30) |
| `anticipation_enabled` | `bool` | |

### `terminals`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | `text` PK | |
| `merchant_id` | `text` → `merchants.user_id` | índice |
| `model` | `text` | `Get Smart`, `Get Clássica`, `Get Mini` |
| `serial` | `text` | |
| `connectivity` | `text` | `wifi` \| `chip_4g` \| `ethernet` |
| `status` | `text` | `online` \| `offline` \| `error` |
| `last_seen_at` | `timestamptz` | |
| `last_error` | `text` null | ex.: `NO_SIGNAL`, `WIFI_AUTH_FAILED` |

### `transactions`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | `text` PK | |
| `merchant_id` | `text` → `merchants.user_id` | índice (`merchant_id`, `created_at desc`) |
| `terminal_id` | `text` null → `terminals.id` | null para Link de Pagamento |
| `created_at` | `timestamptz` | |
| `amount_cents` | `bigint` | > 0 |
| `method` | `text` | `credit` \| `debit` \| `pix` \| `payment_link` |
| `installments` | `int` | ≥ 1 |
| `status` | `text` | `approved` \| `declined` |
| `decline_code` | `text` null → `decline_codes.code` | obrigatório se `declined` |

### `settlements`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | `text` PK | |
| `merchant_id` | `text` → `merchants.user_id` | índice (`merchant_id`, `expected_date`) |
| `transaction_id` | `text` → `transactions.id` | |
| `expected_date` | `date` | |
| `amount_cents` | `bigint` | líquido de taxas |
| `status` | `text` | `scheduled` \| `paid` \| `anticipated` |

### `decline_codes`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `code` | `text` PK | ex.: `05`, `51`, `57` |
| `description_pt` / `description_en` | `text` | |
| `action_pt` / `action_en` | `text` | ação recomendada |

O seed é relativo a uma data fixa (`SEED_REFERENCE_DATE`) para que "vendas de ontem" e "transação
recusada recente" sejam determinísticas em testes; em execução normal a referência é `today()`.

## 3. Conversa e execução

### `conversations`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | `uuid` PK | gerado pelo servidor se ausente |
| `user_id` | `text` → `users.id` | dono; toda leitura filtra por ele (REQ-MEM-01) |
| `created_at` | `timestamptz` | |
| `last_activity_at` | `timestamptz` | base da retenção de 90 dias |
| `handoff_status` | `text` | `none` \| `awaiting_human` \| `resolved` \| `expired` |

O histórico de mensagens e o estado do grafo vivem nos checkpoints do LangGraph
(`AsyncPostgresSaver`, tabelas `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) com
`thread_id = "{user_id}:{conversation_id}"`. Não há tabela de mensagens duplicada; a leitura usa
`graph.aget_state(config)` e a exclusão usa `checkpointer.adelete_thread(thread_id)`.

### Estado do grafo (`AgentState`, não persistido em tabela própria)

| Campo | Tipo | Observação |
| --- | --- | --- |
| `messages` | `list[AnyMessage]` (reducer `add_messages`) | já com PII mascarada |
| `summary` | `str \| None` | resumo do histórico antigo (REQ-MEM-02) |
| `language` | `str` | `pt` \| `en` \| outro (REQ-ORC-07) |
| `plan` | `Plan \| None` | rota, subtarefas, confiança, justificativa |
| `results` | `list[AgentResult]` (reducer `operator.add`) | um por subtarefa executada |
| `attempts` | `int` | rodadas de replanejamento |
| `step` | `int` | passos executados; limite 6 (REQ-ORC-04) |
| `tokens_used` | `int` | limite 20.000 (research R-06) |
| `route_trace` | `list[str]` | caminho percorrido, vai na resposta |
| `escalation` | `Escalation \| None` | motivo, ticket, ação pendente |
| `guardrail_flags` | `list[str]` | sinalizações de entrada/saída |
| `final_response` | `str \| None` | resposta entregue |

`user_id` **não** está no estado: vem de `config["configurable"]["user_id"]` (ADR 0005).

- `Plan`: `{route: list["knowledge"|"support"|"escalation"], subtasks: list[SubTask], confidence:
  float, rationale: str, language: str, sensitive: bool}`.
- `SubTask`: `{id, agent, query}`.
- `AgentResult`: `{subtask_id, agent, answer, confidence: float, sources: list[Source],
  tools_used: list[ToolCall], error: str | None}`.
- `Source`: `{title, url, kind: "kb"|"web", retrieved_at}`.
- `ToolCall`: `{name, status: "ok"|"error"|"timeout", latency_ms}`.

## 4. Base de conhecimento (REQ-RAG-01/02)

### `documents`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | `bigserial` PK | |
| `url` | `text` UNIQUE | domínio na allowlist |
| `title` | `text` | |
| `lang` | `text` | `pt` \| `en` |
| `source_type` | `text` | `page` \| `faq` \| `pdf` |
| `content_hash` | `text` | `sha256` do texto limpo; igual → não reindexa |
| `fetched_at` | `timestamptz` | data de coleta |

### `chunks`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | `bigserial` PK | |
| `document_id` | `bigint` → `documents.id` ON DELETE CASCADE | |
| `ord` | `int` | ordem no documento |
| `section` | `text` | caminho de títulos (`H1 > H2`) |
| `content` | `text` | 400–800 tokens; tabela nunca cortada |
| `lang` | `text` | |
| `embedding` | `vector(1536)` | índice HNSW (`vector_cosine_ops`) |

O índice **BM25** não é uma coluna: é montado em memória pela API (`bm25s`) a partir de
`chunks.content`, no startup e quando a impressão digital `(count(*), max(id))` muda
(research R-03, ADR 0003). A ingestão substitui os trechos de um documento alterado (novos `id`),
o que muda a impressão digital.

## 5. Human-in-the-loop

### `handoffs`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | `uuid` PK | `ticket_id` |
| `conversation_id` | `uuid` → `conversations.id` | |
| `user_id` | `text` → `users.id` | dono da conversa; usado na retomada |
| `reason` | `text` | `low_confidence` \| `human_request` \| `sensitive_topic` \| `repeated_failures` \| `side_effect_action` |
| `status` | `text` | `awaiting_human` \| `resolved` \| `expired` |
| `priority` | `text` | `normal` \| `high` (sobe ao estourar SLA) |
| `summary` | `text` | resumo para o operador, sem PII |
| `context` | `jsonb` | rota, tools usadas, últimas mensagens mascaradas |
| `pending_action` | `jsonb` null | `{type: "open_dispute", params, decision: "pending"|"approved"|"rejected"}` |
| `created_at` | `timestamptz` | |
| `sla_due_at` | `timestamptz` | `created_at + 15 min` |
| `sla_notified_at` | `timestamptz` null | aviso enviado |
| `expires_at` | `timestamptz` | `created_at + 24 h` |
| `operator_id` | `text` null → `users.id` | `role = operator` |
| `operator_reply` | `text` null | |
| `resolved_at` | `timestamptz` null | |

**Transições**

```text
handoffs.status:     awaiting_human ──reply──▶ resolved
                     awaiting_human ──24 h──▶ expired
                     resolved / expired: terminais (reply → 409)
pending_action:      pending ──approve──▶ approved (executa a ação simulada)
                     pending ──reject───▶ rejected (lojista é informado)
conversations.handoff_status acompanha o ticket aberto mais recente.
```

## 6. Auditoria, feedback e retenção

### `audit_events`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | `bigserial` PK | |
| `ts` | `timestamptz` | |
| `actor_id` | `text` | `users.id`; após exclusão LGPD vira `deleted:<hmac>` |
| `actor_role` | `text` | |
| `action` | `text` | `auth_failed`, `forbidden_user_mismatch`, `tool_call`, `escalated`, `operator_reply`, `action_approved`, `data_deleted`, ... |
| `target` | `text` | recurso alvo (ex.: `user:clienteB`, `tool:get_settlement_schedule`) |
| `outcome` | `text` | `allowed` \| `denied` \| `error` |
| `trace_id` | `text` | |
| `metadata` | `jsonb` | sem PII crua |

### `feedback`

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | `bigserial` PK | |
| `trace_id` | `text` | índice |
| `user_id` | `text` → `users.id` | |
| `conversation_id` | `uuid` null | |
| `rating` | `smallint` | `-1` \| `1` |
| `comment` | `text` null | PII mascarada, máx. 1.000 caracteres |
| `created_at` | `timestamptz` | |

### Retenção (clarify Q4, REQ-SEC-09)

| Dado | Prazo | Base |
| --- | --- | --- |
| `conversations` + checkpoints, `feedback` | 90 dias | `last_activity_at` / `created_at` |
| Logs e traces | 30 dias | configuração do Langfuse/coletor |
| `handoffs`, `audit_events` | 1 ano | `created_at` / `ts` |

Expurgo diário (research R-11). `DELETE /v1/me/data` apaga na hora conversas, checkpoints e
feedback do usuário e pseudonimiza `audit_events.actor_id`.

## 7. Redis (efêmero, sem persistência obrigatória)

| Chave | TTL | Uso |
| --- | --- | --- |
| `rl:{user_id}:{minuto}` | 60 s | rate limit |
| `idem:{user_id}:{key}` | 24 h | hash do corpo + resposta |
| `web:{sha256(query)}` | 15 min / 6 h | cache de web search |
| `emb:{sha256(text)}` | 7 dias | cache de embeddings de consulta |
