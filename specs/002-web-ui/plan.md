# Implementation Plan: Interface web do atendimento Getnet

**Branch**: `002-web-ui` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-web-ui/spec.md`

## Summary

A spec pede uma interface web para a API da 001 cobrindo cadastro/login, chat em streaming,
fila do operador, histórico, privacidade e admin. A spec já resolveu as 4 decisões arquiteturais
em `/speckit.clarify`: vínculo com estabelecimento só pelo admin, exclusão de conta separada da
exclusão de conversas, e-mail por SMTP com caixa local de desenvolvimento, e sessão 30 min
inativa / 12 h absoluta sem "lembrar de mim". A abordagem técnica: um SPA React + Vite + TS
servido por nginx no mesmo compose, uma camada de contas e sessão no backend FastAPI (cookie
HttpOnly, SameSite=Lax, CSRF) que não altera a regra de identidade da 001, e Playwright para os
fluxos críticos. A direção visual segue o site da Getnet e é formalizada pelo Impeccable
(`PRODUCT.md` e `DESIGN.md`) antes das telas, como manda o princípio XIII da constituição.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.6 (frontend, strict).

**Primary Dependencies**: FastAPI, LangGraph (reutilizados da 001). Novos no backend: `argon2-cffi`
(hash de senha), `itsdangerous` ou cookies assinados do próprio FastAPI com `python-jose` já
instalado (JWT HS256 reaproveitado), `aiosmtplib` para envio dos links. No frontend: React 18 +
Vite 5 + TypeScript 5, React Router 6, TanStack Query 5, Zod para validação,
`react-i18next` para PT/EN, Tailwind CSS 3 **só como engine utilitária**: as classes são
produzidas pelos tokens do design system definidos em `DESIGN.md` (não há uso de utilitários
brutos nas telas).

**Storage**: Postgres (reutiliza o cluster da 001). Novas tabelas sob prefixo `auth_`:
`auth_accounts`, `auth_credentials`, `auth_sessions`, `auth_one_time_tokens`, `auth_login_attempts`.
O vínculo lojista → estabelecimento vira coluna em `merchants` (`account_id text UNIQUE`).

**Testing**: pytest (contratos novos, segurança, suíte LGPD estendida). Playwright + TypeScript
para E2E dos 4 fluxos críticos (FR-030): cadastro-confirmação-login, chat com fontes, chamado
humano com resposta do operador, controle de acesso por papel. Visual regression com Playwright
screenshots nos componentes do design system.

**Target Platform**: SPA servido por nginx como container do mesmo `docker-compose.yml`. Navegadores:
duas últimas versões de Chrome, Edge, Firefox, Safari (desktop e celular). Largura mínima 360 px.

**Project Type**: Web application. Backend em `src/app/` (existente), frontend em `apps/web/`.

**Performance Goals**: Primeiro byte do SPA < 1 s em rede local; primeira etapa SSE do chat < 1 s
após envio (SC-002); resposta do operador chega ao lojista em até 5 s (SC-002). LCP < 2,5 s em
desktop local, < 4 s em celular simulado 4G.

**Constraints**: Nenhum segredo embarcado no bundle. Nenhum cookie acessível a JavaScript da
página (`HttpOnly`). CSP sem `unsafe-inline` nem `unsafe-eval` em produção. WCAG 2.2 AA (SC-005).
Sem rolagem horizontal a partir de 360 px (SC-007).

**Scale/Scope**: Demonstração: dezenas de lojistas simultâneos (mesma carga da 001), ~15 telas,
4 fluxos E2E, 1 design system com tokens e ~25 componentes.

## Constitution Check

*GATE: deve passar antes da Fase 0 e ser revisto após a Fase 1.*

- **I. Identidade só do servidor** — Pass. A sessão nasce e é validada no servidor; o cookie é
  opaco (JWT HS256 na claim `sub`). O frontend nunca lê o `user_id` para enviar à API — ele vai
  junto no cookie e é extraído pelo `current_user` já existente. Nenhum endpoint novo aceita
  identidade no corpo.
- **II. Segredos** — Pass. Variáveis novas (`SESSION_SECRET`, `SMTP_URL`, `PASSWORD_PEPPER`) em
  `.env.example` vazias; `gitleaks` já roda. O bundle do frontend não contém segredo.
- **III. Fontes** — Pass. A tela mostra as fontes como a 001 já devolve; sem invenção.
- **IV. Menor privilégio** — Pass. Novos endpoints trazem `require_role("merchant")` ou
  `require_role("operator","admin")` já existentes. Sem endpoint "/me" admin ambíguo.
- **V. Todo requisito tem teste** — Pass. Cada FR aparece em um teste; a matriz segue para
  `tasks.md`. `test_no_stubs` vale também para `apps/web/`.
- **VI. Determinismo nos testes** — Pass. Playwright sem rede externa (compose com `internal:true`
  também para o E2E), Mailpit lido direto pela sua API HTTP interna. Sem flakiness por tempo
  humano: usamos `clock.setFixedTime` do Playwright nos testes de SLA.
- **VII. Observável por padrão** — Pass. Novas métricas: `getnet_auth_login_total{outcome=...}`,
  `getnet_sessions_active`. Spans para `auth.login`, `auth.verify_email`, `auth.send_email`.
- **VIII. Falha segura** — Pass. Falha de SMTP não revela se a conta existe (FR-002a). Falha de
  Redis não abre acesso (CSRF cookie fallback já embarcado no token). Erro 500 nunca mostra a
  stack ao usuário.
- **IX. Reprodutível com um comando** — Pass. `docker compose up -d --build` sobe tudo, inclusive
  Mailpit e nginx. Nenhuma dependência local do host.
- **X. LGPD e privacidade** — Pass. FR-016 (apaga conversas) e FR-016a (apaga conta) estendem o
  endpoint existente. A caixa de desenvolvimento não vai para produção.
- **XI. Repositório sem artefatos gerados** — Pass. `apps/web/dist/`, `node_modules/` e
  `apps/web/playwright-report/` entram no `.gitignore` e `.dockerignore`.
- **XII. Simplicidade (Ponytail)** — Pass. Reutilizamos: JWT HS256 e `require_role` existentes;
  pool do Postgres e Redis; o grafo da 001 inteiro, sem mudança. Novo: só o módulo de contas,
  o módulo de e-mail e o pacote `apps/web/`. Sem BFF, sem GraphQL, sem state management externo
  (TanStack Query é cache de servidor, não store).
- **XIII. Excelência de interface (Impeccable)** — Pass **após setup**. A ordem é obrigatória:
  o Impeccable escreve `PRODUCT.md` e `DESIGN.md` **antes** da primeira tela ser codada. Isso
  é a tarefa 1 das fases 2/3.

**Veredito**: todas as portas abertas. O único item condicionado é o XIII, resolvido pela
primeira tarefa da fase de implementação da UI.

## Project Structure

### Documentation (this feature)

```text
specs/002-web-ui/
├── plan.md                 # Este arquivo
├── research.md             # Fase 0 (padrões de cookie de sessão, Playwright+SSE, Mailpit)
├── data-model.md           # Fase 1 (tabelas auth_* + coluna account_id em merchants)
├── quickstart.md           # Fase 1 (como demonstrar as 6 histórias ponta a ponta)
├── contracts/              # Fase 1 (OpenAPI dos endpoints novos; events.md estendido)
│   ├── auth.yaml
│   ├── me.yaml
│   ├── admin.yaml
│   └── events.md
├── checklists/
│   └── requirements.md
└── tasks.md                # Fase 2 (saída de /speckit.tasks)
```

### Source Code (repository root)

```text
src/app/                        # backend existente (001) + módulos novos
├── api/
│   ├── auth.py                 # EXISTENTE: ganha /v1/auth/register, /login, /logout,
│   │                           # /verify-email, /password/reset-request, /password/reset,
│   │                           # /sessions, com cookie de sessão + CSRF
│   ├── me.py                   # EXISTENTE: ganha DELETE /v1/me/account (FR-016a)
│   ├── admin.py                # NOVO: /v1/admin/accounts, /v1/admin/merchants/{id}/link,
│   │                           # /v1/admin/accounts/{id}/activate|deactivate, /v1/admin/queue,
│   │                           # /v1/admin/audit
│   └── chat.py, conversations.py, handoffs.py, health.py (sem alteração estrutural)
├── auth/                       # NOVO: lógica reutilizável de sessão
│   ├── passwords.py            # argon2 + pepper + lista de senhas vazadas (hash local)
│   ├── sessions.py             # emissão/validação/revogação; cookie HttpOnly SameSite=Lax
│   ├── csrf.py                 # double-submit cookie (CSRF token lido do body ou header)
│   ├── one_time_tokens.py      # confirmação, reset, convite
│   └── login_rate.py           # bloqueio por conta e por IP
├── ops/
│   ├── mailer.py               # NOVO: aiosmtplib, templates PT/EN; usa Mailpit no dev
│   └── scheduler.py            # EXISTENTE: ganha expurgo de sessões e tokens expirados
└── db/
    ├── migrations/0002_auth.sql  # NOVO
    └── repo.py                 # EXISTENTE: ganha helpers auth_* e account linkage

