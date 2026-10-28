# ADR 0011: Canal SSE de eventos da conversa com teto por usuário

- **Status**: Aceito · **Data**: 2026-10-28 · **Requisitos**: REQ-API-07, REQ-SEC-08, REQ-REL-04

## Contexto

A spec 002 introduziu `GET /v1/conversations/{id}/events` para a UI web receber
`handoff_update`, `final_message`, `sla_breached` e `handoff_expired` sem polling. O ADR 0004
já descreve o fluxo HITL que publica nesses eventos, mas ficou em aberto o custo do canal
em si: cada conexão SSE segura um worker da API até o cliente desconectar (ou até o
`handoff_expired` encerrar o stream), e um usuário malicioso ou um cliente web com bug pode
abrir N conexões em paralelo e esgotar o pool.

O rate limit do REQ-SEC-08 cobre `POST /v1/chat`, não streams de longa duração — ele mede
requests/min, não conexões abertas simultaneamente. É um recurso diferente.

## Decisão

Teto de **conexões SSE simultâneas por usuário** no canal `/v1/conversations/{id}/events`,
configurável via `SSE_EVENTS_MAX_PER_USER` (default 3). Implementação:

- contador in-memory `dict[user_id, int]` protegido por `asyncio.Lock`;
- `_acquire_sse_slot(user_id)` roda antes de `EventSourceResponse(_generator())`;
- `_release_sse_slot(user_id)` no `finally` do generator (garante liberação em erro, close
  do cliente ou shutdown da API);
- excedente retorna `HTTP 429` com body `{code: "too_many_connections", message: "Too many
  open event streams (max N)."}` — mesmo contrato de erro das outras 429 (REQ-API-02).

O `/v1/chat/stream` (streaming do turno) **não** usa esse teto: cada chamada é curta
(segundos, até `done`) e já é limitada pelo rate limit por usuário. Só o canal `events`,
que é long-lived, carrega o contador.

## Alternativas

- **Redis counter com TTL por conexão**: suporta cluster multi-réplica, mas o canal já é
  pinned por conexão TCP (nginx `ip_hash` ou sticky); in-memory é correto por réplica. Fica
  como evolução no mesmo molde do shortcut 2 em `docs/limitations.md` (circuit breaker).
- **Teto global na API inteira (sem per-user)**: protege o pool, mas um lojista mal
  comportado derruba o canal pra todo mundo. Rejeitado.
- **Fechar a conexão mais antiga ao estourar**: implementação mais complexa (LRU por user)
  sem ganho pra UX (o cliente web mantém uma conexão só).

## Consequências

- (+) Fecha o vetor de DoS leve que ficou "parcial" no threat model da spec 001.
- (+) Contrato claro: 429 `too_many_connections` com `max` no mensagem, cliente mostra toast
  e tenta reconectar após o backoff.
- (−) In-memory ⇒ o teto é por réplica; cluster com N réplicas deixa `N * MAX_SSE_PER_USER`
  conexões por usuário no limite — aceitável para o volume alvo. Evolução documentada acima.
- (−) O stream `/v1/chat/stream` não tem esse teto. Decisão deliberada; a defesa dele é o
  rate limit do POST, não o número de conexões.

## Contrato de erros do canal

| Status | Code                      | Quando                                             |
| ------ | ------------------------- | -------------------------------------------------- |
| 401    | `unauthorized`            | token ausente ou expirado                          |
| 403    | `forbidden` / `csrf_failed` | conversa pertence a outro user; CSRF em mutações |
| 404    | `not_found`               | conversation_id inexistente                        |
| 429    | `too_many_connections`    | `>= SSE_EVENTS_MAX_PER_USER` streams abertas       |

## Testes de referência

- `tests/security/test_sse_connection_limit.py` — acquire/release direto + endpoint 429
- `tests/security/test_chat_stream_audit_endpoint.py` — audit do 403 em stream
