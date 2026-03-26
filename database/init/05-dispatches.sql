-- 05-dispatches.sql — Track Claude Code dispatch jobs

CREATE TABLE IF NOT EXISTS dispatches (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    status          VARCHAR(50)  NOT NULL DEFAULT 'queued',
        -- queued → running → completed | failed | stopped
    prompt          TEXT         NOT NULL DEFAULT '',
    project_name    VARCHAR(255),
    workdir         VARCHAR(500),
    agent_mode      VARCHAR(50)  NOT NULL DEFAULT 'dev-task',
        -- dev-task (single agent) or claude-teams (multi-agent)
    session_id      VARCHAR(100),
    exit_code       INTEGER,
    output          TEXT,
    error_reason    TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- Index for fast lookup of active dispatches
CREATE INDEX IF NOT EXISTS idx_dispatches_status ON dispatches(status);
CREATE INDEX IF NOT EXISTS idx_dispatches_task_id ON dispatches(task_id);
