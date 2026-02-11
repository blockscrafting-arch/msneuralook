-- Migration 007: Editor-bot delivery retry and publish status
-- Apply: docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_007_delivery_retry.sql

ALTER TABLE posts ADD COLUMN IF NOT EXISTS delivery_attempts INT NOT NULL DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS last_delivery_error TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ;

ALTER TABLE posts DROP CONSTRAINT IF EXISTS posts_status_check;
ALTER TABLE posts ADD CONSTRAINT posts_status_check
    CHECK (status IN (
        'processing', 'pending_review', 'approved', 'rejected',
        'published', 'scheduled', 'publishing', 'send_failed', 'publish_failed'
    ));

CREATE INDEX IF NOT EXISTS idx_posts_next_retry ON posts (next_retry_at) WHERE status IN ('processing', 'send_failed');
