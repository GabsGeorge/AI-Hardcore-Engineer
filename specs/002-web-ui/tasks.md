---
description: "Task list for feature 002 — Interface web do atendimento Getnet"
---

# Tasks: Interface web do atendimento Getnet

**Input**: Design documents em `specs/002-web-ui/` (spec.md, plan.md, research.md,
data-model.md, contracts/, quickstart.md).

**Prerequisites**: feature 001 mergeada em `main` (todos os endpoints `/v1/*` existentes). O
backend não roda só em pytest aqui — a 002 adiciona o SPA, o nginx como proxy único e um
subprojeto `apps/web/`.

**Tests**: obrigatórios (constitution V, FR-030, SC-006). Tudo marcado `[X]` só quando o teste
correspondente passar.

**Organization**: tarefas agrupadas por história para entrega incremental; a 001 provou que o
caminho feliz é concluir fase 1 (setup) + fase 2 (foundational) e depois rodar US1/US2/US3 em
paralelo em worktrees separadas.

## Format: `[ID] [P?] [Story] Descrição [REQ-IDs]`

- **[P]**: pode rodar em paralelo com outras `[P]` do mesmo bloco (arquivos diferentes).
- **[Story]**: a qual história a tarefa pertence (US1–US6; vazio para setup/foundational/polish).
- Cada tarefa cita arquivos reais do repositório.

## Convenções de caminho

- Backend: [src/app/](../../src/app/) (existente). Migrações em
  [src/app/db/migrations/](../../src/app/db/migrations/).
- Frontend: `apps/web/` (criado nesta feature).
- Testes de backend: [tests/](../../tests/).
- Testes do frontend: `apps/web/src/**/__tests__/` (Vitest) e `apps/web/e2e/` (Playwright).
- Observabilidade e deploy: [deploy/](../../deploy/).

## Defaults aceitos para começar (podem mudar na US1 sem retrabalho)

- **Fonte**: Inter (open-source, pilha de fallback nativa). Troca de fonte depois é um
  `tokens.ts` + `tailwind.config.ts`.
- **Logotipo**: baixado da Getnet
  (`site.getnet.com.br/wp-content/uploads/2021/08/logo-getnet.png`), gravado uma única vez em
  `apps/web/public/brand/logo-getnet.png` e referenciado por `<img src="/brand/logo-getnet.png">`.
- **Admin de dev**: `admin@getnet.local` com senha definida em `.env` (ADMIN_SEED_PASSWORD).

---

## Phase 1: Setup

**Purpose**: subprojeto `apps/web`, nginx, Mailpit, variáveis de ambiente, pre-commit do
frontend.

- [ ] T001 Criar o scaffold `apps/web/` com `package.json`, `tsconfig.json`, `vite.config.ts`,
      `index.html` e `src/main.tsx` (React 18 + Vite 5 + TS strict). ESLint com
      `@typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-jsx-a11y` e
      `eslint-plugin-tailwindcss`.
- [ ] T002 [P] Criar `apps/web/Dockerfile` (multi-stage: `node:22-alpine` build →
      `nginx:1.27-alpine` runtime, usuário não-root, HEALTHCHECK em `/healthz`). Copiar
      `dist/` para `/usr/share/nginx/html`.
- [ ] T003 [P] Criar [deploy/nginx/default.conf](../../deploy/nginx/default.conf) servindo o
      SPA, com `proxy_pass` para `api:8000`, `proxy_buffering off` nas rotas
      `/v1/chat/stream` e `/v1/conversations/*/events`, cabeçalho `X-Accel-Buffering: no` e
      `try_files $uri /index.html` como rota curinga.
- [ ] T004 Atualizar [docker-compose.yml](../../docker-compose.yml): adicionar serviço `web`
      (expõe `80:80` e troca a publicação da porta `8000` do `api` por `expose`), serviço
      `mailpit` (`axllent/mailpit:latest`, portas internas 1025 SMTP e 8025 HTTP). O `api`
      ganha `SMTP_URL`, `SESSION_SECRET`, `PASSWORD_PEPPER` do `.env`.
- [ ] T005 [P] Estender [.env.example](../../.env.example) com `SESSION_SECRET`,
      `PASSWORD_PEPPER`, `SMTP_URL=smtp://mailpit:1025`, `WEB_BASE_URL=http://localhost`,
      `ADMIN_SEED_EMAIL=admin@getnet.local`, `ADMIN_SEED_PASSWORD=` (vazio no exemplo).
- [ ] T006 [P] Atualizar [.gitignore](../../.gitignore) e `apps/web/.gitignore` para
      `apps/web/node_modules/`, `apps/web/dist/`, `apps/web/playwright-report/`,
      `apps/web/test-results/`. Idem [.dockerignore](../../.dockerignore).
