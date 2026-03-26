"""Monitor API — live view into Claude Code session activity.

Reads the JSONL session logs that Claude Code writes to disk and returns
structured activity data (tool calls, thinking summaries, text outputs).

The frontend polls this endpoint every few seconds to show a live view
of what Claude Code is doing.
"""

import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Dispatch, Task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/monitor", tags=["monitor"])

# Claude Code stores sessions under ~/.claude/projects/<encoded-dir>/<session-id>.jsonl
CLAUDE_SESSIONS_PATH = os.environ.get(
    "CLAUDE_SESSIONS_PATH",
    "/claude-sessions",  # mounted volume
)


# ---- Response schemas ----

class ActivityEntry(BaseModel):
    """A single activity event from a Claude session."""
    timestamp: Optional[str] = None
    type: str  # "thinking" | "tool_use" | "tool_result" | "text" | "error" | "status"
    summary: str  # Short human-readable description
    detail: Optional[str] = None  # Extra info (tool input, truncated thinking, etc.)


class SessionStatus(BaseModel):
    """Live status of a Claude Code session."""
    dispatch_id: Optional[int] = None
    task_id: Optional[int] = None
    task_title: Optional[str] = None
    project_name: Optional[str] = None
    dispatch_status: Optional[str] = None  # queued | running | completed | failed
    session_id: Optional[str] = None
    session_file: Optional[str] = None
    started_at: Optional[str] = None
    total_messages: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    activity: list[ActivityEntry] = []  # Recent activity (last N events)


class MonitorOverview(BaseModel):
    """Overview of all Claude Code processes."""
    has_active: bool = False
    active_dispatches: int = 0
    sessions: list[SessionStatus] = []
    recent_completed: list[SessionStatus] = []


# ---- Helpers ----

def _find_session_file(session_id: str) -> Optional[str]:
    """Find a session JSONL file by session ID across all project dirs."""
    base = Path(CLAUDE_SESSIONS_PATH)
    if not base.exists():
        return None
    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        candidate = project_dir / f"{session_id}.jsonl"
        if candidate.exists():
            return str(candidate)
    return None


def _find_latest_session_for_workdir(workdir: str) -> Optional[str]:
    """Find the most recently modified session file for a given workdir (project)."""
    base = Path(CLAUDE_SESSIONS_PATH)
    if not base.exists():
        return None

    # Claude encodes the workdir path: /home/noody/Projects/X → -home-noody-Projects-X
    encoded = workdir.replace("/", "-").lstrip("-")

    best_file = None
    best_mtime = 0
    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        dir_name = project_dir.name.lstrip("-")
        if encoded in dir_name or dir_name in encoded:
            for jsonl in project_dir.glob("*.jsonl"):
                mtime = jsonl.stat().st_mtime
                if mtime > best_mtime:
                    best_mtime = mtime
                    best_file = str(jsonl)
    return best_file


