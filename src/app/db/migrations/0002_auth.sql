-- 002 Interface web: contas, sess\xf5es revog\xe1veis, tokens de link, bloqueio e v\xednculo com merchants.
-- Separado de `users` para que a exclus\xe3o da conta pelo pr\xf3prio lojista remova a pessoa sem
-- derrubar handoffs e conversas sob users (CASCADE da 001 cuidaria disso de forma errada).

CREATE TABLE auth_accounts (
    id                 text PRIMARY KEY,                 -- ulid com prefixo "acc_"
    email_lower        text NOT NULL UNIQUE,             -- lower(trim(email))
    display_name       text NOT NULL CHECK (char_length(display_name) BETWEEN 2 AND 80),
    role               text NOT NULL CHECK (role IN ('merchant', 'operator', 'admin')),
    status             text NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'active', 'locked', 'deactivated')),
    locked_until       timestamptz,
    email_verified_at  timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auth_accounts_role_idx ON auth_accounts (role);
CREATE INDEX auth_accounts_status_idx ON auth_accounts (status);

CREATE TABLE auth_credentials (
    account_id  text NOT NULL REFERENCES auth_accounts (id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('password')),
    secret      text NOT NULL,                           -- argon2id string
    created_at  timestamptz NOT NULL DEFAULT now(),
    rotated_at  timestamptz,
    PRIMARY KEY (account_id, kind)
);

CREATE TABLE auth_sessions (
    jti           text PRIMARY KEY,                      -- ulid; vai no JWT
    account_id    text NOT NULL REFERENCES auth_accounts (id) ON DELETE CASCADE,
    issued_at     timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    revoked_at    timestamptz,
    ip            inet NOT NULL,
    user_agent    text NOT NULL
);
CREATE INDEX auth_sessions_account_active_idx
    ON auth_sessions (account_id, last_seen_at DESC)
    WHERE revoked_at IS NULL;

CREATE TABLE auth_one_time_tokens (
    hash        text PRIMARY KEY,                        -- sha256(token em hex)
    account_id  text NOT NULL REFERENCES auth_accounts (id) ON DELETE CASCADE,
    purpose     text NOT NULL CHECK (purpose IN ('verify_email', 'password_reset', 'invite')),
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auth_one_time_tokens_account_purpose_idx
    ON auth_one_time_tokens (account_id, purpose, expires_at DESC);

-- Hist\xf3rico para suporte interno; o bloqueio efetivo vive em Redis (login_rate).
CREATE TABLE auth_login_attempts (
    ts           timestamptz NOT NULL DEFAULT now(),
    email_lower  text NOT NULL,
    ip           inet NOT NULL,
    outcome      text NOT NULL
        CHECK (outcome IN ('ok', 'bad_password', 'unknown_account', 'locked', 'rate_limited'))
);
CREATE INDEX auth_login_attempts_email_ts_idx ON auth_login_attempts (email_lower, ts DESC);
CREATE INDEX auth_login_attempts_ts_idx ON auth_login_attempts (ts);

-- V\xednculo com a 001: um merchant pode ser dono de no m\xe1ximo uma conta de autentica\xe7\xe3o (FR-021).
-- ON DELETE SET NULL preserva o merchant quando o lojista exclui a pr\xf3pria conta (FR-016a).
ALTER TABLE merchants
    ADD COLUMN account_id text UNIQUE REFERENCES auth_accounts (id) ON DELETE SET NULL;
CREATE INDEX merchants_account_idx ON merchants (account_id);