- [ ] T007 [P] Adicionar hooks de pre-commit do frontend (prettier + eslint sobre
      `apps/web/src`) em [.pre-commit-config.yaml](../../.pre-commit-config.yaml) rodando
      via `docker compose` (sem Node no host).
- [ ] T008 Baixar `logo-getnet.png` do site da Getnet uma única vez para
      `apps/web/public/brand/logo-getnet.png` (binário pequeno; comita como asset da demo com
      atribuição no NOTICE).
- [ ] T009 Criar `apps/web/NOTICE.md` registrando que o logotipo da Getnet é usado só nesta
      demonstração e que Inter é distribuída sob OFL.

**Checkpoint**: `docker compose up -d --build` sobe api, postgres, redis, web e mailpit;
`curl -I http://localhost` responde 200.

---

## Phase 2: Foundational (bloqueia todas as US)

**Purpose**: migração 0002, módulo `auth/`, mailer, Impeccable `PRODUCT.md` e `DESIGN.md`
antes de qualquer tela.

### Backend (auth + mailer)

- [ ] T010 Criar [src/app/db/migrations/0002_auth.sql](../../src/app/db/migrations/0002_auth.sql)
      com `auth_accounts`, `auth_credentials`, `auth_sessions`, `auth_one_time_tokens`,
      `auth_login_attempts` e a coluna `merchants.account_id text UNIQUE` conforme
      [data-model.md](data-model.md).
- [ ] T011 [P] Criar `src/app/auth/passwords.py`: argon2id (`argon2-cffi`) com
      `PASSWORD_PEPPER` e lista local de senhas vazadas (SHA1 prefix, 10 000 entradas,
      baixada no build via `scripts/fetch-pwned-top.py`). Função `verify(hash, raw) -> bool`
      resistente a timing.
- [ ] T012 [P] Criar `src/app/auth/sessions.py`: emissão (`issue(account_id, role) -> (jwt,
      jti)`), validação (`current_session(cookie) -> Session`), revogação por `jti` e por
      `account_id`. `last_seen_at` é atualizado por middleware em toda requisição autenticada.
- [ ] T013 [P] Criar `src/app/auth/csrf.py`: geração de cookie `csrf` (32 bytes b64url) e
      verificação do header `X-CSRF-Token` em toda rota mutante.
- [ ] T014 [P] Criar `src/app/auth/one_time_tokens.py`: `mint(purpose, account_id,
      expires_in) -> (raw, hash)`, `consume(raw) -> account_id | None` (marca `used_at` na
      mesma transação da ação).
- [ ] T015 [P] Criar `src/app/auth/login_rate.py`: contadores em Redis por e-mail e por IP
      (janela fixa 15 min, `shortcut:` documentado); `check(email, ip) -> Decision` devolve
      `allow | locked | rate_limited`.
- [ ] T016 [P] Criar `src/app/ops/mailer.py`: `aiosmtplib`; funções `send_verification`,
      `send_reset`, `send_invite`. Templates em `src/app/ops/mail_templates/<name>.{pt,en}.html`
      com placeholders seguros. Falha de envio é logada e nunca propaga 5xx.
- [ ] T017 Atualizar [src/app/api/auth.py](../../src/app/api/auth.py): adicionar middleware de
      cookie de sessão coexistindo com o `Authorization: Bearer` legado (seed 001 continua
      funcionando). `current_user` passa a aceitar os dois.
- [ ] T018 Estender `src/app/ops/scheduler.py` com `expire_auth_tokens` (varre
      `auth_one_time_tokens` e `auth_sessions` revogadas há mais de 7 dias) e documentar na
      docstring da função que o expurgo roda no mesmo tick de retenção.
- [ ] T019 Criar `src/app/db/repo_auth.py` com os helpers de auth\_\*: `create_account`,
      `get_account_by_email`, `set_password`, `activate_account`, `deactivate_account`,
      `link_merchant`, `unlink_merchant`, `list_accounts`, `list_sessions`,
      `revoke_sessions_of_account`, `delete_account_cascade` (transação completa de FR-016a).

### Testes de infraestrutura

- [ ] T020 [P] `tests/unit/test_auth_passwords.py`: hash é diferente a cada chamada; verify
      bate; verify de senha vazada é bloqueado antes do hash. [REQ-SEC-01]
- [ ] T021 [P] `tests/unit/test_auth_sessions.py`: cookie emitido tem `HttpOnly`, `SameSite=Lax`,
      `Max-Age=43200`; sessão expira após 30 min sem uso; revogação individual e em massa.
      [FR-007, FR-008]
