-- Calendar fields + "planning" status
-- planning → planned → in_progress → testing → review → done

-- Add scheduling columns to tasks
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS scheduled_end TIMESTAMP WITH TIME ZONE DEFAULT NULL;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS cron_job_id VARCHAR(100) DEFAULT NULL;

-- Index for calendar range queries
CREATE INDEX IF NOT EXISTS idx_tasks_scheduled ON tasks (scheduled_at)
    WHERE scheduled_at IS NOT NULL;

-- Update some sample tasks with scheduling info
UPDATE tasks SET scheduled_at = NOW() + INTERVAL '2 days' WHERE title = 'Set up CI/CD pipeline';
UPDATE tasks SET scheduled_at = NOW() + INTERVAL '5 days' WHERE title = 'Design database schema';
