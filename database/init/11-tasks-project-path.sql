-- Add project_path column for arbitrary working directory dispatch
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_path TEXT;