- [ ] T022 [P] `tests/unit/test_auth_csrf.py`: mutante sem `X-CSRF-Token` → 403; com token
      correto → prossegue; token rotaciona no login e no reset. [FR-008]
- [ ] T023 [P] `tests/unit/test_auth_one_time_tokens.py`: expira após prazo; uso duplo falha;
      hash não é reversível a partir do banco. [FR-002, FR-006]
- [ ] T024 [P] `tests/unit/test_login_rate.py`: 5 falhas por conta → 15 min bloqueio; 20
      falhas por IP → 429 com `Retry-After`. [FR-005]
- [ ] T025 [P] `tests/unit/test_mailer.py`: templates renderizam PT e EN; falha SMTP é logada
      e retorna normal; corpo não contém senha nem hash. [FR-002a]

### Impeccable (bloqueia QUALQUER tela)

- [ ] T026 Executar `.claude/skills/impeccable/scripts/impeccable.cmd context --target
      apps/web/src/features/auth/LoginPage.tsx` para iniciar o fluxo e, em seguida, rodar
      `/impeccable init`. Produto: `apps/web/PRODUCT.md` com os campos obrigatórios do
      schema do Impeccable, registrando lojista/operador/admin como audiências, as 6
      histórias como jobs principais e o commitment de marca (logo da Getnet, Inter como
      fonte substituta documentada).
- [ ] T027 Executar `/impeccable new-work --mode operate` para a direção visual.
      Produto: `apps/web/DESIGN.md` com paleta (vermelho `#EC0000`, textos `#282828`,
      cinzas `#454C52`/`#66707A`/`#E1E6EB`/`#F5F7FA`), escala tipográfica (Inter 400/600/700),
      espaços (4/8/16/24/32), raios (8 px), elevações (sombras `0 1px 2px rgba(0,0,0,.08)`
      e `0 8px 24px rgba(0,0,0,.12)`), estados (foco, hover, disabled, erro), estados do
      chat (digitando, aguardando, respondido) e grade do operador. Nada de pixel sketch do
      site da Getnet; a decisão fica registrada em DESIGN.md como "redesign limitado".
- [ ] T028 Criar `apps/web/src/design/tokens.ts` espelhando DESIGN.md e
      `apps/web/src/design/tailwind.generated.css` gerado por
      `apps/web/scripts/tokens-to-tailwind.ts`. O `tailwind.config.ts` lê somente do
      `tokens.ts`; `features/**` MUST NOT importar classes de cor cruas (ESLint rule).
- [ ] T029 [P] Design system — componentes mínimos em `apps/web/src/design/`:
      `Button.tsx`, `Input.tsx`, `PasswordInput.tsx`, `Label.tsx`, `FormField.tsx`,
      `Card.tsx`, `Dialog.tsx`, `Toast.tsx`, `EmptyState.tsx`, `Spinner.tsx`,
      `LiveRegion.tsx` (anuncia SSE para leitores de tela), `Icon.tsx`, `Avatar.tsx`,
      `Logo.tsx` (usa `/brand/logo-getnet.png`).
- [ ] T030 [P] `apps/web/src/lib/api.ts`: `fetch` com `credentials: "include"`, injeção
      automática do header `X-CSRF-Token` lido do cookie em mutantes, mapeamento de
      `{error:{code,message}}` para `ApiError` tipada, tratamento de 401 (redireciona para
      `/login`).
- [ ] T031 [P] `apps/web/src/lib/sse.ts`: cliente `EventSource` com reconexão exponencial
      (backoff cap 10 s), desduplicação por `(event, payload.trace_id | payload.ticket_id)`,
      cancelamento com `AbortController`.
- [ ] T032 [P] `apps/web/src/lib/i18n.ts`: `react-i18next` com dicionários PT/EN em
      `apps/web/src/i18n/{pt,en}.json`.
- [ ] T033 Layout base: `apps/web/src/app/layout.tsx` (header com logo, menu por papel,
      indicador de sessão), `apps/web/src/app/routes.tsx` com `createBrowserRouter`,
      `apps/web/src/app/guards.tsx` com `AuthGuard` e `RoleGuard` (buscam
      `GET /v1/auth/me` uma vez por sessão com TanStack Query).
- [ ] T034 [P] Script de seed de admin: `scripts/create_demo_admin.py` que lê
      `ADMIN_SEED_EMAIL`/`ADMIN_SEED_PASSWORD` do `.env` e cria/atualiza o admin em dev; falha
      explícita se `APP_ENV=production`. Documentado no quickstart.
