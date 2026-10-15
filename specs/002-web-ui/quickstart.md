# Quickstart: 002 Web UI

Como provar que a feature funciona ponta a ponta, sem Python nem Node no host.

## 1. Subir a stack

```bash
cp .env.example .env  # preencha OPENAI_API_KEY, JWT_SECRET, SESSION_SECRET, PASSWORD_PEPPER,
                      # POSTGRES_PASSWORD, DATABASE_URL, REDIS_URL, SMTP_URL=smtp://mailpit:1025
docker compose up -d --build  # agora inclui web (nginx) e mailpit
curl -fsS http://localhost/healthz
```

A API deixa de publicar porta pública; só o nginx atende em `80`.

## 2. Confirmar que o admin de demo foi criado

Em produção o primeiro admin é criado por comando; em dev ele vem do seed com `.env`.

```bash
docker compose exec api python scripts/create_demo_admin.py \
    --email admin@getnet.local --password 'senha-segura-demo-123'
```

Entre em [http://localhost/login](http://localhost/login) com `admin@getnet.local`.

## 3. História 1 — cadastro e login

- Abrir [http://localhost/register](http://localhost/register).
- Nome: `Loja Demo`, e-mail: `demo@loja.local`, senha: `senha-segura-demo-456`.
- Mensagem genérica aparece.
- Abrir [http://localhost:8025](http://localhost:8025) (Mailpit) e clicar no link de confirmação.
- Fazer login. Aparece a tela de chat.

Validação (REQ-SEC): tentar `curl -X POST /v1/auth/register` com o mesmo e-mail: resposta
genérica, sem revelar que existe. Tentar logar com senha errada 5× seguidas: a 6ª dá 423 com
mensagem genérica.

## 4. História 2 — chat com fontes

- Enviar: "Como funciona a antecipação?".
- Esperado: etapas `supervisor`, `knowledge` aparecem em até 1 s; resposta em até 8 s; fontes
  clicáveis (`site.getnet.com.br/...`).
- Enviar: "quero falar com um humano". Esperado: aparece "aguardando atendente" + ticket id.

## 5. História 3 — operador atende

- Em outra janela, entrar como `operador01@getnet.local`.
- Ver o ticket na fila. Abrir, responder "Resolvido!".
- Voltar à janela do lojista: a resposta chega sem recarregar em até 5 s.

## 6. História 4 — histórico

- Como lojista, ir em [http://localhost/me/conversations](http://localhost/me/conversations).
- Ver duas conversas. Clicar na primeira: histórico completo volta.

## 7. História 5 — privacidade

- Em `Privacidade`, "Apagar minhas conversas" → confirma digitando `EXCLUIR` → lista fica vazia,
  sessão permanece.
- "Excluir minha conta" → confirma digitando a senha atual e `EXCLUIR` → volta ao login.
- Tentar logar: resposta genérica. Cadastrar de novo com o mesmo e-mail: funciona como novo.

## 8. História 6 — admin

- Como admin: `Contas` → "Convidar operador". Novo link chega no Mailpit; abrir e definir a
  senha. Entrar como esse novo operador.
- `Vinculações` → associar `demo@loja.local` ao merchant `cliente1988`. No chat da loja,
  perguntar sobre recebíveis: o atendimento passa a responder com os dados do merchant.
- `Fila do dia` e `Auditoria` abrem sem dado pessoal em claro.

## 9. Suíte

```bash
# backend (como na 001)
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm tests pytest

# frontend (unit + a11y + visual regression)
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm web-tests npm run test

# E2E (Playwright headless; usa Mailpit API; rede interna, sem internet)
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm web-e2e

# lint e tipos
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm lint
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm web-lint
```

## 10. Carga e observabilidade

Os comandos da 001 continuam valendo. O nginx passa a aparecer no `getnet_http_requests_total`
com `route="/{anything}"` quando serve o SPA; o filtro do dashboard é `route=~"^/v1/"`.
