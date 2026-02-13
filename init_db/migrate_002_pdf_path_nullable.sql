-- Migration 002: Allow empty pdf_path for text-only posts.
-- Apply on existing DB: psql -f migrate_002_pdf_path_nullable.sql or via docker exec.

ALTER TABLE posts ALTER COLUMN pdf_path DROP NOT NULL;
ALTER TABLE posts ALTER COLUMN pdf_path SET DEFAULT '';