- [ ] T035 [P] Testes de observabilidade do backend: `getnet_auth_login_total{outcome}`,
      `getnet_sessions_active`, spans `auth.login` e `auth.send_email`. Teste em
      `tests/integration/test_auth_metrics.py`.

**Checkpoint**: migração roda; a login/CSRF/mailer existem com cobertura; PRODUCT.md e
DESIGN.md congelam o visual; design system está pronto para ser consumido.

---

## Phase 3: User Story 1 — Cadastro, login e saída (P1) 🎯 MVP

**Goal**: lojista cria conta por autocadastro, confirma e-mail, entra, sai.

**Independent Test**: `apps/web/e2e/01-register-login.spec.ts` roda contra Mailpit, cadastra
`demo@loja.local`, abre o link, loga e sai; retorno à `/chat` sem sessão redireciona para
`/login`.

### Testes (escrever primeiro, devem falhar)

- [ ] T036 [P] [US1] Contract test de `auth.yaml`: `tests/contract/test_auth_api.py` com
      schemathesis sobre `/v1/auth/*` (apenas códigos ≥ 400 na suíte rápida; a sweep
      profunda roda no job `schema` da CI). [REQ-API-02]
- [ ] T037 [P] [US1] Integração: `tests/integration/test_auth_register_flow.py` — cadastro
      com e-mail novo retorna GenericPending e Mailpit tem 1 mensagem; cadastro com e-mail já
      existente retorna GenericPending **sem** adicionar mensagem no Mailpit (sem
      enumeração). [FR-001, FR-004]
- [ ] T038 [P] [US1] Integração: `tests/integration/test_auth_verify.py` — token válido
      ativa; token usado dá 410; token expirado dá 410. [FR-002]
- [ ] T039 [P] [US1] Integração: `tests/integration/test_auth_login.py` — cookie session +
      csrf voltam; sessão aparece em `/v1/auth/sessions`; logout limpa cookies e revoga.
      [FR-007, FR-008]
- [ ] T040 [P] [US1] Integração: `tests/integration/test_auth_reset.py` — reset troca a senha,
      revoga **todas** as sessões, mesmo link não serve de novo. [FR-006]
- [ ] T041 [P] [US1] Segurança: `tests/security/test_auth_enumeration.py` — tempo de resposta
      não vaza existência (medir em 50 chamadas; p95 do existente / p95 do inexistente < 1,2);
      mensagens idênticas. [FR-004]
- [ ] T042 [P] [US1] Playwright: `apps/web/e2e/01-register-login.spec.ts` — fluxo completo
      com Mailpit API. [FR-030]
- [ ] T043 [P] [US1] a11y automático em login/register/verify com `axe-core` dentro do
      Playwright: zero violações sérias ou críticas. [FR-027, SC-005]

### Implementação backend

- [ ] T044 [US1] Endpoints em `src/app/api/auth.py`: `POST /v1/auth/register`,
      `POST /v1/auth/verify-email`, `POST /v1/auth/login`, `POST /v1/auth/logout`,
      `POST /v1/auth/password/reset-request`, `POST /v1/auth/password/reset`,
      `GET /v1/auth/me`, `GET /v1/auth/sessions`, `DELETE /v1/auth/sessions`
      conforme [contracts/auth.yaml](contracts/auth.yaml).
- [ ] T045 [US1] Auditoria: cada evento de conta (`account_registered`, `email_verified`,
      `login_ok`, `login_failed`, `login_locked`, `logout`, `password_reset_requested`,
      `password_reset_completed`) grava em `audit_events` sem senha nem e-mail em claro.
      [FR-025, REQ-SEC-07]

### Implementação frontend

- [ ] T046 [P] [US1] `apps/web/src/features/auth/LoginPage.tsx` com `Button`, `Input`,
      `FormField`; validação Zod no cliente; chamada a `/v1/auth/login`; mensagens genéricas;
      autoFocus no e-mail; "esqueci minha senha".
- [ ] T047 [P] [US1] `apps/web/src/features/auth/RegisterPage.tsx` — mostra barra de força da
      senha (não bloqueia, só orienta), força comprimento mínimo, bloqueia senhas vazadas na
      submissão (reusa a lista do backend via `GET /v1/auth/password/policy`).
- [ ] T048 [P] [US1] `apps/web/src/features/auth/VerifyEmailPage.tsx` consome `?token=`,
      chama `POST /v1/auth/verify-email`, redireciona para `/login` com toast de sucesso.
- [ ] T049 [P] [US1] `apps/web/src/features/auth/ResetRequestPage.tsx` e
      `ResetPasswordPage.tsx` com os mesmos padrões; mensagens genéricas sempre.
