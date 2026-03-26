-- Task activity / message log
-- Append-only: AI agents ADD messages, never delete or replace existing ones.

CREATE TABLE IF NOT EXISTS task_messages (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    author VARCHAR(100) NOT NULL DEFAULT 'system',
    event_type VARCHAR(50) NOT NULL DEFAULT 'comment',
    status_from VARCHAR(50),
    status_to VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fast lookup by task
CREATE INDEX idx_task_messages_task_id ON task_messages (task_id, created_at);

-- Seed some example messages for the existing tasks
INSERT INTO task_messages (task_id, message, author, event_type) VALUES
    (1, 'Task created', 'system', 'created'),
    (2, 'Task created', 'system', 'created'),
    (3, 'Task created', 'system', 'created'),
    (3, 'Started working on JWT auth with refresh token rotation', 'claude-teams', 'comment'),
    (4, 'Task created', 'system', 'created'),
    (5, 'Task created', 'system', 'created'),
    (6, 'Task created', 'system', 'created'),
    (6, 'Docker Compose stack is running on ports 5434/8100/5174', 'dev-task', 'comment');
