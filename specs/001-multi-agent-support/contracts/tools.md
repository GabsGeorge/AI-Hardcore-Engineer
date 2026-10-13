# Contrato das tools dos agentes

Contrato interno entre os agentes e as tools. Todas as tools: entrada validada por Pydantic,
timeout de 2 s (web: 5 s), retry com backoff (REQ-REL-01), span próprio e evento de auditoria
`tool_call`. **Nenhum schema contém identidade**: as tools de Support leem `user_id` de
`config["configurable"]` (parâmetro `config: RunnableConfig`, injetado e invisível ao modelo).

## Allowlist por agente (REQ-ORC-05)

| Agente | Tools permitidas |
| --- | --- |
| Knowledge | `search_knowledge_base`, `web_search` |
| Support | `get_settlement_schedule`, `diagnose_terminal`, `lookup_decline_code`, `get_recent_transactions`, `get_customer_profile`, `search_knowledge_base` |
| Escalation | `create_ticket`, `request_action_approval` |
| Supervisor | nenhuma (só planeja e delega) |

Chamada fora da allowlist → status `denied`, auditoria e resultado de erro para o Supervisor.

## Knowledge

| Tool | Entrada | Saída |
| --- | --- | --- |
| `search_knowledge_base` | `query: str (1..500)`, `lang: "pt"\|"en"\|None` | `list[{chunk_id, title, url, section, content, score: 0..1}]` (top-5 após rerank) |
| `web_search` | `query: str (1..300)` | `list[{title, url, snippet, retrieved_at}]` (máx. 5; cache Redis) |

## Support (dados do usuário do token)

| Tool | Entrada | Saída |
| --- | --- | --- |
| `get_settlement_schedule` | `from_date: date`, `to_date: date` (máx. 90 dias) | `list[{expected_date, amount_cents, status, transaction_count}]` |
| `diagnose_terminal` | `terminal_id: str \| None` (todos se ausente) | `list[{terminal_id, model, connectivity, status, last_seen_at, last_error, suggested_checks: list[str]}]` |
| `lookup_decline_code` | `code: str (1..4)` | `{code, description, action}` ou `{code, known: false}` |
| `get_recent_transactions` | `days: int (1..30)`, `status: "approved"\|"declined"\|None`, `limit: int (1..50)` | `list[{id, created_at, amount_cents, method, installments, status, decline_code}]` |
| `get_customer_profile` | — | `{trade_name, plan, settlement_days, anticipation_enabled, terminal_count}` |

`terminal_id` é filtrado também pelo dono: terminal de outro lojista retorna lista vazia, nunca
erro que revele existência.

## Escalation

| Tool | Entrada | Saída |
| --- | --- | --- |
| `create_ticket` | `reason: enum`, `summary: str (1..1000)` | `{ticket_id, sla_due_at, expires_at}` |
| `request_action_approval` | `action: "open_dispute"`, `params: {transaction_id: str, reason: str}` | `{ticket_id, decision: "pending"}` — executa só após `approve` (REQ-HITL-04) |

## Retorno ao Supervisor

Cada especialista devolve um `AgentResult` (ver [data-model.md](../data-model.md) §3) com
`confidence` calculada como em research R-07.
