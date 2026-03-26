"""Tests for the monitor router.

Run with:
  docker compose run --rm --entrypoint python api -m pytest /app/tests/test_monitor.py -v
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---- Test the JSONL parsing helpers directly ----

# We need to make the helpers importable
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.monitor import _parse_session_activity, _count_messages, _find_session_file


@pytest.fixture
def sample_session_file(tmp_path):
    """Create a sample JSONL session file."""
    session_id = "test-session-123"
    project_dir = tmp_path / "-home-test-project"
    project_dir.mkdir()
    session_file = project_dir / f"{session_id}.jsonl"

    lines = [
        # Thinking block
        json.dumps({
            "type": "assistant",
            "timestamp": "2025-01-01T10:00:00Z",
            "message": {
                "content": [{
                    "type": "thinking",
                    "thinking": "Let me analyze this problem. I need to read the file first and understand the structure before making changes."
                }]
            }
        }),
        # Tool use: Bash
        json.dumps({
            "type": "assistant",
            "timestamp": "2025-01-01T10:00:05Z",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {
                        "command": "ls -la /app/src/",
                        "description": "List source files"
                    }
                }]
            }
        }),
        # Tool result
        json.dumps({
            "type": "user",
            "userType": "external",
            "timestamp": "2025-01-01T10:00:06Z",
        }),
        # Tool use: Read
        json.dumps({
            "type": "assistant",
            "timestamp": "2025-01-01T10:00:10Z",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "name": "Read",
                    "input": {"file_path": "/app/src/main.py"}
                }]
            }
        }),
        # Text output
        json.dumps({
            "type": "assistant",
            "timestamp": "2025-01-01T10:00:20Z",
            "message": {
                "content": [{
                    "type": "text",
                    "text": "I've completed the changes. The new function handles edge cases correctly."
                }]
            }
        }),
        # Tool use: Edit
        json.dumps({
            "type": "assistant",
            "timestamp": "2025-01-01T10:00:25Z",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "name": "Edit",
                    "input": {"file_path": "/app/src/handler.py"}
                }]
            }
        }),
        # TodoWrite
        json.dumps({
            "type": "assistant",
            "timestamp": "2025-01-01T10:00:30Z",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "name": "TodoWrite",
                    "input": {
                        "todos": [
                            {"content": "Task A", "status": "completed"},
                            {"content": "Task B", "status": "in_progress"},
                            {"content": "Task C", "status": "pending"},
                        ]
                    }
                }]
            }
        }),
        # Queue operation (should be skipped)
        json.dumps({
            "type": "queue-operation",
            "timestamp": "2025-01-01T10:00:35Z",
        }),
    ]

    session_file.write_text("\n".join(lines))
    return tmp_path, session_id, str(session_file)


def test_parse_session_activity(sample_session_file):
    """Test that we correctly parse all activity types from JSONL."""
    _, _, filepath = sample_session_file
    activities = _parse_session_activity(filepath, max_events=50)

    # Should have: thinking, bash tool_use, tool_result, read tool_use, text, edit tool_use, todo tool_use
    assert len(activities) == 7

    # Thinking
    assert activities[0].type == "thinking"
    assert "🧠" in activities[0].summary
    assert "analyze this problem" in activities[0].summary

    # Bash tool
    assert activities[1].type == "tool_use"
    assert "Bash" in activities[1].summary
    assert "List source files" in activities[1].summary

    # Tool result
    assert activities[2].type == "tool_result"

    # Read tool
    assert activities[3].type == "tool_use"
    assert "Read" in activities[3].summary
    assert "main.py" in activities[3].summary

    # Text
    assert activities[4].type == "text"
    assert "completed the changes" in activities[4].summary

    # Edit tool
    assert activities[5].type == "tool_use"
    assert "Edit" in activities[5].summary
    assert "handler.py" in activities[5].summary

    # TodoWrite
    assert activities[6].type == "tool_use"
    assert "Todos" in activities[6].summary
    assert "1 done" in activities[6].summary
    assert "1 in progress" in activities[6].summary


def test_parse_session_max_events(sample_session_file):
    """Test that max_events limits the returned activities."""
    _, _, filepath = sample_session_file
    activities = _parse_session_activity(filepath, max_events=3)
    assert len(activities) == 3
    # Should be the LAST 3 events: text, edit tool_use, todo tool_use
    assert activities[0].type == "text"
    assert activities[1].type == "tool_use"  # Edit
    assert activities[2].type == "tool_use"  # TodoWrite


def test_count_messages(sample_session_file):
    """Test message counting."""
    _, _, filepath = sample_session_file
    count = _count_messages(filepath)
    assert count == 8  # 8 JSONL lines


def test_find_session_file(sample_session_file):
    """Test session file lookup by ID."""
    base_dir, session_id, expected_path = sample_session_file

    with patch("routers.monitor.CLAUDE_SESSIONS_PATH", str(base_dir)):
        result = _find_session_file(session_id)
        assert result == expected_path


def test_find_session_file_not_found(sample_session_file):
    """Test that missing sessions return None."""
    base_dir, _, _ = sample_session_file

    with patch("routers.monitor.CLAUDE_SESSIONS_PATH", str(base_dir)):
        result = _find_session_file("nonexistent-session-id")
        assert result is None


def test_parse_empty_file(tmp_path):
    """Test parsing an empty session file."""
    f = tmp_path / "empty.jsonl"
    f.write_text("")
    activities = _parse_session_activity(str(f))
    assert activities == []


def test_parse_invalid_json(tmp_path):
    """Test that invalid JSON lines are skipped."""
    f = tmp_path / "bad.jsonl"
    f.write_text("not json\n{bad json too}\n")
    activities = _parse_session_activity(str(f))
    assert activities == []


def test_thinking_truncation(tmp_path):
    """Test that long thinking is truncated to 200 chars."""
    f = tmp_path / "long.jsonl"
    long_thinking = "A" * 500
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "thinking", "thinking": long_thinking}]}
    })
    f.write_text(line)
    activities = _parse_session_activity(str(f))
    assert len(activities) == 1
    # Summary should be "🧠 " + 200 chars + "…"
    assert activities[0].summary.endswith("…")
    assert len(activities[0].summary) < 220  # emoji + space + 200 + …


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
