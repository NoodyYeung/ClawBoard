-- Calendar events — independent from board tasks
-- These are OpenClaw-oriented scheduled jobs/prompts with color tags

CREATE TABLE IF NOT EXISTS event_tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(60) NOT NULL UNIQUE,
    color VARCHAR(9) NOT NULL DEFAULT '#3b82f6',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    tag_id INTEGER REFERENCES event_tags(id) ON DELETE SET NULL,
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    scheduled_end TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calendar_events_scheduled ON calendar_events (scheduled_at);
CREATE INDEX IF NOT EXISTS idx_calendar_events_tag ON calendar_events (tag_id);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_calendar_event_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_calendar_event_timestamp ON calendar_events;
CREATE TRIGGER set_calendar_event_timestamp
    BEFORE UPDATE ON calendar_events
    FOR EACH ROW
    EXECUTE FUNCTION update_calendar_event_timestamp();

-- Seed some default tags
INSERT INTO event_tags (name, color) VALUES
    ('dev-task', '#3b82f6'),
    ('security', '#ef4444'),
    ('maintenance', '#f59e0b'),
    ('research', '#8b5cf6'),
    ('deployment', '#22c55e'),
    ('meeting', '#ec4899')
ON CONFLICT (name) DO NOTHING;

-- Seed a sample calendar event
INSERT INTO calendar_events (title, prompt, tag_id, scheduled_at, scheduled_end) VALUES
    (
        'Audit API endpoints',
        'Run a comprehensive security audit on all API endpoints. Check for authentication issues, input validation, and rate limiting.',
        (SELECT id FROM event_tags WHERE name = 'security'),
        NOW() + INTERVAL '3 days' + INTERVAL '9 hours',
        NOW() + INTERVAL '3 days' + INTERVAL '10 hours'
    ),
    (
        'Refactor database queries',
        'Analyze slow queries in the backend and optimize them. Use EXPLAIN ANALYZE on the most frequent endpoints.',
        (SELECT id FROM event_tags WHERE name = 'dev-task'),
        NOW() + INTERVAL '5 days' + INTERVAL '14 hours',
        NOW() + INTERVAL '5 days' + INTERVAL '15 hours'
    );