def _parse_session_activity(filepath: str, max_events: int = 0) -> dict:
    """max_events=0 means no limit. Callers trim as needed."""
    """Parse a session JSONL file and extract activity entries.
    Returns dict: {activity, total_tokens, total_cost_usd}
    """
    activities: list[ActivityEntry] = []
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost_usd = 0.0

    try:
        with open(filepath) as f:
            lines = [l.strip() for l in f if l.strip()]
    except (OSError, IOError) as e:
        logger.warning("Cannot read session file %s: %s", filepath, e)
        return {"activity": [ActivityEntry(type="error", summary=f"Cannot read session: {e}")],
                "total_tokens": 0, "total_cost_usd": 0.0}

    for line in lines:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type", "")
        timestamp = msg.get("timestamp")

        if msg_type == "assistant":
            usage = msg.get("message", {}).get("usage", {})
            total_input_tokens += usage.get("input_tokens", 0)
            total_output_tokens += usage.get("output_tokens", 0)

            content = msg.get("message", {}).get("content", [])
            for block in content:
                btype = block.get("type", "")

                if btype == "thinking":
                    thinking_text = block.get("thinking", "")
                    summary = thinking_text[:200]
                    if len(thinking_text) > 200:
                        summary += "…"
                    activities.append(ActivityEntry(
                        timestamp=timestamp,
                        type="thinking",
                        summary=f"🧠 {summary}",
                        detail=thinking_text if len(thinking_text) > 200 else None,
                    ))

                elif btype == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    if tool_name == "Bash":
                        cmd = tool_input.get("command", "")
                        desc = tool_input.get("description", "")
                        detail = cmd if cmd else None
                        summary = f"🔧 Bash: {desc or cmd[:120]}"
                    elif tool_name == "Read":
                        fpath = tool_input.get("file_path", "")
                        summary = f"📖 Read: {fpath}"
                        detail = None
                    elif tool_name in ("Edit", "Write"):
                        fpath = tool_input.get("file_path", "")
                        summary = f"✏️ {tool_name}: {fpath}"
                        detail = None
                    elif tool_name == "TodoWrite":
                        todos = tool_input.get("todos", [])
                        in_progress = [t for t in todos if t.get("status") == "in_progress"]
                        completed = [t for t in todos if t.get("status") == "completed"]
                        summary = f"📋 Todos: {len(completed)} done, {len(in_progress)} in progress, {len(todos)} total"
                        detail = None
                    elif tool_name == "WebFetch":
                        url = tool_input.get("url", "")
                        summary = f"🌐 WebFetch: {url[:100]}"
                        detail = None
                    else:
                        input_str = json.dumps(tool_input)
                        summary = f"🔧 {tool_name}"
                        detail = input_str[:300] if len(input_str) > 0 else None
                    activities.append(ActivityEntry(
                        timestamp=timestamp, type="tool_use", summary=summary, detail=detail,
                    ))

                elif btype == "text":
                    text = block.get("text", "")
                    if text.strip():
                        truncated = text[:300]
                        if len(text) > 300:
                            truncated += "…"
                        activities.append(ActivityEntry(
                            timestamp=timestamp, type="text",
                            summary=f"💬 {truncated}",
                            detail=text if len(text) > 300 else None,
                        ))

        elif msg_type == "user":
            content_list = msg.get("message", {}).get("content", [])
            for block in content_list:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue
                is_error = block.get("is_error", False)

                # Try tool_use_result first (has separate stdout/stderr)
                tool_use_result = msg.get("tool_use_result", {})
                if not isinstance(tool_use_result, dict):
                    tool_use_result = {}
                stdout = tool_use_result.get("stdout", "")
                stderr = tool_use_result.get("stderr", "")
                interrupted = tool_use_result.get("interrupted", False)

                if interrupted:
                    actual = "⚠️ Interrupted"
                elif stdout or stderr:
                    actual = (stdout + ("\n" + stderr if stderr else "")).strip()
                else:
                    raw = block.get("content", "")
                    actual = raw if isinstance(raw, str) else json.dumps(raw)

                actual = actual.strip()
                icon = "❌" if is_error else "📤"
                if not actual:
                    summary = f"{icon} (empty result)"
                    detail = None
                elif len(actual) <= 200:
                    summary = f"{icon} {actual}"
                    detail = None
                else:
                    summary = f"{icon} {actual[:200]}…"
                    detail = actual

                activities.append(ActivityEntry(
                    timestamp=timestamp, type="tool_result",
                    summary=summary, detail=detail,
                ))

        elif msg_type == "result":
            total_cost_usd = msg.get("total_cost_usd", total_cost_usd)
            usage = msg.get("usage", {})
            total_input_tokens = usage.get("input_tokens", total_input_tokens)
            total_output_tokens = usage.get("output_tokens", total_output_tokens)

    trimmed = activities[-max_events:] if max_events > 0 else activities
    return {
        "activity": trimmed,
        "total_tokens": total_input_tokens + total_output_tokens,
        "total_cost_usd": total_cost_usd,
    }


