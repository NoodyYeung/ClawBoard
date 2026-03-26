-- Per-project git strategy settings
CREATE TABLE IF NOT EXISTS project_settings (
    id SERIAL PRIMARY KEY,
    project_key VARCHAR(500) NOT NULL UNIQUE,
    git_strategy VARCHAR(50) NOT NULL DEFAULT 'direct_commit',
    default_branch VARCHAR(100) NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
