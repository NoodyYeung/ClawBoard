-- 08-dispatch-retry.sql — Add retry_count to dispatches for auto-retry support

ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
