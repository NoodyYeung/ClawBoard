-- Add project_name column to tasks table
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_name VARCHAR(255) DEFAULT NULL;