- [ ] T050 [US1] Guards: `AuthGuard` redireciona para `/login?next=...`; sair limpa cache do
      TanStack Query e invalida o cookie.

**Checkpoint US1**: cadastrar → confirmar → logar → sair funciona do navegador; o
Playwright passa; auditoria registra tudo.

---

## Phase 4: User Story 2 — Chat com fontes e handoff visível (P1)

**Goal**: lojista conversa com o atendimento vendo etapas, resposta, fontes, e status do
chamado humano em tempo real.

**Independent Test**: `apps/web/e2e/02-chat.spec.ts` — logar como lojista, perguntar
"Como funciona a antecipação?", conferir pelo menos uma `agent_step`, resposta final e uma
fonte com link; perguntar "quero falar com um humano" e ver o status mudar.

### Testes

- [ ] T051 [P] [US2] Backend extensão: `tests/contract/test_me_conversations.py` para
      `GET /v1/me/conversations` (paginado por cursor). [FR-014, REQ-API-02]
- [ ] T052 [P] [US2] Backend extensão: `tests/contract/test_events_delta.py` — eventos
      `sla_breached` e `handoff_expired` surgem no canal de eventos quando o scheduler
      detecta vencimento. [REQ-API-07, FR-011]
- [ ] T053 [P] [US2] `apps/web/src/features/chat/__tests__/ChatPage.test.tsx` (Vitest+RTL):
      ordem das etapas, resposta final, fontes clicáveis, estado "aguardando atendente".
- [ ] T054 [P] [US2] Playwright `apps/web/e2e/02-chat.spec.ts` cobre o cenário completo.
      [FR-010, FR-011]
- [ ] T055 [P] [US2] XSS: `tests/security/test_chat_render.py` — resposta do grafo contendo
      `<script>` chega ao front como texto (`textContent` igual ao original; `innerHTML` do
      container de mensagens não ganha novas tags). [FR-012]
- [ ] T056 [P] [US2] Streaming: `tests/integration/test_chat_stream_mergeback.py` — refaz a
      sessão (dropa `EventSource`), reconecta, confere que não há mensagem duplicada
      (dedup por `trace_id`). [FR-013]

### Implementação backend

- [ ] T057 [US2] Endpoint `GET /v1/me/conversations` em `src/app/api/me.py` conforme
      [contracts/me.yaml](contracts/me.yaml), ordenado por `last_activity_at DESC`, com
      `last_message_preview` já mascarado (`_scrub`). [FR-014, REQ-GR-02]
- [ ] T058 [US2] Em `src/app/ops/scheduler.py`: ao detectar SLA estourado para um ticket
      aberto, publica `sla_breached` no stream da conversa (lista de "observers" em Redis).
      Ao expirar o ticket, publica `handoff_expired` após emitir o `final_message`.
- [ ] T059 [US2] `src/app/api/conversations.py` passa a emitir `sla_breached` e
      `handoff_expired` quando `/v1/conversations/{id}/events` detecta o estado via DB (sem
      depender de pub/sub externo — polling de 1 s suficiente para o volume).

### Implementação frontend

- [ ] T060 [P] [US2] `apps/web/src/features/chat/ChatPage.tsx` — layout dividido (lista de
      conversas opcional, janela de chat, painel de fontes); input com atalho `Enter`,
      sanitização de texto; preserva texto em caso de 429 (toast + contador do
      `Retry-After`).
- [ ] T061 [P] [US2] `apps/web/src/features/chat/MessageList.tsx` — renderiza eventos SSE em
      ordem; componente separado `AgentStepBadge` para cada etapa; mensagens do assistente
      marcadas com `aria-live="polite"` via `LiveRegion`.
- [ ] T062 [P] [US2] `apps/web/src/features/chat/SourceList.tsx` — fontes com título, link
      (abrir em nova aba, `rel="noopener"`) e data de consulta.
- [ ] T063 [P] [US2] `apps/web/src/features/chat/HandoffBanner.tsx` — mostra estado
      (aguardando, SLA estourado, respondido, expirado), com ticker local de prazo quando
      aguardando.
- [ ] T064 [P] [US2] i18n: todas as strings de chat vêm de `i18n/{pt,en}.json`.
- [ ] T065 [US2] Integração com `/v1/conversations/{id}/events` para `handoff_update`,
      `final_message`, `sla_breached` e `handoff_expired`.

**Checkpoint US2**: Playwright passa; mensagens contendo HTML vão como texto; a conversa
reflete o chamado humano em até 5 s.

---

## Phase 5: User Story 3 — Operador atende a fila (P1)

**Goal**: operador vê a fila ordenada, abre, responde, aprova/rejeita ação pendente.

