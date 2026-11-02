# 003 — UI hardening

**Fonte**: [docs/reports/e2e-browser.md](../../docs/reports/e2e-browser.md),
[docs/reports/ui-review.md](../../docs/reports/ui-review.md) e meu
[docs/reports/e2e-api.md](../../docs/reports/e2e-api.md). Score médio da UI pelo
agente externo: **3,2/10 — produto não entregável**.

## Objetivo

Tornar a aplicação **usável de ponta a ponta pela UI**: lojista envia pergunta
e vê a resposta; operador fecha ticket; registro de novo lojista funciona sem
intervenção manual no banco; privacidade e mobile deixam de ser placeholders.

## Priorização

Agrupada por **"desbloqueia o próximo"** (P0 abre caminho pros outros).
Esforço: XS <30min, S 30–90min, M 2–4h, L 4–8h.

### P0 — Chat volta a responder (destrava TUDO)

| ID | Item | Esforço | Arquivos |
|---|---|---|---|
| T001 | **SSE parser aceita CRLF** — split por `/\r?\n\r?\n/`, linhas por `/\r?\n/` | **XS** | [apps/web/src/lib/sse.ts:112,115,117,125](../../apps/web/src/lib/sse.ts#L112) |
| T002 | **Register cria `users` + `merchants` em transação** (Bug 2 da e2e-api.md) | M | [src/app/api/auth_endpoints.py:140](../../src/app/api/auth_endpoints.py#L140), [src/app/db/repo.py](../../src/app/db/repo.py), nova migração 0003 |
| T003 | **Admin em `/v1/chat*` → 403, não 500** (Bug 3) | XS | [src/app/api/chat.py](../../src/app/api/chat.py) (adicionar `require_role("merchant")`) |
| T004 | **CurrentUser carrega `account_id` + `user_id`** (fix display_name "cliente1988") | S | [src/app/api/auth.py:92](../../src/app/api/auth.py#L92), [src/app/api/auth_endpoints.py:412](../../src/app/api/auth_endpoints.py#L412) |

### P1 — Ciclo HITL fecha

| ID | Item | Esforço | Arquivos |
|---|---|---|---|
| T010 | **Fila: ticket_id na URL do detalhe** (hoje `/queue/undefined`) | XS | [apps/web/src/features/queue](../../apps/web/src/features/queue) |
| T011 | **Reply do operador: fix HTTP 500** — investigar + fix | S | [src/app/api/handoffs.py:30](../../src/app/api/handoffs.py#L30) |
| T012 | **UI SSE: renderizar bolha-sistema no evento `handoff`** com ticket + fila | S | [apps/web/src/features/chat/ChatPage.tsx](../../apps/web/src/features/chat/ChatPage.tsx) |
| T013 | **UI SSE: stepper com `agent_step`** (comunicação do grafo) | S | mesmo arquivo |

### P1 — Histórico útil

| ID | Item | Esforço | Arquivos |
|---|---|---|---|
| T020 | **Abrir conversa carrega mensagens** (hoje não há fetch) | S | [apps/web/src/features/history](../../apps/web/src/features/history), [src/app/api/conversations.py](../../src/app/api/conversations.py) |
| T021 | **`last_message_preview` populado no insert** | S | [src/app/db/repo.py](../../src/app/db/repo.py) |
| T022 | **Markdown no render da bolha do agente** | S | ChatPage |

### P2 — Correções direcionais

| ID | Item | Esforço | Arquivos |
|---|---|---|---|
| T030 | **`.env.example` com `admin@getnet.example.com`** (Bug 1) | XS | [.env.example](../../.env.example), [scripts/bootstrap_env.sh](../../scripts/bootstrap_env.sh) |
| T031 | **Nav entre conversas limpa estado ao ir pra `/chat`** | XS | ChatPage |
| T032 | **Guardrail — few-shot pra crediário/produto** (achado B persiste) | S | [src/app/graph/guardrails](../../src/app/graph/guardrails) |
| T033 | **Investigar Knowledge timeout** (Achado A — persiste do smoke) | L (investigação) | [src/app/graph/knowledge](../../src/app/graph/knowledge), [src/app/rag](../../src/app/rag) |
| T034 | **Remover web_search** se não é esperado (visto na Auditoria 01:23:48) | ? | investigar |

### P2 — UX de base

| ID | Item | Esforço | Arquivos |
|---|---|---|---|
| T040 | **Página Privacidade real** (hoje "PrivacyPage / Em construção") | M | [apps/web/src/features/privacy](../../apps/web/src/features/privacy), endpoints LGPD |
| T041 | **Composer fixo no bottom** (padrão de chat) | XS | ChatPage CSS |
| T042 | **Mobile 375px — menu hamburger** | S | layout |
| T043 | **Dark mode** | S | design tokens |

### P3 — Suspeitos (investigar antes)

| ID | Item | Esforço |
|---|---|---|
| T050 | **Confidence sempre 1.0** — hardcoded? | XS para checar |
| T051 | **Dois admins (`admin@getnet.local` + `.example.com`)** — limpar | XS |
| T052 | **E-mail Hotmail pessoal na tela de Contas** — remover do seed/UI | XS |
| T053 | **"Vendas de ontem" respondeu com 1 de outubro** — SEED_REFERENCE_DATE? | XS |

### P3 — Identidade visual

| ID | Item | Esforço |
|---|---|---|
| T060 | **Design system Getnet** (vermelho #EB0A1E, tipografia, voz) | L |
| T061 | **Referências: Linear/Stripe/Perplexity/Intercom/Claude.ai** | L (iteração) |

## Ordem de execução

1. **T001** (SSE CRLF — XS) → desbloqueia todos os testes de UI
2. **T003** + **T030** (fixes XS) → limpa 2 bugs triviais
3. **T002** + **T004** (register + display_name) → novos cadastros funcionam
4. **T010** + **T011** (ciclo HITL) → fecha o fluxo humano
5. **T012** + **T013** (UI SSE handoff + stepper) → UX do multi-agente
6. **T020** + **T021** + **T022** (histórico útil)
7. **T050-T053** (suspeitos — checagens rápidas)
8. P2 UX de base
9. P3 identidade visual (se sobrar tempo)

**Meta P0+P1+P2 limpos**: ~15-20h → merge-ready.

## Critérios de aceite

- Lojista envia pergunta → **vê resposta na tela** (não só no Histórico)
- Lojista cadastra novo e manda primeira mensagem → **sem HTTP 500**
- Operador abre ticket → URL com UUID válido, **envia resposta sem erro**
- Admin em `/v1/chat*` → 403 (não 500)
- `/privacidade` com ações reais (export/delete)
- Mobile 375px navegável
- 10 cenários do enunciado passam pelo navegador (não só pelo curl)