apps/web/                       # NOVO: SPA Getnet
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
├── public/                     # logotipo e favicon
├── src/
│   ├── app/                    # rotas e layout
│   │   ├── routes.tsx          # React Router: /login, /register, /verify, /chat, /chat/:id,
│   │   │                       # /handoffs (operator), /admin, /admin/accounts, /admin/queue,
│   │   │                       # /me/privacy, /404
│   │   ├── guards.tsx          # RoleGuard, AuthGuard
│   │   └── layout.tsx
│   ├── design/                 # design system (Impeccable)
│   │   ├── tokens.ts           # cores, tipografia, espaços, raios, elevações
│   │   ├── Button.tsx, Input.tsx, Card.tsx, Dialog.tsx, Toast.tsx, EmptyState.tsx, ...
│   │   └── a11y.tsx            # Live region p/ anúncios de SSE
│   ├── features/
│   │   ├── auth/               # LoginPage, RegisterPage, VerifyPage, ResetRequestPage, ResetPage
│   │   ├── chat/               # ChatPage (SSE), MessageList, SourceList, HandoffBanner
│   │   ├── conversations/      # ConversationsPage (lista do lojista)
│   │   ├── handoffs/           # QueuePage, TicketPage (operador)
│   │   ├── admin/              # AccountsPage, QueueOverviewPage, AuditPage, MerchantLinkPage
│   │   └── privacy/            # PrivacyPage (apaga conversas / excluir conta)
│   ├── lib/
│   │   ├── api.ts              # fetch com credentials + CSRF; mapeia erros tipados
│   │   ├── sse.ts              # cliente SSE que reconecta e desduplica eventos
│   │   └── i18n.ts
│   └── main.tsx
├── e2e/
│   ├── 01-register-login.spec.ts
│   ├── 02-chat.spec.ts
│   ├── 03-handoff.spec.ts
│   └── 04-rbac.spec.ts
└── Dockerfile                  # multi-stage: node:22-alpine build → nginx:1.27-alpine runtime