**Independent Test**: `apps/web/e2e/03-handoff.spec.ts` — lojista pede humano; operador abre
a fila (ticket aparece no topo), responde "Resolvido"; lojista recebe a resposta.

### Testes

- [ ] T066 [P] [US3] Contract: `tests/contract/test_handoffs_sort.py` — fila ordenada por
      `(priority DESC, created_at ASC)`; filtro por status; cursor estável. [FR-017]
- [ ] T067 [P] [US3] Integração: `tests/integration/test_handoff_reply_ui.py` — ação pendente
      sem `action_decision` → 422; `approve` → status `resolved` e `pending_action.decision =
      approved`. (regressão da correção 4 do audit; FR-018)
- [ ] T068 [P] [US3] RBAC: `tests/security/test_handoff_rbac.py` — lojista acessando
      `/v1/handoffs` recebe 403 `forbidden_role`. [FR-024, REQ-SEC-06]
- [ ] T069 [P] [US3] Playwright `apps/web/e2e/03-handoff.spec.ts`. [FR-030]

### Implementação

- [ ] T070 [US3] `apps/web/src/features/handoffs/QueuePage.tsx` com `useQuery` de 30 s
      refetch; agrupamento visual por prioridade; selo "SLA estourado" quando prazo passou.
- [ ] T071 [P] [US3] `apps/web/src/features/handoffs/TicketPage.tsx` com resumo, contexto,
      ação pendente e `ActionDecisionField` (radio approve/reject) quando `pending_action`
      existe.
- [ ] T072 [P] [US3] Guards de operador reutilizando `RoleGuard(["operator","admin"])`.
- [ ] T073 [US3] Toasts: "chamado já encerrado" quando a resposta vem 409.

**Checkpoint US3**: operador fecha chamado em até 4 interações (SC-003).

---

## Phase 6: User Story 4 — Histórico de conversas (P2)

**Goal**: lojista lista as próprias conversas, reabre, continua.

**Independent Test**: criar duas conversas, sair, entrar, reabrir a primeira com mensagens
preservadas.

### Testes

- [ ] T074 [P] [US4] Integração: `tests/integration/test_me_conversations_isolation.py` —
      conversa de `cliente2024` não aparece para `cliente1988`. [FR-014]
- [ ] T075 [P] [US4] Playwright `apps/web/e2e/04-rbac.spec.ts` cobre também a tentativa de
      abrir `/me/conversations` sem sessão → `/login`.

### Implementação

- [ ] T076 [US4] `apps/web/src/features/conversations/ConversationsPage.tsx` — lista
      paginada por cursor, carregando a prévia e o status do chamado. Estado vazio com
      ilustração do design system.
- [ ] T077 [US4] Link direto para `/chat/:id` reabrindo a conversa com o estado do
      checkpoint.

---

## Phase 7: User Story 5 — Privacidade (apagar conversas / excluir conta) (P2)

**Goal**: lojista pode apagar só as conversas (sessão permanece) ou excluir a conta
(sessão cai, e-mail livre para novo cadastro).

**Independent Test**: `apps/web/e2e/05-privacy.spec.ts` — apagar conversas e conferir
histórico vazio; excluir conta e conferir login genérico.

### Testes

- [ ] T078 [P] [US5] Backend: `tests/integration/test_me_delete_account.py` — DELETE
      `/v1/me/account` sem senha → 401; com senha → apaga `auth_accounts`, revoga sessões,
      desvincula merchant; `audit_events.actor_id` fica pseudonimizado; novo cadastro com o
      mesmo e-mail funciona. [FR-016a, REQ-SEC-09]
- [ ] T079 [P] [US5] Backend regressão: `tests/integration/test_me_delete_data.py`
      continua apagando checkpoints (correções 2 e 3 do audit da 001; não quebrou com a
      camada nova).
- [ ] T080 [P] [US5] Playwright `apps/web/e2e/05-privacy.spec.ts`.

### Implementação

- [ ] T081 [US5] Endpoint `DELETE /v1/me/account` em `src/app/api/me.py` conforme
      [contracts/me.yaml](contracts/me.yaml): valida senha pelo mesmo caminho do login
      (sem revelar erro específico), executa `repo_auth.delete_account_cascade`, limpa
      cookies com `Max-Age=0`.
- [ ] T082 [US5] `apps/web/src/features/privacy/PrivacyPage.tsx` com duas seções
      ("Apagar minhas conversas" e "Excluir minha conta") separadas visualmente; cada ação
      exige confirmação digitada e, para excluir conta, a senha atual. Resumo final mostra
      o que foi apagado e o que ficou (auditoria pseudonimizada, estabelecimento preservado).

---

## Phase 8: User Story 6 — Admin (P2)

