-- ClawBoard Schema
-- Task statuses: planned → in_progress → testing → review → done

CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(50) NOT NULL DEFAULT 'planned',
    position INTEGER NOT NULL DEFAULT 0,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fast column queries
CREATE INDEX idx_tasks_status ON tasks (status, is_archived, position);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Seed some sample tasks
INSERT INTO tasks (title, description, status, position) VALUES
    ('Set up CI/CD pipeline', 'Configure GitHub Actions for auto-deploy', 'planned', 0),
    ('Design database schema', 'ERD for the main application tables', 'planned', 1),
    ('Build auth module', 'JWT-based authentication with refresh tokens', 'in_progress', 0),
    ('Write unit tests for calc.py', 'Cover all edge cases in math operations', 'testing', 0),
    ('Review PR #42 — fix login bug', 'Security review needed before merge', 'review', 0),
    ('Deploy v0.1 to staging', 'Initial deployment with Docker Compose', 'done', 0);
