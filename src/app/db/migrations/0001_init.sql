-- Schema from specs/001-multi-agent-support/data-model.md.
-- LangGraph checkpoint tables are created by AsyncPostgresSaver.setup().

CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Identity
CREATE TABLE users (
    id           text PRIMARY KEY,
    role         text NOT NULL CHECK (role IN ('merchant', 'operator', 'admin')),
    display_name text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- 2. Support mock data
CREATE TABLE merchants (
    user_id              text PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    trade_name           text NOT NULL,
    document_masked      text NOT NULL,
    plan                 text NOT NULL,
    settlement_days      int  NOT NULL CHECK (settlement_days >= 0),
    anticipation_enabled boolean NOT NULL DEFAULT false
);

CREATE TABLE terminals (
    id           text PRIMARY KEY,
    merchant_id  text NOT NULL REFERENCES merchants (user_id) ON DELETE CASCADE,
    model        text NOT NULL,
    serial       text NOT NULL,
    connectivity text NOT NULL CHECK (connectivity IN ('wifi', 'chip_4g', 'ethernet')),
    status       text NOT NULL CHECK (status IN ('online', 'offline', 'error')),
    last_seen_at timestamptz NOT NULL,
    last_error   text
);
CREATE INDEX terminals_merchant_idx ON terminals (merchant_id);

CREATE TABLE decline_codes (
    code           text PRIMARY KEY,
    description_pt text NOT NULL,
    description_en text NOT NULL,
    action_pt      text NOT NULL,
    action_en      text NOT NULL
);

CREATE TABLE transactions (
    id           text PRIMARY KEY,
    merchant_id  text NOT NULL REFERENCES merchants (user_id) ON DELETE CASCADE,
    terminal_id  text REFERENCES terminals (id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    method       text NOT NULL CHECK (method IN ('credit', 'debit', 'pix', 'payment_link')),
    installments int  NOT NULL CHECK (installments >= 1),
    status       text NOT NULL CHECK (status IN ('approved', 'declined')),
    decline_code text REFERENCES decline_codes (code),
    CHECK (status <> 'declined' OR decline_code IS NOT NULL)
);
CREATE INDEX transactions_merchant_created_idx ON transactions (merchant_id, created_at DESC);

CREATE TABLE settlements (
    id             text PRIMARY KEY,
    merchant_id    text NOT NULL REFERENCES merchants (user_id) ON DELETE CASCADE,
    transaction_id text NOT NULL REFERENCES transactions (id) ON DELETE CASCADE,
    expected_date  date NOT NULL,
    amount_cents   bigint NOT NULL CHECK (amount_cents > 0),
    status         text NOT NULL CHECK (status IN ('scheduled', 'paid', 'anticipated'))
);
CREATE INDEX settlements_merchant_date_idx ON settlements (merchant_id, expected_date);

-- 3. Conversations (history and graph state live in the LangGraph checkpoint tables)
CREATE TABLE conversations (
    id               uuid PRIMARY KEY,
    user_id          text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at       timestamptz NOT NULL DEFAULT now(),
    last_activity_at timestamptz NOT NULL DEFAULT now(),
    handoff_status   text NOT NULL DEFAULT 'none'
        CHECK (handoff_status IN ('none', 'awaiting_human', 'resolved', 'expired'))
);
CREATE INDEX conversations_user_idx ON conversations (user_id);
CREATE INDEX conversations_activity_idx ON conversations (last_activity_at);

-- 4. Knowledge base (BM25 is built in memory from chunks.content, ADR 0003)
CREATE TABLE documents (
    id           bigserial PRIMARY KEY,
    url          text NOT NULL UNIQUE,
    title        text NOT NULL,
    lang         text NOT NULL CHECK (lang IN ('pt', 'en')),
    source_type  text NOT NULL CHECK (source_type IN ('page', 'faq', 'pdf')),
    content_hash text NOT NULL,
    fetched_at   timestamptz NOT NULL
);

CREATE TABLE chunks (
    id          bigserial PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    ord         int  NOT NULL,
    section     text NOT NULL,
    content     text NOT NULL,
    lang        text NOT NULL CHECK (lang IN ('pt', 'en')),
    embedding   vector(1536) NOT NULL
);
CREATE INDEX chunks_document_idx ON chunks (document_id);
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);

-- 5. Human-in-the-loop
CREATE TABLE handoffs (
    id              uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    user_id         text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    reason          text NOT NULL CHECK (reason IN ('low_confidence', 'human_request',
                        'sensitive_topic', 'repeated_failures', 'side_effect_action')),
    status          text NOT NULL DEFAULT 'awaiting_human'
        CHECK (status IN ('awaiting_human', 'resolved', 'expired')),
    priority        text NOT NULL DEFAULT 'normal' CHECK (priority IN ('normal', 'high')),
    summary         text NOT NULL,
    context         jsonb NOT NULL DEFAULT '{}'::jsonb,
    pending_action  jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    sla_due_at      timestamptz NOT NULL,
    sla_notified_at timestamptz,
    expires_at      timestamptz NOT NULL,
    operator_id     text REFERENCES users (id),
    operator_reply  text,
    resolved_at     timestamptz
);
CREATE INDEX handoffs_status_idx ON handoffs (status, priority, created_at);
CREATE INDEX handoffs_conversation_idx ON handoffs (conversation_id);

-- 6. Audit and feedback
CREATE TABLE audit_events (
    id         bigserial PRIMARY KEY,
    ts         timestamptz NOT NULL DEFAULT now(),
    actor_id   text NOT NULL,
    actor_role text NOT NULL,
    action     text NOT NULL,
    target     text NOT NULL,
    outcome    text NOT NULL CHECK (outcome IN ('allowed', 'denied', 'error')),
    trace_id   text NOT NULL,
    metadata   jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX audit_events_ts_idx ON audit_events (ts);
CREATE INDEX audit_events_actor_idx ON audit_events (actor_id);

CREATE TABLE feedback (
    id              bigserial PRIMARY KEY,
    trace_id        text NOT NULL,
    user_id         text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    conversation_id uuid,
    rating          smallint NOT NULL CHECK (rating IN (-1, 1)),
    comment         text CHECK (char_length(comment) <= 1000),
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX feedback_trace_idx ON feedback (trace_id);