**Goal**: admin convida operadores/admins, vincula lojista a merchant, desativa contas,
acompanha fila e auditoria.

**Independent Test**: `apps/web/e2e/06-admin.spec.ts` — admin convida operador, operador
termina o cadastro pelo link, admin desativa a conta, operador recebe acesso negado na
próxima ação.

### Testes

- [ ] T083 [P] [US6] Contract: `tests/contract/test_admin_api.py` cobrindo os 6 endpoints
      de [contracts/admin.yaml](contracts/admin.yaml). [REQ-API-02]
- [ ] T084 [P] [US6] RBAC: `tests/security/test_admin_rbac.py` — operador acessando
      `/v1/admin/*` → 403 `forbidden_role`; lojista idem. [FR-024]
- [ ] T085 [P] [US6] Vínculo: `tests/integration/test_admin_link_merchant.py` — segundo
      vínculo no mesmo merchant → 409 (constraint UNIQUE); desvínculo funciona; o atendimento
      passa a responder com os dados do merchant após o vínculo. [FR-021]
- [ ] T086 [P] [US6] Convite: `tests/integration/test_admin_invite.py` — e-mail chega no
      Mailpit; link define a senha; conta nasce `active`. [FR-020]
- [ ] T087 [P] [US6] Auditoria sem PII: `tests/security/test_admin_audit_no_pii.py` —
      resposta de `/v1/admin/audit` não contém e-mail bruto nem CPF/CNPJ. [FR-023, REQ-SEC-07]
- [ ] T088 [P] [US6] Playwright `apps/web/e2e/06-admin.spec.ts`.

### Implementação backend

- [ ] T089 [US6] Novo módulo `src/app/api/admin.py` registrando os endpoints de
      [contracts/admin.yaml](contracts/admin.yaml) com `require_role("admin")`.
- [ ] T090 [US6] Convite gera `one_time_token(purpose="invite")`; endpoint público
      `POST /v1/auth/invites/{token}/accept` define nome e senha e marca a conta como
      `active`.
- [ ] T091 [US6] `scheduler.py` passa a desativar contas via trigger externo (desativação
      imediata derruba sessões; não há atraso).

### Implementação frontend

- [ ] T092 [P] [US6] `apps/web/src/features/admin/AccountsPage.tsx` — lista, filtro por
      papel e status, "Convidar operador/admin" (dialog com nome, e-mail e papel).
- [ ] T093 [P] [US6] `MerchantLinkPage.tsx` — campo de busca de merchant, de-conta,
      confirmação; aviso quando merchant já tem conta.
- [ ] T094 [P] [US6] `QueueOverviewPage.tsx` — números do dia, link para a fila do operador
      (mesma rota, visível para admin também).
- [ ] T095 [P] [US6] `AuditPage.tsx` — tabela com filtro por `action` e `since`; coluna
      `actor_id` mostra "lojista pseudonimizado" quando `deleted:...`.
- [ ] T096 [P] [US6] `apps/web/src/features/auth/AcceptInvitePage.tsx` para o fluxo de
      convite (mesmo padrão de "resetar senha").

**Checkpoint**: todas as 6 histórias passam seus Playwrights.

---

## Phase 9: Polish e integrações finais

**Purpose**: fechar as pontas que atravessam várias histórias.

- [ ] T097 [P] README root: seção "UI web" com GIF curto de cada história, atualizando a
      seção "Como executar" com `docker compose up` que agora inclui `web` e `mailpit`.
      Linka `apps/web/PRODUCT.md` e `apps/web/DESIGN.md`. [REQ-INF-06]
- [ ] T098 [P] Observabilidade: dashboard "UI" novo em
      [deploy/grafana/dashboards/ui.json](../../deploy/grafana/dashboards/ui.json) com
      taxa de login por outcome, sessões ativas, tempo mediano do SSE.
- [ ] T099 Rodar `/impeccable detect` sobre todas as telas (mandatório na skill):
      `apps/web/scripts/impeccable detect --json apps/web/src/features/**/*.tsx`. Resolver
      todos os findings de nível must/should.
- [ ] T100 [P] Visual regression: `apps/web/e2e/visual.spec.ts` captura cada tela em desktop
      e mobile; rodadas futuras falham se qualquer pixel mudar sem rebase.
- [ ] T101 Rodar `/code-review` sobre o diff completo da 002; aplicar findings "must fix".
- [ ] T102 Rodar `/security-review` especificamente sobre `src/app/auth/` e `src/app/api/
      {auth,me,admin}.py`; aplicar findings.