def _parse_stream_json_output(output: str, max_events: int = 0) -> dict:
    """max_events=0 means no limit. Callers trim as needed."""
    """Parse stream-json output stored in the dispatch DB output field.
    Returns dict: {activity, total_tokens, total_cost_usd}
    """
    activities: list[ActivityEntry] = []
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost_usd = 0.0

    if not output:
        return {"activity": activities, "total_tokens": 0, "total_cost_usd": 0.0}

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type", "")

        if msg_type == "system" and msg.get("subtype") == "init":
            model = msg.get("model", "unknown")
            activities.append(ActivityEntry(
                type="status",
                summary=f"🚀 Session started (model: {model})",
            ))

        elif msg_type == "assistant":
            usage = msg.get("message", {}).get("usage", {})
            total_input_tokens += usage.get("input_tokens", 0)
            total_output_tokens += usage.get("output_tokens", 0)

            content = msg.get("message", {}).get("content", [])
            for block in content:
                btype = block.get("type", "")

                if btype == "thinking":
                    thinking_text = block.get("thinking", "")
                    summary = thinking_text[:200]
                    if len(thinking_text) > 200:
                        summary += "…"
                    activities.append(ActivityEntry(
                        type="thinking",
                        summary=f"🧠 {summary}",
                        detail=thinking_text if len(thinking_text) > 200 else None,
                    ))

                elif btype == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    if tool_name == "Bash":
                        cmd = tool_input.get("command", "")
                        desc = tool_input.get("description", "")
                        detail = cmd if cmd else None
                        summary = f"🔧 Bash: {desc or cmd[:120]}"
                    elif tool_name == "Read":
                        fpath = tool_input.get("file_path", "")
                        summary = f"📖 Read: {fpath}"
                        detail = None
                    elif tool_name in ("Edit", "Write"):
                        fpath = tool_input.get("file_path", "")
                        summary = f"✏️ {tool_name}: {fpath}"
                        detail = None
                    elif tool_name == "TodoWrite":
                        todos = tool_input.get("todos", [])
                        in_progress = [t for t in todos if t.get("status") == "in_progress"]
                        completed = [t for t in todos if t.get("status") == "completed"]
                        summary = f"📋 Todos: {len(completed)} done, {len(in_progress)} in progress, {len(todos)} total"
                        detail = None
                    elif tool_name == "WebFetch":
                        url = tool_input.get("url", "")
                        summary = f"🌐 WebFetch: {url[:100]}"
                        detail = None
                    else:
                        input_str = json.dumps(tool_input)
                        summary = f"🔧 {tool_name}"
                        detail = input_str[:300] if len(input_str) > 0 else None
                    activities.append(ActivityEntry(
                        type="tool_use", summary=summary, detail=detail,
                    ))

                elif btype == "text":
                    text = block.get("text", "")
                    if text.strip():
                        truncated = text[:300]
                        if len(text) > 300:
                            truncated += "…"
                        activities.append(ActivityEntry(
                            type="text",
                            summary=f"💬 {truncated}",
                            detail=text if len(text) > 300 else None,
                        ))

        elif msg_type == "user":
            content_list = msg.get("message", {}).get("content", [])
            for block in content_list:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue
                is_error = block.get("is_error", False)

                tool_use_result = msg.get("tool_use_result", {})
                if not isinstance(tool_use_result, dict):
                    tool_use_result = {}
                stdout = tool_use_result.get("stdout", "")
                stderr = tool_use_result.get("stderr", "")
                interrupted = tool_use_result.get("interrupted", False)

                if interrupted:
                    actual = "⚠️ Interrupted"
                elif stdout or stderr:
                    actual = (stdout + ("\n" + stderr if stderr else "")).strip()
                else:
                    raw = block.get("content", "")
                    actual = raw if isinstance(raw, str) else json.dumps(raw)

                actual = actual.strip()
                icon = "❌" if is_error else "📤"
                if not actual:
                    summary = f"{icon} (empty result)"
                    detail = None
                elif len(actual) <= 200:
                    summary = f"{icon} {actual}"
                    detail = None
                else:
                    summary = f"{icon} {actual[:200]}…"
                    detail = actual

                activities.append(ActivityEntry(
                    type="tool_result", summary=summary, detail=detail,
                ))

        elif msg_type == "result":
            subtype = msg.get("subtype", "")
            duration_ms = msg.get("duration_ms", 0)
            cost = msg.get("total_cost_usd", 0.0)
            turns = msg.get("num_turns", 0)
            duration_s = round(duration_ms / 1000, 1) if duration_ms else 0
            total_cost_usd = cost

            usage = msg.get("usage", {})
            total_input_tokens = usage.get("input_tokens", total_input_tokens)
            total_output_tokens = usage.get("output_tokens", total_output_tokens)
            total_tokens = total_input_tokens + total_output_tokens

            emoji = "✅" if subtype == "success" else "❌"
            result_text = msg.get("result", "").strip()
            result_preview = f" — {result_text[:200]}" if result_text else ""
            cost_str = f"${cost:.4f}" if cost else ""
            activities.append(ActivityEntry(
                type="status",
                summary=f"{emoji} {subtype.title()} — {turns} turns, {duration_s}s{', ' + cost_str if cost_str else ''}, {total_tokens:,} tokens{result_preview}",
                detail=result_text if len(result_text) > 200 else None,
            ))

    trimmed = activities[-max_events:] if max_events > 0 else activities
    return {
        "activity": trimmed,
        "total_tokens": total_input_tokens + total_output_tokens,
        "total_cost_usd": total_cost_usd,
    }


