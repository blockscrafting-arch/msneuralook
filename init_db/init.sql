-- Telegram Parser DB: posts, config, audit_log
-- Runs once on first postgres start (docker-entrypoint-initdb.d).

CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    source_channel TEXT NOT NULL,
    source_message_id BIGINT NOT NULL,
    original_text TEXT,
    pdf_path TEXT DEFAULT '',
    extracted_text TEXT,
    summary TEXT,
    edited_summary TEXT,
    editor_message_id BIGINT,
    status TEXT DEFAULT 'processing'
        CHECK (status IN ('processing', 'pending_review', 'approved', 'rejected', 'published')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_posts_source_message ON posts(source_channel, source_message_id);
CREATE INDEX idx_posts_status ON posts(status);
CREATE INDEX idx_posts_created_at ON posts(created_at);

CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO config (key, value, description) VALUES
    ('openai_prompt', 'Напиши краткое саммари текста для публикации в канале. Сохраняй смысл, будь лаконичен.', 'Промпт для OpenAI'),
    ('target_channel', '', 'ID целевого канала для публикации'),
    ('editor_chat_id', '', 'Telegram user ID редактора');

CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    post_id INT REFERENCES posts(id),
    action TEXT NOT NULL,
    actor TEXT,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_log_post_id ON audit_log(post_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);

-- Admin panel: source channels, admins, editors
CREATE TABLE source_channels (
    id SERIAL PRIMARY KEY,
    channel_identifier TEXT NOT NULL UNIQUE,
    display_name TEXT DEFAULT '',
    is_active BOOLEAN DEFAULT TRUE,
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE admins (
    user_id BIGINT PRIMARY KEY,
    username TEXT DEFAULT '',
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE editors (
    user_id BIGINT PRIMARY KEY,
    username TEXT DEFAULT '',
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
