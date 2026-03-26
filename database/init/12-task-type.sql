-- Add task_type and task_meta columns to tasks table
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS task_type VARCHAR(50) NOT NULL DEFAULT 'coding';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS task_meta JSONB;
