-- Migration 003: Keywords (markers) for filtering posts in userbot
-- Apply: docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_003_keywords.sql

CREATE TABLE IF NOT EXISTS keywords (
    id SERIAL PRIMARY KEY,
    word TEXT NOT NULL UNIQUE,
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
