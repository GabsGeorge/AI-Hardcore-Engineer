# Eventos SSE — delta da 002

A 001 já definiu `agent_step`, `handoff`, `done` em `/v1/chat/stream` e
`handoff_update`, `final_message` em `/v1/conversations/{id}/events`
(ver [../../001-multi-agent-support/contracts/events.md](../../001-multi-agent-support/contracts/events.md)
no commit mergeado). A 002 adiciona dois eventos para que a UI avise o lojista sem polling.

## `/v1/conversations/{id}/events` — eventos adicionados

| event              | quando                                                      | data                                                                 |
|--------------------|-------------------------------------------------------------|----------------------------------------------------------------------|
| `sla_breached`     | o scheduler detecta que `sla_due_at` do ticket aberto venceu| `{ ticket_id, breached_at }`                                         |
| `handoff_expired`  | o scheduler expira o ticket; a conversa recebe final        | `{ ticket_id, final_message }`                                       |

Semântica:

- O cliente SSE desduplica eventos pelo par `(event, data.ticket_id)`.
- `sla_breached` **não** encerra o stream; o canal continua esperando a resposta do operador
  ou o `handoff_expired` subsequente.
- `handoff_expired` é seguido do `final_message` do turno (texto gerado pela retomada da
  thread), então o cliente que recebe `handoff_expired` espera o próximo `final_message` antes
  de desenhar o estado "expirada". Em caso de perda de conexão, o cliente reconecta e lê o
  estado consolidado em `GET /v1/conversations/{id}`.

## Cabeçalhos obrigatórios do stream (resposta do nginx)

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no        # necessário no nginx para flush imediato
```
