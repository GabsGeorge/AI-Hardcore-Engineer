# SSE: `/v1/chat/stream` e `/v1/conversations/{id}/events` (REQ-API-07)

Dois canais Server-Sent Events usam o mesmo formato `event:` + `data:` do padrão SSE.

## `POST /v1/chat/stream`

Mesmo payload de `POST /v1/chat`. Em vez de uma resposta única, o cliente recebe eventos
nomeados ao longo da execução:

| event          | quando                                      | data                                        |
|----------------|---------------------------------------------|---------------------------------------------|
| `agent_step`   | cada nó do grafo entra em execução          | `{"node": "supervisor" \| "knowledge" \| …}`  |
| `token`        | token (ou chunk pequeno) da síntese final   | `{"text": "..."}`                           |
| `handoff`      | handoff abre durante o turno                | `{"status": "awaiting_human", "ticket_id":…}` |
| `done`         | último evento, carrega o `ChatResponse`     | `ChatResponse` serializado em JSON          |

O cliente pode fechar a conexão a qualquer momento.

## `GET /v1/conversations/{id}/events`

Canal push para o dono da conversa. Entrega apenas eventos novos (long-polling):

| event              | quando                                           | data                           |
|--------------------|--------------------------------------------------|--------------------------------|
| `handoff_update`   | ticket muda de status (resolvido, expirado)      | `HandoffRef`                   |
| `final_message`    | nova mensagem assistant após handoff             | `{"content": "..."}`           |

Autenticação: Bearer JWT, idêntica aos demais endpoints. Dono: 200. Terceiros: 404.
