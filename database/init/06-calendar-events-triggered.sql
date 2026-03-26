-- Add is_triggered to calendar_events
ALTER TABLE calendar_events ADD COLUMN is_triggered BOOLEAN NOT NULL DEFAULT FALSE;
