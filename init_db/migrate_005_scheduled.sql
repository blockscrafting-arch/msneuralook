-- Migration 005: Scheduled publishing (scheduled_at, status 'scheduled')
-- Apply: docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_005_scheduled.sql

ALTER TABLE posts ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ;

ALTER TABLE posts DROP CONSTRAINT IF EXISTS posts_status_check;
ALTER TABLE posts ADD CONSTRAINT posts_status_check
    CHECK (status IN ('processing','pending_review','approved','rejected','published','scheduled'));

CREATE INDEX IF NOT EXISTS idx_posts_scheduled ON posts (scheduled_at) WHERE status = 'scheduled';
