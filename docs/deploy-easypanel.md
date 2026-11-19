# Deploy no EasyPanel (VPS Hostinger, Ubuntu 24.04)

Sobe a pilha inteira (site, API, Postgres com pgvector, Redis, caixa de e-mail de demonstracao)
a partir de `docker-compose.easypanel.yml`. Sem dominio: acesso por `http://IP:8080`, sem HTTPS.

## 1. Preparar

- Repositorio no GitHub com o arquivo `docker-compose.easypanel.yml` na raiz.
- Servidor com pelo menos 4 GB de RAM livres (a API usa ate 2 GB; o KVM 2 tem 8 GB).
- No painel da Hostinger, se houver firewall ativo, libere as portas **8080** (site) e **8025**
  (caixa de e-mail de demonstracao).
- Gere os segredos (um valor diferente para cada), por exemplo: `openssl rand -hex 32`.

## 2. Criar o servico

1. EasyPanel → **Create Project** (ex.: `getnet`) → **+ Service** → **Compose**.
2. **Source**: Git → URL do repositorio, branch `main`.
   **Compose file**: `docker-compose.easypanel.yml`.
3. Aba **Environment**, preencha:

```
OPENAI_API_KEY=<sua chave>
POSTGRES_PASSWORD=<aleatorio>
JWT_SECRET=<aleatorio>
SESSION_SECRET=<aleatorio>
PASSWORD_PEPPER=<aleatorio>
ADMIN_SEED_PASSWORD=<senha do usuario admin, minimo 12 caracteres>
MAILPIT_UI_AUTH=<usuario>:<senha da caixa de e-mail, sem espacos>
WEB_BASE_URL=http://<IP-da-VPS>:8080
```

`APP_ENV` fica em `local` (padrao): so assim a base carrega os dados de exemplo
(comerciantes, recebiveis, terminais). Com `production` o banco sobe sem esses dados.

4. **Deploy**. A primeira vez demora (build da API e da base de conhecimento).
   O servico `seed-admin` cria o admin (`ADMIN_SEED_EMAIL`, padrao `admin@getnet.example.com`)
   e termina; nos deploys seguintes ele ve que o admin existe e sai sem mudar a senha.

## 3. Usar

- Site: `http://<IP-da-VPS>:8080`
- Login de admin: `ADMIN_SEED_EMAIL` / `ADMIN_SEED_PASSWORD`.
- Cadastro: o link de confirmacao chega na caixa de demonstracao `http://<IP-da-VPS>:8025`
  (pede o usuario e a senha de `MAILPIT_UI_AUTH`).

## Limitacoes

- Sem HTTPS: login e senha trafegam em texto puro. Para producao, use um dominio e o
  dominio do proprio EasyPanel (Traefik emite o certificado).
- A porta 8025 mostra todos os e-mails a quem tiver a senha de `MAILPIT_UI_AUTH`, e ela tambem
  trafega sem HTTPS. Em producao, aponte `SMTP_URL` para um
  provedor real e remova essa porta do compose.
