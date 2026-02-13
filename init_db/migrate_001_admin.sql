-- Migration 001: Admin panel tables (source_channels, admins, editors)
-- Apply on existing DB: psql -f migrate_001_admin.sql or via docker exec.

CREATE TABLE IF NOT EXISTS source_channels (
    id SERIAL PRIMARY KEY,
    channel_identifier TEXT NOT NULL UNIQUE,
    display_name TEXT DEFAULT '',
    is_active BOOLEAN DEFAULT TRUE,
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admins (
    user_id BIGINT PRIMARY KEY,
    username TEXT DEFAULT '',
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS editors (
    user_id BIGINT PRIMARY KEY,
    username TEXT DEFAULT '',
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
