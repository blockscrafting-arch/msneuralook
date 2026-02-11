-- Migration 006: Userbot outbox for reliable delivery to n8n
-- Apply: docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_006_userbot_outbox.sql

CREATE TABLE IF NOT EXISTS userbot_outbox (
    id SERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL,
    message_id BIGINT NOT NULL,
    pdf_path TEXT DEFAULT '',
    pdf_missing BOOLEAN DEFAULT FALSE,
    post_text TEXT DEFAULT '',
    source_channel TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'failed')),
    attempts INT NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (channel_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_userbot_outbox_status ON userbot_outbox (status);
CREATE INDEX IF NOT EXISTS idx_userbot_outbox_next_retry ON userbot_outbox (next_retry_at) WHERE status = 'pending';
