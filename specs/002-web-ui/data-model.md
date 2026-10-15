# Data Model: Interface web

Migration: `src/app/db/migrations/0002_auth.sql`. Nenhuma tabela da 001 é alterada
destrutivamente; `merchants` ganha uma coluna opcional.

---

## auth_accounts

Pessoa que faz login. Separada de `users` (001) para que a exclusão da conta não arraste em
cascade os `handoffs` e `conversations` que estão sob `users`.

| Coluna             | Tipo        | Regra                                                  |
|--------------------|-------------|--------------------------------------------------------|
| `id`               | text PK     | ulid gerado no servidor (`acc_<26 chars>`)             |
| `email_lower`      | text UNIQUE | NOT NULL, armazenado em `lower(trim(e-mail))`          |
| `display_name`     | text        | NOT NULL                                               |
| `role`             | text        | CHECK IN ('merchant','operator','admin')               |
| `status`           | text        | CHECK IN ('pending','active','locked','deactivated')   |
| `locked_until`     | timestamptz | NULL quando não bloqueada                              |
| `created_at`       | timestamptz | DEFAULT now()                                          |
| `email_verified_at`| timestamptz | NULL enquanto não confirmada                           |

Índices: `idx_auth_accounts_email_lower` já implicado pelo UNIQUE.

**Vinculação com a 001**: quando o admin liga uma conta de lojista a um `merchants.user_id`,
grava-se `merchants.account_id = auth_accounts.id`. A API passa a traduzir
`auth_accounts.id → users.id` só nas chamadas do grafo da 001 (que opera com `user_id` texto). A
tradução acontece dentro do backend; o SPA nunca vê `users.id`.

Transições:
- `pending → active` quando `email_verified_at` é preenchido.
- `active → locked` quando `locked_until` é setado por `login_rate`.
- `locked → active` quando `locked_until < now()`.
- `active → deactivated` só por admin; destrói todas as sessões.
- qualquer → *linha removida* na exclusão (`DELETE /v1/me/account`): o CASCADE abaixo cuida das
  tabelas filhas da autenticação; `users` não é tocado.

---

## auth_credentials

Hash de senha isolado da conta para permitir rotação sem reescrever a linha de conta e para
que um futuro login social fique como outra credencial.

| Coluna          | Tipo       | Regra                                        |
|-----------------|------------|----------------------------------------------|
| `account_id`    | text FK → auth_accounts(id) ON DELETE CASCADE |
| `kind`          | text       | CHECK IN ('password')                        |
| `secret`        | text       | argon2id com pepper                          |
| `created_at`    | timestamptz| DEFAULT now()                                |
| `rotated_at`    | timestamptz| NULL até a próxima troca                     |

PK: (`account_id`, `kind`).

---

## auth_sessions

Uma sessão por login. Tudo que o `check-sessions.py` precisa para revogar sem reemitir cookies.

| Coluna          | Tipo        | Regra                                                      |
|-----------------|-------------|------------------------------------------------------------|
| `jti`           | text PK     | ulid; vai dentro do JWT                                    |
| `account_id`    | text FK → auth_accounts(id) ON DELETE CASCADE               |
| `issued_at`     | timestamptz | DEFAULT now()                                              |
| `last_seen_at`  | timestamptz | DEFAULT now(); atualizado em toda req autenticada          |
| `revoked_at`    | timestamptz | NULL enquanto ativa                                        |
| `ip`            | inet        | NOT NULL                                                   |
| `user_agent`    | text        | NOT NULL (truncado a 200 caracteres)                       |

Índice: `(account_id, revoked_at NULLS FIRST, last_seen_at DESC)` para "listar minhas sessões".

Regras:
- Troca de senha: `UPDATE auth_sessions SET revoked_at = now() WHERE account_id = $1`.
- Exclusão de conta ou desativação: idem, em transação, antes do `DELETE` ou `UPDATE` da conta.
- Scheduler expurga `revoked_at IS NOT NULL AND revoked_at < now() - 7 days`.

---

## auth_one_time_tokens

Confirmação de e-mail, redefinição de senha, convite de operador/admin.

| Coluna        | Tipo        | Regra                                                  |
|---------------|-------------|--------------------------------------------------------|
| `hash`        | text PK     | sha256(token) em hex (o token em claro só vai no e-mail) |
| `account_id`  | text FK → auth_accounts(id) ON DELETE CASCADE           |
| `purpose`     | text        | CHECK IN ('verify_email','password_reset','invite')    |
| `expires_at`  | timestamptz | NOT NULL                                               |
| `used_at`     | timestamptz | NULL até o primeiro uso                                |
| `created_at`  | timestamptz | DEFAULT now()                                          |

Regras:
- Qualquer rota que consome um token procura por `hash` e verifica `used_at IS NULL AND
  expires_at > now()`.
- Após uso bem-sucedido, `UPDATE ... SET used_at = now()` na mesma transação da ação.
- Scheduler expurga `used_at IS NOT NULL OR expires_at < now() - 7 days`.

---

## auth_login_attempts

Tabela só para auditoria/estatística histórica. O bloqueio efetivo é em Redis.

| Coluna      | Tipo        | Regra                                            |
|-------------|-------------|--------------------------------------------------|
| `ts`        | timestamptz | DEFAULT now()                                    |
| `email_lower` | text      | NOT NULL                                         |
| `ip`        | inet        | NOT NULL                                         |
| `outcome`   | text        | CHECK IN ('ok','bad_password','unknown_account','locked','rate_limited') |

Índice: `(email_lower, ts DESC)` para suporte interno.
Scheduler expurga segundo `retention_log_days` (REQ-SEC-09).

---

## Alterações em tabelas existentes

```sql
-- 001 continua intacto; só anexamos a chave do novo mundo de contas.
ALTER TABLE merchants ADD COLUMN account_id text UNIQUE
    REFERENCES auth_accounts(id) ON DELETE SET NULL;
CREATE INDEX merchants_account_idx ON merchants(account_id);
```

Sem outras alterações. `audit_events` já aceita qualquer `actor_id`; passa a receber tanto
`auth_accounts.id` (lojista logado) quanto `users.id` legado (seed) sem mudança.

---

## Semântica de "excluir minha conta" (FR-016a)

Em uma transação única:

1. Revoga toda sessão (`auth_sessions`).
2. Para cada `thread_id` do lojista: `adelete_thread` (igual ao DELETE /v1/me/data atual).
3. Deleta conversas e feedback do `users.id` correspondente (via tradução
   `auth_accounts.id → users.id`).
4. Desvincula o `merchants.account_id`.
5. Pseudonimiza `audit_events.actor_id = 'deleted:' + hmac(SESSION_SECRET, account_id)`.
6. `DELETE FROM auth_accounts WHERE id = $1` (CASCADE em `auth_credentials`,
   `auth_sessions`, `auth_one_time_tokens`).

Resultado observável: tentativa de login com o mesmo e-mail devolve a resposta genérica, como se
o e-mail nunca tivesse existido (FR-004); o merchant continua ativo, pronto para outro vínculo.
