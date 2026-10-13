# Contrato de eventos SSE (P2, REQ-API-07)

Formato `text/event-stream`; cada evento tem `event:` e `data:` em JSON. Toda conexão exige o
mesmo Bearer token das rotas REST.

## `POST /v1/chat/stream`

| Evento | `data` | Ordem |
| --- | --- | --- |
| `agent_step` | `{node: string, status: "start"\|"end", ts}` | 0..n, na ordem de execução |
| `token` | `{text: string}` | 0..n, somente durante `synthesize` |
| `done` | `ChatResponse` completo (openapi.yaml) | exatamente 1, sempre o último |
| `error` | `Error` (openapi.yaml) | substitui `done` em falha |

## `GET /v1/conversations/{id}/events`

| Evento | `data` |
| --- | --- |
| `handoff_update` | `{ticket_id, status, priority, sla_due_at}` (inclui aviso de SLA estourado) |
| `final_message` | `{content, trace_id}` após retomada ou expiração |
| `keepalive` | `{}` a cada 15 s |

O canal base continua sendo `GET /v1/conversations/{id}` com polling a cada 3 s; SSE é melhoria.
