-- Migration 004: Target channels table (multiple targets for publishing)
-- Apply: docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_004_target_channels.sql

CREATE TABLE IF NOT EXISTS target_channels (
    id SERIAL PRIMARY KEY,
    channel_identifier TEXT NOT NULL UNIQUE,
    display_name TEXT DEFAULT '',
    is_active BOOLEAN DEFAULT TRUE,
    added_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Migrate existing single target from config into target_channels
INSERT INTO target_channels (channel_identifier, display_name)
SELECT value, 'Основной'
FROM config WHERE key = 'target_channel' AND value IS NOT NULL AND value != ''
ON CONFLICT (channel_identifier) DO NOTHING;
