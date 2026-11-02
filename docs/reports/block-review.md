# Block Review — registros por fase

Este documento compila as revisões "read-only" acionadas no fechamento de cada bloco
(T090, T133, T175). Para cada fase, cita a data real da revisão, o escopo coberto, o
instrumento usado e os achados aplicados antes do merge.

A regra é fixa: revisor não edita; aponta ❌ com `arquivo:linha`; o agente principal
corrige; revisor roda de novo até liberar.

---

## Fase 1 — US1 + US2 + US3 (T090)

- **Data**: 2026-10-17
- **Escopo**: router de supervisor, agente de conhecimento, guardrails de entrada/saída.
- **Instrumento**: checklist embutido em `specs/001-multi-agent-support/checklists/block-review.md`.
- **Achados aplicados antes do merge**:
  - Guardrail de saída não re-mascarava PII na resposta ao lojista — corrigido em `src/app/guardrails/output.py` com teste `tests/security/test_pii.py::test_output_reapplies_mask`.
  - Supervisor podia rotear para `knowledge` sem threshold mínimo de confiança — ajustado para 0,30 (REQ-RAG-06).
  - `search_knowledge_base` logava documento inteiro em DEBUG — reduzido para `doc_id` + score.
- **Status**: liberado para merge; CI verde em todos os testes de injeção direta/indireta/identidade.

## Fase 2 — US4 + US5 + US6 (T133)

- **Data**: 2026-10-28
- **Escopo**: HITL, operador, admin, auditoria, SSE.
- **Instrumento**: `specs/002-web-ui/checklists/block-review.md` (seção completa; cobre
  o diff integrado da 002 + a soma com a 001 Fase 3 — foi usada também como registro de T177).
- **Achados aplicados antes do merge** (4 bloqueantes identificados por T177 e corrigidos):
  - **Item 1 — Primeiro uso quebrado** (`f72784a`): docker build do web, nginx não-root e API publicada.
  - **Item 2 — CSRF middleware global** (`d0fd0b0`): toda mutação cookie-authed passa por `enforce_csrf`; Bearer é isento (ADR 0005).
  - **Item 3 — CI web completo** (`e600454`): Vitest cobrindo guards e ChatPage; CI pipeline web ligado.
  - **Item 4 — Auditoria + limite SSE** (`d4b4cf2`): `/chat/stream` audita; `MAX_SSE_PER_USER=3` com 429 `too_many_connections`; `handoff/reply` bloqueia resume duplo.
- **Status**: liberado para merge; threat-model revisado e coerente (`specs/001-multi-agent-support/threat-model.md`).

## Fase 3 — US7 + polish final (T175)

- **Data**: 2026-10-28
- **Escopo**: busca web, k6 de carga, golden set de evals.
- **Instrumento**: continuação do checklist Fase 2 + revisão dirigida por `/security-review` em `src/app/tools/knowledge_tools.py` e `deploy/k6/chat.js`.
- **Achados aplicados antes do merge**:
  - DuckDuckGo sem circuit breaker — adicionado em `src/app/core/resilience.py`; limitação aceita documentada em `docs/limitations.md` §2.
  - k6 rodava com um único token — reescrito para gerar múltiplos tokens e reportar p50/p95 por rota (`deploy/k6/chat.js`, commit `ea4449d`).
  - Golden set não cobria crediário (sc-19/20/21) — adicionado em `067234c`.
  - Fontes RAG não cobriam consultas em inglês — adicionadas em `a1cf941` (`getnet.net/en`).
- **Status**: liberado para merge.

## Fase 4 — hardening de entrega (pós-fechamento, outubro 2026)

- **Data**: 2026-10-29 → 2026-10-30
- **Escopo**: pontos de desconto do enunciado (primeiro uso real, CI com pin por SHA,
  segurança Bearer vs cookie, threat-model com coluna de teste, CVE aceita documentada,
  smoke de 10 cenários).
- **Instrumento**: backlog interno dividido em 8 itens, cada um fechado com evidência
  (ver mensagens finais da sessão).
- **Entregas**:
  - Branch `002-release-hardening`: commits `d239e09` (bootstrap_env.sh), `03c0dc6`
    (trivy@SHA + Bearer + perms cache + traceability + smoke script),
    `a3b25a5` (threat-model coluna teste + CVE zod).
  - `docs/reports/smoke.md` com saídas reais dos 10 cenários.
- **Status**: em revisão para merge via PR.

---

## Como re-rodar uma revisão

1. Checkout do commit a revisar; `git log --name-only --since=<data>` para o escopo real.
2. Abrir o checklist do bloco e marcar ✅/❌/N/A por item, com `arquivo:linha`.
3. ❌ em `[bloqueante]` → agente principal corrige; revisor roda de novo.
4. Fechar o bloco só quando não restar bloqueante aberto.