deploy/nginx/
└── default.conf                # serve o SPA e faz proxy /v1/* para api:8000 (SSE habilitado)

docker-compose.yml              # EXISTENTE: ganha serviços `web` (nginx), `mailpit`
```

**Structure Decision**: dois subprojetos no mesmo repo. O backend fica onde está, e todo o
frontend vive isolado em [apps/web/](apps/web/), com seu próprio Dockerfile e CI. O
`docker-compose.yml` passa a montar o SPA pelo nginx, que também faz o proxy para a API,
mantendo o browser falando com uma única origem (requisito para cookie `SameSite=Lax`).

## Fluxo de uma mensagem (chat do lojista)

```text
browser ─GET /chat/:id──► nginx ──► (SPA; cookie de sessão vai junto)
browser ─POST /v1/chat/stream──► nginx ──► api (001)
         Cookie: session=...
         X-CSRF-Token: ...
api valida cookie → current_user → /v1/chat/stream (já existente)
    emite agent_step / handoff / done como SSE
browser renderiza etapas + resposta + fontes (sem recarregar)
browser abre em paralelo /v1/conversations/{id}/events para final_message e handoff_update
```

## Entrega por prioridade

- **P1 (bloqueio)**: histórias 1, 2, 3 (cadastro-login-saída, chat, operador). Entrega inclui
  design system mínimo (botão, input, card, diálogo, toast, estados vazio/erro/carregando),
  o módulo de contas e sessão, o chat em streaming e a fila do operador.
- **P2 (segue junto)**: histórias 4, 5, 6 (histórico, privacidade, admin). Entrega inclui
  listagem de conversas, as duas ações de privacidade e as telas de admin.
- Edge cases cobertos pelas fases 1 e 2 do design: estados de carregamento, vazio, erro,
  escalonamento humano, prazo estourado.

## Modo de execução (agentes)

Depois do `/speckit.tasks`, uso no máximo 3 subagentes em paralelo (uma worktree por
história de P1), seguindo o padrão da 001. Cada worktree só edita a sua pasta de feature
(`apps/web/src/features/<x>`) e seu contrato (`specs/002-web-ui/contracts/<x>.yaml`). O design
system (`apps/web/src/design/`) é congelado após a tarefa 1 e qualquer novo componente é
decisão do agente principal, nunca de um subagente.

## Responsáveis (equipe de agentes)

- **Backend/segurança**: módulos `auth/`, `ops/mailer.py`, migrações e endpoints novos.
- **Frontend/UX (impeccable)**: `PRODUCT.md`, `DESIGN.md`, design system e telas.
- **QA**: pytest + Playwright + testes de rastreabilidade; a11y automático nas telas.
- **PO**: README, quickstart, demos.
- **Orquestrador (eu)**: setup, integrações entre pastas, revisão por bloco com
  `checklists/block-review.md` reaproveitado da 001.

## Complexity Tracking

> Preenchido só com justificativas; nenhuma violação da constitution até aqui.

| Decisão | Por que | Alternativa simples descartada |
|---|---|---|
| Tabelas `auth_*` separadas em vez de estender `users` | A exclusão de conta precisa remover a pessoa sem apagar o estabelecimento. Separar o quem-tem-login da identidade de domínio evita cascade acidental sobre merchants/handoffs. | Guardar e-mail/senha em `users` falhou porque o FK em cascade de handoffs apagaria chamados históricos de uma conta excluída. |
| nginx como proxy único (mesma origem) em vez de dois domínios + CORS | Cookie `SameSite=Lax` resolve CSRF por padrão quando origem é única; sem CORS, menos superfície. | Dois domínios + `SameSite=None; Secure` + CORS adiciona configuração sem ganho na demo. |
| Tailwind limitado a utilitários expressando tokens | Ganho de velocidade sem rodar um bundler de CSS extra. Os tokens vivem em `tokens.ts` e geram a config do Tailwind. | CSS plano com variáveis puras funcionaria, mas o custo editorial em 25 componentes supera o ganho. |
