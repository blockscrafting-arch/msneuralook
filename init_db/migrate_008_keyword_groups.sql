-- Migration 008: Keyword groups (each group -> one target channel for routing)
-- Apply after 004 (target_channels) and 007. 006/007 are userbot_outbox and delivery_retry.
-- docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_008_keyword_groups.sql

CREATE TABLE IF NOT EXISTS keyword_groups (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    target_channel_id INT NOT NULL REFERENCES target_channels(id) ON DELETE RESTRICT,
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE keywords ADD COLUMN IF NOT EXISTS group_id INT REFERENCES keyword_groups(id) ON DELETE SET NULL;
