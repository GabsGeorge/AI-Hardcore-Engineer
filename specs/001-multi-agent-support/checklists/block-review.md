# Block Review Checklist: Getnet Multi-Agent Support System

**Purpose**: Roteiro do revisor **somente leitura** acionado ao fim de cada bloco, sobre o diff
integrado na branch `001-multi-agent-support`, antes do próximo bloco.
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [threat-model.md](../threat-model.md)

**Como usar**: o revisor não edita arquivos. Para cada item, responde ✅, ❌ ou N/A com
`arquivo:linha` como evidência. Qualquer ❌ em item marcado **[bloqueante]** impede o próximo
bloco; o agente principal corrige e o revisor roda de novo. Este checklist cumpre as revisões
obrigatórias de segurança e de orquestração da constitution.

## Pré-condições do bloco

- [ ] Suíte completa verde via `docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm tests` **[bloqueante]**
- [ ] Lint e tipos verdes via `docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm lint` **[bloqueante]**
- [ ] Commits no formato `feat(T049): descrição [REQ-...]`, um por task ou grupo lógico
- [ ] Nenhum arquivo congelado alterado fora do bloco do agente principal: `src/app/graph/state.py`, `src/app/api/schemas.py`, `src/app/tools/interfaces.py`, registro de nós em `src/app/graph/builder.py` **[bloqueante]**

## Checklist 1 — Segurança

### Identidade e IDOR

- [ ] O usuário efetivo vem só do `sub` do JWT; nenhum caminho usa `user_id` do corpo como identidade (constitution I) **[bloqueante]**
- [ ] `user_id` divergente → 403 e auditoria antes de qualquer agente ou tool (REQ-SEC-02) **[bloqueante]**
- [ ] Nenhum schema de tool exposto ao modelo contém identidade; tools leem `user_id` de `RunnableConfig` (REQ-SEC-03) **[bloqueante]**
- [ ] Toda consulta de dados de cliente filtra pelo dono, com SQL parametrizado **[bloqueante]**
- [ ] Conversa ou terminal de outro usuário → 404 ou lista vazia, sem revelar existência (REQ-MEM-01)
- [ ] `thread_id` é `{user_id}:{conversation_id}`; retomada de handoff usa o dono do ticket do banco

### PII

- [ ] Máscara de PII antes de qualquer chamada ao modelo (REQ-GR-02) **[bloqueante]**
- [ ] Logs, spans e auditoria não recebem texto sem máscara (constitution VII e X) **[bloqueante]**
- [ ] Respostas e resumos para o operador passam pela re-máscara de saída

### Segredos e artefatos

- [ ] Nenhum segredo no diff (gitleaks verde); só `.env.example`, sem valores (constitution II) **[bloqueante]**
- [ ] Nenhum artefato gerado rastreado (bancos, índices, caches, modelos, `.env`) (constitution XI) **[bloqueante]**
- [ ] Novos segredos ou variáveis entram por `pydantic-settings` e constam no `.env.example`

### Injeção

- [ ] Conteúdo recuperado (base e web) vai delimitado como dado não confiável e nunca como instrução (REQ-GR-05) **[bloqueante]**
- [ ] Nenhuma decisão de rota, autorização ou ação é tirada de texto livre do modelo; só de saída estruturada validada (LLM05)
- [ ] Ações com efeito colateral só executam após `approve` do operador (REQ-HITL-04)
- [ ] Prompts não contêm segredos

## Checklist 2 — Orquestração

### Rotas

- [ ] Toda rota do `Plan` corresponde a um nó registrado; plano inválido vai para `degraded_response` (REQ-ORC-01) **[bloqueante]**
- [ ] Fan-out com `Send` só para subtarefas independentes; resultados agregados pelo reducer de `results` (REQ-ORC-02)
- [ ] Bloqueio na entrada vai para `safe_response` sem acionar especialistas
- [ ] `route_trace` reflete o caminho real e chega na resposta

### Término e `max_steps`

- [ ] Todo ciclo incrementa `step` e respeita `MAX_STEPS = 6` (REQ-ORC-04) **[bloqueante]**
- [ ] `tokens_used` soma o `usage_metadata` de toda chamada e respeita `TOKEN_BUDGET_PER_RUN` **[bloqueante]**
- [ ] Limiares vêm da config (replaneja < 0,70; escala 2× < 0,70 ou 1× < 0,40), sem números mágicos
- [ ] Existe teste que prova o término (sem loop) para cada caminho novo do bloco

### Allowlist por agente

- [ ] Cada agente só chama as tools da sua allowlist em `src/app/tools/interfaces.py` (REQ-ORC-05) **[bloqueante]**
- [ ] Chamada fora da allowlist → `denied`, auditoria e resultado de erro ao Supervisor
- [ ] O Supervisor não chama tools

### Uso do estado

- [ ] Nenhum campo novo em `AgentState` fora do agente principal; `user_id` nunca no estado (ADR 0005) **[bloqueante]**
- [ ] Nós retornam atualizações parciais do estado, sem mutar listas compartilhadas
- [ ] Estado permanece serializável pelo checkpointer (REQ-ORC-06)
- [ ] Mensagens no estado já estão mascaradas

## Resultado

| Bloco | Data | Segurança | Orquestração | Achados bloqueantes | Liberado? |
| --- | --- | --- | --- | --- | --- |
| Fase 0 + grafo base | 2026-10-13 | ✅ (achados 1 e 2 corrigidos) | ✅ (achados 3, 5 e 6 corrigidos; 4 registrado na T120) | 1 (auditoria sem máscara) — corrigido em d67ff1c | ✅ LIBERADO na re-revisão |
| US2 + US1 + US3 | 2026-10-13 | ✅ (achados 1 e 3 corrigidos) | ✅ (achados 2, 4, 5, 6 e 7 corrigidos) | 1 (delimitador aninhado remontável) — corrigido em 38ede50 | ✅ LIBERADO |
| Fase 2 (US4+US5, US6, US7 + suítes transversais) | 2026-10-20 | ✅ (auditoria `operator_reply` e `action_*d` confirmadas em `tests/security/test_audit.py`; allowlist por agente verde) | ✅ (`route_trace` reflete real; MAX_STEPS respeitado; `results` reducer sem mutação) | 0 — audit T176 registrou 3 débitos não-bloqueantes (breaker só no DuckDuckGo, online-eval sem Langfuse, run_eval sem RAGAS), todos citados em `docs/limitations.md` | ✅ LIBERADO |
| Fase 3 (US9, US8, plataforma, polish) | 2026-10-28 | ⚠️→✅ 4 achados bloqueantes corrigidos nos itens 1–4 do backlog pós-fechamento (ver notas abaixo) | ✅ (SSE honra contracts/events.md; stream termina com `done`; rate limit por janela fixa; idempotência por 24 h) | 4 bloqueantes **todos corrigidos**: (a) API em `expose:` sem publicar — f72784a; (b) CSRF sem middleware global para endpoints mutantes cookie-authed — d0fd0b0; (c) SSE `/v1/conversations/{id}/events` sem teto de conexões por usuário — d4b4cf2; (d) race entre `SELECT status` e `graph.ainvoke(Command(resume=...))` em `/v1/handoffs/{id}/reply` permitia resume duplo — d4b4cf2 | ✅ LIBERADO (ver `specs/002-web-ui/checklists/block-review.md` para os detalhes dos 4 fixes e o resultado de T177) |
