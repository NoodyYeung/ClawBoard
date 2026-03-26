-- 10-dispatch-pr-url.sql — Add pr_url column to dispatches table
-- Stores the GitHub pull request URL created during a dispatch,
-- so the completion email can reliably link to the PR.

ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS pr_url TEXT;