def _count_messages(filepath: str) -> int:
    """Count total lines in a session JSONL."""
    try:
        with open(filepath) as f:
            return sum(1 for l in f if l.strip())
    except (OSError, IOError):
        return 0


# ---- Endpoints ----

@router.get("/status", response_model=MonitorOverview)
async def monitor_status(
    max_events: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get live monitor overview of all Claude Code activity.

    Returns:
      - Active dispatches and their session activity
      - Recently completed dispatches (last 5)
    """
    # Get active dispatches
    result = await db.execute(
        select(Dispatch)
        .where(or_(Dispatch.status == "queued", Dispatch.status == "running"))
        .order_by(Dispatch.created_at.desc())
    )
    active_dispatches = result.scalars().all()

    # Get recent completed/failed (last 5)
    result = await db.execute(
        select(Dispatch)
        .where(Dispatch.status.in_(["completed", "failed", "stopped"]))
        .order_by(Dispatch.completed_at.desc())
        .limit(5)
    )
    recent_dispatches = result.scalars().all()

    sessions: list[SessionStatus] = []
    recent_completed: list[SessionStatus] = []

    for dispatch in active_dispatches:
        task_title = None
        if dispatch.task_id:
            task_result = await db.execute(select(Task).where(Task.id == dispatch.task_id))
            task = task_result.scalar_one_or_none()
            if task:
                task_title = task.title

        activity = []
        total_messages = 0
        total_tokens = 0
        total_cost_usd = 0.0

        # Prefer stream-json DB output (has cost/token totals in result event)
        if dispatch.output:
            parsed = _parse_stream_json_output(dispatch.output)
            activity = parsed["activity"][-max_events:]  # trim for overview only
            total_tokens = parsed["total_tokens"]
            total_cost_usd = parsed["total_cost_usd"]
            total_messages = len(parsed["activity"])  # report true total

        # Fallback: try JSONL session file if no DB output
        if not activity:
            session_file = None
            if dispatch.session_id:
                session_file = _find_session_file(dispatch.session_id)
            if not session_file and dispatch.workdir:
                session_file = _find_latest_session_for_workdir(dispatch.workdir)
            if session_file:
                parsed = _parse_session_activity(session_file)
                activity = parsed["activity"][-max_events:]
                total_tokens = parsed["total_tokens"]
                total_cost_usd = parsed["total_cost_usd"]
                total_messages = len(parsed["activity"])

        # If still nothing, add a status-only entry
        if not activity:
            if dispatch.status == "queued":
                activity = [ActivityEntry(type="status", summary="⏳ Waiting in queue…")]
            elif dispatch.status == "running":
                activity = [ActivityEntry(type="status", summary="🚀 Running (no output yet)")]

        sessions.append(SessionStatus(
            dispatch_id=dispatch.id,
            task_id=dispatch.task_id,
            task_title=task_title,
            project_name=dispatch.project_name,
            dispatch_status=dispatch.status,
            session_id=dispatch.session_id,
            session_file=None,
            started_at=dispatch.started_at.isoformat() if dispatch.started_at else None,
            total_messages=total_messages,
            total_tokens=total_tokens,
            total_cost_usd=total_cost_usd,
            activity=activity,
        ))

    for dispatch in recent_dispatches:
        task_title = None
        if dispatch.task_id:
            task_result = await db.execute(select(Task).where(Task.id == dispatch.task_id))
            task = task_result.scalar_one_or_none()
            if task:
                task_title = task.title

        # For completed dispatches, just show summary (no need to parse full session)
        duration = ""
        if dispatch.started_at and dispatch.completed_at:
            delta = dispatch.completed_at - dispatch.started_at
            mins = int(delta.total_seconds() // 60)
            secs = int(delta.total_seconds() % 60)
            duration = f"{mins}m {secs}s"

        status_emoji = {"completed": "✅", "failed": "❌", "stopped": "⏸️"}.get(dispatch.status, "❓")
        summary = f"{status_emoji} {dispatch.status.title()}"
        if duration:
            summary += f" ({duration})"
        if dispatch.error_reason:
            summary += f" — {dispatch.error_reason[:100]}"

        # Quick cost/token scan from stream-json result event (no full parse needed)
        rec_tokens = 0
        rec_cost = 0.0
        if dispatch.output:
            for line in dispatch.output.splitlines():
                try:
                    ev = json.loads(line)
                    if ev.get("type") == "result":
                        rec_cost = ev.get("total_cost_usd", 0.0)
                        usage = ev.get("usage", {})
                        rec_tokens = (
                            usage.get("input_tokens", 0)
                            + usage.get("output_tokens", 0)
                            + usage.get("cache_read_input_tokens", 0)
                            + usage.get("cache_creation_input_tokens", 0)
                        )
                        break
                except Exception:
                    pass

        if rec_tokens > 0 or rec_cost > 0:
            summary += f" — 🪙 {rec_tokens:,} tokens, ${rec_cost:.4f}"

        recent_completed.append(SessionStatus(
            dispatch_id=dispatch.id,
            task_id=dispatch.task_id,
            task_title=task_title,
            project_name=dispatch.project_name,
            dispatch_status=dispatch.status,
            session_id=dispatch.session_id,
            started_at=dispatch.started_at.isoformat() if dispatch.started_at else None,
            total_messages=0,
            total_tokens=rec_tokens,
            total_cost_usd=rec_cost,
            activity=[ActivityEntry(type="status", summary=summary)],
        ))

    return MonitorOverview(
        has_active=len(active_dispatches) > 0,
        active_dispatches=len(active_dispatches),
        sessions=sessions,
        recent_completed=recent_completed,
    )


@router.get("/session/{dispatch_id}", response_model=SessionStatus)
async def session_detail(
    dispatch_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get full session activity for a specific dispatch (no event limit)."""
    result = await db.execute(select(Dispatch).where(Dispatch.id == dispatch_id))
    dispatch = result.scalar_one_or_none()
    if not dispatch:
        raise HTTPException(404, f"Dispatch #{dispatch_id} not found")

    task_title = None
    if dispatch.task_id:
        task_result = await db.execute(select(Task).where(Task.id == dispatch.task_id))
        task = task_result.scalar_one_or_none()
        if task:
            task_title = task.title

    activity = []
    total_messages = 0
    total_tokens = 0
    total_cost_usd = 0.0

    # Prefer stream-json DB output (richer: has cost/token totals in result event)
    if dispatch.output:
        parsed = _parse_stream_json_output(dispatch.output)  # no limit — return all
        activity = parsed["activity"]
        total_tokens = parsed["total_tokens"]
        total_cost_usd = parsed["total_cost_usd"]
        total_messages = len(activity)

    # Fallback: try JSONL session file
    if not activity:
        session_file = None
        if dispatch.session_id:
            session_file = _find_session_file(dispatch.session_id)
        if not session_file and dispatch.workdir:
            session_file = _find_latest_session_for_workdir(dispatch.workdir)
        if session_file:
            parsed = _parse_session_activity(session_file)  # no limit
            activity = parsed["activity"]
            total_tokens = parsed["total_tokens"]
            total_cost_usd = parsed["total_cost_usd"]
            total_messages = len(activity)

    return SessionStatus(
        dispatch_id=dispatch.id,
        task_id=dispatch.task_id,
        task_title=task_title,
        project_name=dispatch.project_name,
        dispatch_status=dispatch.status,
        session_id=dispatch.session_id,
        session_file=None,
        started_at=dispatch.started_at.isoformat() if dispatch.started_at else None,
        total_messages=total_messages,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd,
        activity=activity,
    )


@router.get("/processes")
async def list_processes():
    """List Claude-related processes on the host.
    
    Note: This only works if /proc is accessible (Linux host mount).
    Falls back to empty list inside Docker.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=5,
        )
        processes = []
        for line in result.stdout.splitlines():
            if "claude" in line.lower() and "grep" not in line:
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    processes.append({
                        "pid": parts[1],
                        "cpu": parts[2],
                        "mem": parts[3],
                        "stat": parts[7],
                        "command": parts[10][:200],
                    })
        return {"processes": processes}
    except Exception:
        return {"processes": [], "note": "Process listing not available inside container"}
