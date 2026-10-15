# Research: Interface web do atendimento Getnet

Decisões técnicas que o `/speckit.clarify` não cobriu, pré-requisitos para a Fase 1
(contratos e dados).

---

## 1. Formato da sessão: JWT HS256 em cookie `HttpOnly`

**Decision**: cookie `session` com um JWT HS256 assinado com `SESSION_SECRET` novo. Atributos:
`HttpOnly`, `Secure` em produção, `SameSite=Lax`, `Path=/`, `Max-Age=43200` (12 h teto absoluto).
A claim `sub` traz o `account_id`, `role`, `jti` (ID único por sessão) e `iat`. A tabela
`auth_sessions(jti PRIMARY KEY, account_id, issued_at, last_seen_at, revoked_at, ip, user_agent)`
é consultada em toda requisição: se `revoked_at IS NOT NULL` ou `now() - last_seen_at > 30 min`,
a sessão é tratada como expirada e o cookie é apagado.

**Rationale**: reaproveita o `python-jose` já instalado e o `require_role` existente. Guardar
o `jti` em tabela é o que torna a sessão **revogável** (saída, troca de senha, exclusão,
desativação) — exigência direta do FR-007. O prazo de 30 min sem uso vem do `last_seen_at`
atualizado em toda requisição autenticada; o teto absoluto é o `exp` do próprio token.

**Alternatives considered**:
- *Session cookie opaco com estado puro no banco*: funcionaria, mas obriga lookup em todo
  request. O JWT já carrega `role`, então o lookup serve só para checar revogação e inatividade
  — baixo custo e muito mais flexível.
- *Access + refresh em `localStorage`*: FR-008 proíbe credenciais acessíveis a JavaScript.
  Reprovado.

---

## 2. CSRF: double-submit com token em cookie legível + header

**Decision**: além do `session` HttpOnly, servir um cookie `csrf` com valor aleatório de 32 bytes
em base64url, `SameSite=Lax`, **sem** `HttpOnly` (precisa ser lido pelo JS). Toda chamada
mutante (POST/PUT/PATCH/DELETE) envia esse valor no header `X-CSRF-Token`. O servidor verifica
igualdade estrita; GETs ficam fora porque `SameSite=Lax` já bloqueia requisições cross-site
simples. O cookie CSRF é rotacionado a cada login e em cada troca de senha.

**Rationale**: compatível com SPA, sem necessidade de endpoint `/csrf-token`. Resiliente contra
ataques CSRF clássicos; `SameSite=Lax` é a primeira camada e o header é a segunda.

**Alternatives considered**:
- *Confiar só em `SameSite=Lax`*: insuficiente para navegadores que não respeitam totalmente;
  política aceita, mas defesa em profundidade exige o header.
- *Encrypted token em header, sem cookie*: exige o SPA fazer um fetch inicial de CSRF ao
  carregar a página; adiciona latência sem ganho.

---

## 3. Hash de senha: argon2id + pepper

**Decision**: `argon2-cffi` com perfil `argon2id`, `time_cost=3`, `memory_cost=64 MiB`,
`parallelism=4`, `hash_len=32`. Pepper (`PASSWORD_PEPPER`, 32 bytes aleatórios) concatenado à
senha antes do hash; vive só no `.env`. Senhas são comparadas contra uma lista local das 10 mil
mais comuns (SecLists `common-passwords.txt`, versão com SHA1 prefix para não distribuir texto
em claro; a lista é baixada na build e é tratada como artefato, não vai no repositório).

**Rationale**: argon2id é o padrão OWASP; o pepper protege contra vazamento só do banco (o
atacante precisa do `.env` também). O corte em 10 mil mantém o cadastro rápido (comparação em
memória, sem rede) e cobre o grosso dos ataques.

**Alternatives considered**:
- *bcrypt 12*: ainda é aceito, mas argon2id é a recomendação atual e o custo CPU é controlável.
- *API da HaveIBeenPwned (k-anonymity)*: adiciona dependência de rede; preferimos
  reproduzibilidade total (princípio IX).

---

## 4. Links de uso único: tokens opacos, não JWT

**Decision**: tokens de confirmação, redefinição e convite são 32 bytes aleatórios em base64url.
Guardados como `sha256(token)` em `auth_one_time_tokens(hash PRIMARY KEY, account_id, purpose,
expires_at, used_at)`. Expiração: 24 h para confirmação e convite, 1 h para redefinição. O token
em claro só existe na URL enviada por e-mail; o banco só guarda o hash. Usar o token marca
`used_at`; usar de novo retorna o mesmo erro de "link inválido" (FR-002 enumeration-free).

**Rationale**: JWT para link de uso único é anti-padrão porque não dá para invalidar antes do
`exp`. Guardar hash evita que vazamento do banco permita usar o token.

**Alternatives considered**:
- *JWT com claim `purpose` e `jti`*: exigiria a mesma tabela de revogação; sem ganho.

---

## 5. Bloqueio por falhas: por conta e por IP

**Decision**: duas chaves Redis independentes, janela deslizante por aproximação (janela fixa de
15 min, aceitamos a borda, com `shortcut:` documentado).
- Por conta: `auth:login:acct:{account_id}` conta falhas; 5 falhas em 15 min → status
  `locked_until = now() + 15 min`.
- Por IP: `auth:login:ip:{ip}` conta falhas; 20 em 15 min → 429 `rate_limited`.

A resposta ao usuário é sempre a mesma mensagem genérica (FR-004); só o `Retry-After` do 429
muda. A mesma métrica alimenta o dashboard de segurança (`getnet_auth_login_total{outcome=
"ok|bad_password|unknown_account|locked|rate_limited"}`).

