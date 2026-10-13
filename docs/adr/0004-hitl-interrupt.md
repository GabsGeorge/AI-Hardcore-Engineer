# ADR 0004: Human-in-the-loop com interrupt() e checkpointer persistente

- **Status**: Aceito · **Data**: 2026-10-13 · **Requisitos**: REQ-HITL-01..06

## Contexto

Um ticket desacoplado não devolve a resposta humana ao agente nem à conversa original.

## Decisão

O nó `escalation` cria o ticket e chama `interrupt()`; o estado fica no `AsyncPostgresSaver`. O
operador responde em `POST /v1/handoffs/{id}/reply`; a API retoma a mesma execução com
`Command(resume=...)`, usando a identidade do dono do ticket lida do banco. Ações com efeito
colateral ficam `pending` até `approve`. A entrega ao lojista é por polling (P1) e SSE (P2). SLA de
15 min com alerta e expiração em 24 h, por tarefa periódica com advisory lock.

## Alternativas

- **Ticket desacoplado sem retomada**: simples, mas a conversa nunca recebe a resposta humana.
- **Retomada assíncrona em fila**: mais peças sem ganho para o volume do desafio.

## Consequências

- (+) A mesma thread entrega a resposta final; testável com `interrupt`/`resume` e LLM fake.
- (−) Exige persistência, endpoint de operador e tarefa periódica.
