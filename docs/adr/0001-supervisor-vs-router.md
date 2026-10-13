# ADR 0001: Supervisor em ciclo com replanejamento

- **Status**: Aceito · **Data**: 2026-10-13 · **Requisitos**: REQ-ORC-01..04

## Contexto

O enunciado pede um Router Agent. Um router de uma passada não consegue
replanejar nem tratar perguntas compostas.

## Decisão

Supervisor em ciclo no LangGraph: um planejador LLM com saída estruturada (`Plan`) e uma política
determinística que, após cada rodada de especialistas, decide sintetizar, replanejar, escalar ou
degradar. Fan-out com `Send`, transições com `Command(goto=...)`. Limite de 6 passos e 20k tokens.

## Alternativas

- **Router de uma passada**: mais rápido e barato, mas não se recupera de baixa confiança nem
  decompõe perguntas compostas.
- **Supervisor LLM a cada passo**: mais flexível, porém mais caro, não determinístico e difícil de
  testar.

## Consequências

- (+) Replanejamento e escalonamento testáveis com LLM fake; término garantido.
- (−) Mais latência e tokens em perguntas difíceis (p95 ≤ 15 s para compostas).