**Alternatives considered**:
- *Só por conta*: um atacante distribuído evita o bloqueio.
- *Só por IP*: NAT corporativo bloqueia todos os colegas.

---

## 6. Entrega de e-mail: aiosmtplib + Mailpit no dev

**Decision**: `aiosmtplib` com `SMTP_URL` (ex.: `smtp://mailpit:1025` em dev,
`smtps://user:pass@smtp.provider.com:465` em produção). Templates PT/EN em
`src/app/ops/mail_templates/`. Falha no envio **não** vira 5xx no usuário: a API responde o
mesmo 202 do caminho feliz; o erro é logado e contado em `getnet_auth_email_errors_total`. Isso
preserva FR-004/FR-002a (ninguém descobre que uma conta existe pelo erro). Para testes, Mailpit
expõe uma API HTTP (`http://mailpit:8025/api/v1/messages`) que os E2E do Playwright consultam
para pegar o link de confirmação, sem depender de polling de inbox real.

**Rationale**: Mailpit é um binário pequeno (10 MB), roda sem configuração e tem uma API
HTTP estável para testes.

**Alternatives considered**:
- *MailHog*: funcionando mas sem releases recentes e com UI mais pobre.
- *Enviar links no log*: aceito para desenvolvimento, mas quebra o fluxo E2E.

---

## 7. Playwright + SSE: event-source e desduplicação

**Decision**: Playwright 1.49 em TypeScript, com `expect` ampliado para esperar eventos SSE via
`page.waitForFunction` sobre um objeto global `__sse_events__` que o cliente SSE empurra. O
cliente SSE no SPA (lib/sse.ts) usa `EventSource` nativo; na perda de conexão, reconecta com
backoff e desduplica por `done.trace_id`. A reconexão não dispara `done` de novo porque o
servidor fecha o stream no final e o cliente usa o `done` como sinal de encerramento.

**Rationale**: `EventSource` nativo é mais leve que `fetch-event-source` e cobre o que o
contrato de eventos exige. Desduplicação por `trace_id` protege o teste contra flakiness.

**Alternatives considered**:
- *WebSocket*: muda o contrato da 001 sem necessidade.
- *fetch-event-source*: útil para headers customizados, mas aqui o cookie é enviado
  automaticamente.

---

## 8. nginx como proxy único; SPA + API na mesma origem

**Decision**: nginx 1.27-alpine, servindo os assets estáticos e fazendo `proxy_pass` de
`/v1/*` para `api:8000` (`proxy_buffering off` para SSE funcionar). Rota curinga `/*` serve
`index.html` (SPA routing). A porta pública do compose troca de `8000:api` para `80:web`; a API
deixa de ser pública (`api` não publica mais a 8000, só expõe internamente). A porta 9100 das
métricas continua interna (correção 14 do audit).

**Rationale**: mesma origem resolve CSRF em primeiro grau com `SameSite=Lax`. `proxy_buffering
off` em `/v1/chat/stream` e `/v1/conversations/*/events` evita o bufferização que quebra SSE.

**Alternatives considered**:
- *FastAPI servindo os estáticos*: mistura papéis, perde o `proxy_buffering off` seletivo e
  obriga rebuild da imagem backend a cada mudança de UI.
- *Vite dev server em produção*: inaceitável (fonte aberta de dev, sem cache).

---

## 9. Design system via Impeccable: tokens → Tailwind → componentes

**Decision**: `apps/web/src/design/tokens.ts` é a fonte da verdade (cores, tipografia, raios,
espaçamentos, sombras). Um script `scripts/tokens-to-tailwind.ts` lê o arquivo e gera
`tailwind.config.ts`, para evitar duplicação. Os componentes do design system não usam utilitários
`text-red-500` ou `p-4` diretamente — eles consomem tokens (`color.brand.primary`, `space.4`).
As telas das features usam só os componentes do design system; o lint da CI falha se um arquivo
em `features/` importa `tailwindcss/*` ou usa classes de cor cruas.

**Rationale**: cumpre o princípio XIII (tokens documentados em DESIGN.md) e evita drift visual.

**Alternatives considered**:
- *CSS Modules puro*: funciona, mas o custo de boilerplate é alto para 25 componentes.
- *CSS-in-JS (styled-components, emotion)*: adiciona runtime; sem ganho.

---

## 10. Identidade visual: redesign limitado baseado no site da Getnet

**Decision**: a identidade visual é tratada como **redesign limitado** no sentido do Impeccable:
preservar os sinais fortes da marca (vermelho `#EC0000`, logo publicado no site, tipografia
sem serifa com tom institucional, cantos de 8 px) e inventar o que o site **não cobre** (padrões
de chat, estados de SSE, fila de operador, formulários de autenticação, telas de admin), em vez
de tentar copiar pixel do site, que é um portal comercial. A fonte proprietária Santander é
substituída pela **Inter**, de distribuição aberta e proporções próximas, com fallback para a
pilha nativa do SO. O logotipo da Getnet é usado com atribuição e restrito a esta demonstração;
`PRODUCT.md` registra isso como brand commitment.

**Rationale**: o site da Getnet é marketing, não produto; adaptar sem clonar é a única rota
honesta para um painel operacional.

**Alternatives considered**:
- *Clonar o visual do site*: a hierarquia de banners de venda não serve a um chat; não há
  componente análogo a chat/fila no site.
- *Novo mundo visual (sem referência à Getnet)*: rejeitado pelo pedido explícito ("usando
  também a identidade visual da Getnet").
