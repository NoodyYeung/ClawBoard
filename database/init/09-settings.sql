-- 09-settings.sql: System-wide key-value settings table
-- Allows runtime configuration (e.g., LLM provider switch) without code changes.

CREATE TABLE IF NOT EXISTS system_settings (
    key         VARCHAR(100) PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed defaults (idempotent — won't overwrite existing values)
INSERT INTO system_settings (key, value, description) VALUES
    ('llm_provider',     'claude',                            'LLM provider for Claude Code: claude or minimax'),
    ('minimax_api_key',  '',                                  'MiniMax API key (Anthropic-compatible endpoint)'),
    ('minimax_base_url', 'https://api.minimax.io/anthropic',  'MiniMax API base URL'),
    ('minimax_model',    'MiniMax-M2.5',                      'MiniMax model name to use')
ON CONFLICT (key) DO NOTHING;
