# ADR 0005: Identidade só via token; tools com contexto injetado

- **Status**: Aceito · **Data**: 2026-10-13 · **Requisitos**: REQ-SEC-01..03, constitution I

## Contexto

O enunciado envia `user_id` no corpo. Se ele substituir o usuário autenticado, há IDOR
(um cliente lê dados de outro).

## Decisão

O usuário efetivo é o `sub` do JWT validado. `user_id` no corpo é opcional; se divergir → 403,
auditoria e nenhum agente executado. O grafo recebe `user_id` em `config["configurable"]`, fora do
estado visível ao LLM; as tools leem dali via `RunnableConfig` injetado. O `thread_id` é
`{user_id}:{conversation_id}`.

## Alternativas

- **`user_id` do corpo**: IDOR por definição.
- **`user_id` como parâmetro da tool**: o modelo poderia ser induzido a trocar o alvo.

## Consequências

- (+) Injeção em linguagem natural não muda o cliente consultado, por construção.
- (−) Testes e demo precisam gerar tokens (`scripts/issue_token.py`).
