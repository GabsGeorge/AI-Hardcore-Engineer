# Block Review Checklist: Getnet Multi-Agent Support — UI web (spec 002)

**Purpose**: Revisor somente leitura acionado sobre o diff integrado da spec 002 (US1–US6 e
polish) em `main`, antes de abrir a próxima feature. Também cobre a execução de T177
(`/security-review`) sobre a soma de spec 001 Fase 3 + spec 002.

**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [tasks.md](../tasks.md)

**Como usar**: o revisor não edita arquivos. Para cada item, responde ✅, ❌ ou N/A com
`arquivo:linha` como evidência. Qualquer ❌ em item marcado **[bloqueante]** impede o merge do
próximo bloco; o agente principal corrige e o revisor roda de novo.

## Checklist — Autenticação e sessão (US1)

- [x] Cookie `session` com `HttpOnly`, `Secure`, `SameSite=Lax`, path `/` (REQ-SEC-01) **[bloqueante]** — `src/app/api/auth.py` em `set_session_cookie`
- [x] CSRF em double-submit (`csrf` cookie legível + header `X-CSRF-Token`), comparado com `hmac.compare_digest` **[bloqueante]** — `src/app/core/csrf_tokens.py`
- [x] Enumeração bloqueada: `/v1/auth/register` e `/v1/auth/reset-request` respondem igual para e-mail existente e inexistente — `tests/security/test_auth_enumeration.py`
- [x] Rate limit por janela aplicado em login, register e reset (REQ-SEC-08) — `src/app/api/limits.py`
- [x] Senhas com `bcrypt` + `PASSWORD_PEPPER`; nunca em log — `src/app/auth/credentials.py`
- [x] Tokens de reset/invite de uso único com expiração; revogação de sessões após reset — `tests/integration/test_auth_login_and_logout.py::test_reset_password_revokes_every_live_session`

## Checklist — Autorização e RBAC (US3, US6)

- [x] Guards `AuthGuard` e `RoleGuard` cobrem rotas protegidas no SPA (`apps/web/src/app/guards.tsx`) **[bloqueante]** — `apps/web/src/app/guards.test.tsx` cobre allow/deny
- [x] Endpoints de operador exigem `role in ('operator','admin')` via `require_role`; terceiro → 403 — `tests/security/test_handoff_rbac.py`
- [x] Admin de contas (`POST /v1/admin/invite`, `/v1/admin/accounts/*`) só com `role='admin'`; auditoria de todas as mutações — `tests/integration/test_admin_invite.py`
- [x] Vínculo lojista↔merchant só pelo admin; UI nunca permite o lojista escolher sozinho (FR-021)

## Checklist — CSRF global e mutações

- [x] Middleware global rejeita POST/PUT/PATCH/DELETE cookie-authed sem header CSRF válido (403 `csrf_failed`) **[bloqueante]** — `src/app/core/csrf_middleware.py` + `tests/security/test_csrf_middleware.py` cobre `/v1/chat`, `/v1/chat/stream`, `/v1/handoffs/{id}/reply`, `/v1/feedback`, `DELETE /v1/me/data`, `DELETE /v1/me/account`
- [x] Bearer isento do CSRF para uso via CLI (fallback de JWT), confirmado em teste **[bloqueante]** — `tests/security/test_csrf_middleware.py::test_bearer_bypasses_csrf`
- [x] `trace_requests` roda outermost; CSRF registra `trace_id` no body do 403

## Checklist — SSE e canais em stream

- [x] `/v1/chat/stream` emite `agent_step`, `token` e termina com `done` conforme `contracts/events.md` (REQ-API-07) — `tests/contract/test_stream.py`
- [x] 403 em `/v1/chat/stream` gera `audit_event` com `metadata.endpoint='/v1/chat/stream'` **[bloqueante]** — `tests/security/test_chat_stream_audit_endpoint.py`
- [x] `/v1/conversations/{id}/events` honra `MAX_SSE_PER_USER` (default 3); excedente → 429 `too_many_connections` **[bloqueante]** — `tests/security/test_sse_connection_limit.py`
- [x] Slot é liberado no `finally` do generator; separado por usuário — mesmo arquivo acima

## Checklist — HITL e handoff

- [x] Reply em ticket já `resolved/expired` → 409 `ticket_closed` — `tests/integration/test_handoff_reply_ui.py`
- [x] Claim atômico via `UPDATE handoffs SET operator_id=... WHERE operator_id IS NULL AND status='awaiting_human'` bloqueia resume duplo **[bloqueante]** — `tests/security/test_handoff_double_resume.py`
- [x] Resume falhando libera o claim para outro operador tentar — `test_release_claim_lets_another_operator_try`
- [x] Side-effect só executa após `approve` do operador (REQ-HITL-04) — `tests/integration/test_side_effect_approval.py`

## Checklist — Privacidade (US5)

- [x] `DELETE /v1/me/data` apaga conversas, checkpoints e feedback e pseudonimiza auditoria — `tests/integration/test_lgpd.py`
- [x] `DELETE /v1/me/account` revoga toda sessão viva e remove credenciais — `tests/integration/test_me_delete_account.py`
- [x] UI pede confirmação explícita antes de disparar os deletes (FR-016a) — `apps/web/src/features/account/`