- [ ] T103 Atualizar o workflow do CI
      ([.github/workflows/ci.yml](../../.github/workflows/ci.yml)) com os jobs novos:
      `web-tests` (Vitest), `web-lint` (ESLint), `web-e2e` (Playwright+Mailpit, rede
      interna), `web-a11y` (axe-core sobre os componentes).
- [ ] T104 `tests/test_no_stubs.py` passa a procurar `// STUB(` em `apps/web/src/` também.
- [ ] T105 Validar `specs/002-web-ui/quickstart.md` do zero num clone limpo (igual ao T179
      da 001).

**Checkpoint final**: `/code-review ultra` do PR passa; `/security-review` sem findings
críticos; CI verde em todos os jobs.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Fase 1)**: nada. 1 agente, sequencial.
- **Foundational (Fase 2)**: Setup. 1 agente até T025; **T026/T027 (Impeccable) são
  bloqueantes para QUALQUER tela** — nada de `features/**` começa antes deles. T028–T035 em
  seguida, podem ter até 3 agentes em paralelo (`[P]`).
- **US1 (P1)**: Foundational completa (incluindo DESIGN.md).
- **US2 (P1)**: Foundational completa; integra com US1 pelo cookie de sessão, mas é
  testável sozinha com um login programático de teste.
- **US3 (P1)**: Foundational completa; teste depende de ter um ticket (fixture backend
  cria).
- **US4, US5, US6 (P2)**: dependem só de Foundational.

### Dentro de cada US

- Testes antes da implementação (falhando) → código mínimo que faz passar → integração.
- Backend antes do frontend quando o endpoint é novo (US1 contratos, US5 delete-account,
  US6 admin).

### Parallelismo

- Na Fase 2, após T026/T027: T028, T029, T030, T031, T032, T034, T035 em paralelo em até 3
  agentes.
- Depois da Fase 2: 3 agentes em worktrees paralelas, uma para cada P1 (US1, US2, US3). O
  design system está congelado; qualquer componente novo é escalado para o agente principal.
- As US P2 (4, 5, 6) seguem o mesmo padrão em outra rodada; US6 pode exigir dependência
  leve de US1 (convite usa o fluxo de confirmação).

---

## Parallel Example — US1

```bash
# Testes (todos [P]):
Task: "tests/contract/test_auth_api.py (schemathesis)"
Task: "tests/integration/test_auth_register_flow.py (Mailpit)"
Task: "tests/integration/test_auth_verify.py"
Task: "tests/integration/test_auth_login.py"
Task: "tests/integration/test_auth_reset.py"
Task: "tests/security/test_auth_enumeration.py"
Task: "apps/web/e2e/01-register-login.spec.ts (Playwright)"

# Páginas de autenticação (todos [P]):
Task: "apps/web/src/features/auth/LoginPage.tsx"
Task: "apps/web/src/features/auth/RegisterPage.tsx"
Task: "apps/web/src/features/auth/VerifyEmailPage.tsx"
Task: "apps/web/src/features/auth/ResetRequestPage.tsx + ResetPasswordPage.tsx"
```

---

## Implementation Strategy

### MVP (US1 + US2 + US3)

Com as 3 histórias P1 fechamos o par lojista/operador. O admin de dev é criado via
`scripts/create_demo_admin.py`, então não dependemos da US6 para a demonstração.

1. Setup + Foundational (bloqueante): 1 agente para T001–T019 + T026/T027.
2. T020–T025 em paralelo (até 3 agentes, só testes/mocks de infra).
3. T028–T035 em paralelo (design system, lib, i18n).
4. US1 + US2 + US3 em paralelo (3 worktrees).
5. **Parar e validar**: quickstart manual, Playwright na CI.

### Entrega incremental

1. Setup + Foundational → `main`.
2. US1 → PR → merge → demo.
3. US2 + US3 juntas (operador precisa de lojista perguntando) → PR → merge → demo.
4. US4, US5, US6 em sequência de PRs curtos (cada uma vale uma mini-demo).

### Equipe de 3 agentes paralelos (igual à 001)

1. Juntos até T035 (congela DESIGN.md e design system).
2. A: US1; B: US2; C: US3.
3. Depois: A: US4; B: US5; C: US6.
4. Agente principal integra, roda `/code-review ultra` e abre o PR final.

---

## Notes

- `[P]` significa arquivos distintos sem acoplamento.
- `[Story]` liga a tarefa à história para rastreabilidade REQ → task → teste → commit.
- Cada task vira um ou dois commits do padrão `feat(T0NN): descrição [REQ-...]`.
- Nenhum stub (`// STUB(` em TS, `# STUB(` em Py) pode sobrar na entrega final (T104).
- Tudo roda via `docker compose` (constitution IX): nem Node nem Python no host.