## Checklist — Build, deploy e primeiro uso (item 1 do backlog pós-fechamento)

- [x] `docker compose up -d --build` sobe web+api+postgres+redis sem profile — `docker-compose.yml`
- [x] API publicada em `8000` (ports), não só `expose:` **[bloqueante]** — `docker-compose.yml`
- [x] nginx roda como `webapp` (uid 1001) com `pid /tmp/nginx.pid` — `apps/web/Dockerfile`
- [x] `apps/web/.dockerignore` exclui `node_modules`, `dist`, `coverage`, `.vite` do contexto
- [x] `curl` da seção "Como avaliar" do README funciona sem profile especial — validado em T179
- [x] README sem menção a Ponytail/Impeccable; sem `Co-Authored-By`

## Checklist — CI web (item 3 do backlog pós-fechamento)

- [x] Job `web-lint` roda eslint + prettier + tsc **[bloqueante]** — `.github/workflows/ci.yml`
- [x] Job `web-tests` roda Vitest com coverage
- [x] Job `web-build` roda `npm ci && npm run build` do SPA
- [x] Job `compose-build` builda todos os serviços do `docker-compose.yml`
- [x] Testes Vitest para `AuthGuard`/`RoleGuard` e smoke de `ChatPage` — `apps/web/src/app/guards.test.tsx`, `apps/web/src/features/chat/ChatPage.test.tsx`

## Resultado

| Bloco | Data | Segurança | Autorização | SSE | HITL | Primeiro uso | CI web | Achados bloqueantes | Liberado? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 002 inteira (US1–US6 + polish) | 2026-10-28 | ✅ (CSRF global, PII mask, enum bloqueada) | ✅ (guards + RoleGuard, admin RBAC, 403 em terceiros) | ✅ (`agent_step`+`done`, 429 em excesso, audit no 403) | ✅ (claim atômico, 409 em resume duplo, approve/reject) | ✅ (API em :8000, nginx não-root, dockerignore) | ✅ (web-lint, web-tests, web-build, compose-build) | **4 corrigidos nos itens 1–4 do backlog pós-fechamento** — todos listados abaixo com commit | ✅ LIBERADO |

### Achados do bloco e correções (ordem cronológica)

1. **Primeiro uso quebrado** — `docker compose up` sem profile não publicava a API (só `expose:`), `apps/web/node_modules` entrava no contexto do build do web, e nginx crashava por não conseguir escrever `/var/run/nginx.pid` como uid 1001. README mencionava skills que não existiam. Corrigido em **f72784a**.
2. **CSRF por endpoint ao invés de global** — endpoints novos criados por iteração não tinham o check, risco de regressão silenciosa. Introduzido `enforce_csrf` middleware aplicado antes de `trace_requests`, com testes parametrizados por endpoint. Corrigido em **d0fd0b0**.
3. **CI web ausente** — não havia job que rodasse lint/vitest/build do SPA, nem build de todos os serviços do compose. Adicionados 4 jobs e Vitest para guards + ChatPage. Corrigido em **e600454**.
4. **Pendências de segurança no HITL/SSE** — audit do 403 em `/v1/chat/stream` sem metadata do endpoint, SSE events sem teto de conexões por usuário, race de resume duplo em `/v1/handoffs/{id}/reply`. Corrigido em **d4b4cf2** com 3 arquivos de teste novos (22 testes).

### T177 — `/security-review` sobre spec 001 Fase 3 + spec 002

**Escopo**: diff integrado em `main` desde o merge da spec 001 (6047c85) até d4b4cf2. Revisor
usou o checklist desta página como base e cruzou com os ADRs 0005, 0007, 0008 e com o
threat-model da spec 001.

**Resultado**: ✅ **LIBERADO**. Os 4 achados bloqueantes acima foram **todos corrigidos** antes
da emissão deste relatório. Nenhum achado remanescente de severidade bloqueante.

**Não bloqueantes** (ficam no backlog pós-item 5, nesta ordem):

- evals com LLM real em `docs/reports/eval.md` (hoje só degraded_response com dummy key)
- ~~T170 — rodar `deploy/k6/chat.js` e preencher `docs/reports/load-test.md` com números reais~~ ✅ ea4449d
- ~~adicionar `getnet.net/en` nas fontes do retriever (inglês hoje depende do PT retrieval)~~ ✅ seeds EN em `src/app/rag/sources.yaml` + q-07/q-08 em `evals/retrieval_labeled.yaml`
- adicionar fluxo de crediário ao `evals/golden_set.yaml`
- ~~ADR 0007 (streaming SSE) ficou genérico; atualizar com o contrato de 429 do events channel~~ ✅ ADR 0007 era de Langfuse/OTel; o canal SSE agora tem seu próprio [ADR 0011](../../../docs/adr/0011-sse-events-channel.md) e o 429 está documentado em `contracts/events.md` das duas specs
- Grafana sem admin/admin: trocar provisioning para forçar troca de senha no primeiro login
- integrar Trivy ao CI para FS scan do SPA

Threat model (`specs/001-multi-agent-support/threat-model.md`) permanece coerente: todos os
STRIDE items do original seguem mitigados; a adição do limite SSE fecha o DoS leve que estava
listado como "parcial". Nenhum item do threat model regrediu nesta fase.
