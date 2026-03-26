"""Dispatch API — bridge between ClawBoard tasks and Claude Code execution.

Flow:
  1. POST /api/dispatch/{task_id}  → queue a dispatch, move task planned→in_progress
  2. Host watcher polls GET /api/dispatch/pending → picks up queued dispatches
  3. Host runs Claude Code with the prompt
  4. Claude Code Stop hook fires → POST /api/dispatch/callback
  5. API updates dispatch + task status (→testing on success, stays in_progress on fail)
  6. POST /api/dispatch/timeout-stale → auto-fail dispatches running > timeout
"""

import os
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Dispatch, Task, TaskMessage, ProjectSettings
from schemas import DispatchCreate, DispatchResponse, DispatchCallback
from services.email_service import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dispatch", tags=["dispatch"])

# Project root on the host (for building workdir paths)
HOST_PROJECTS_ROOT = os.environ.get(
    "HOST_PROJECTS_ROOT",
    "/home/noody/Projects/Moltbot_ClaudeCode/ClaudeCodeProject",
)

VALID_DISPATCH_STATUSES = {"queued", "running", "completed", "failed", "stopped"}
VALID_AGENT_MODES = {"dev-task", "claude-teams"}

# Path to the Video Editor skill (used for auto-generating prompts)
VIDEO_EDITOR_SKILL_PATH = os.environ.get(
    "VIDEO_EDITOR_SKILL_PATH",
    "/home/noody/Projects/Moltbot_ClaudeCode/skills/video-editor/SKILL.md",
)

# Dispatch is considered stale/stuck if running longer than this
STALE_TIMEOUT_MINUTES = int(os.environ.get("DISPATCH_STALE_TIMEOUT_MINUTES", "30"))


# ---- Helper: add task message ----
async def _log_task_message(
    db: AsyncSession,
    task_id: int,
    message: str,
    author: str = "system",
    event_type: str = "comment",
    status_from: str | None = None,
    status_to: str | None = None,
):
    msg = TaskMessage(
        task_id=task_id,
        message=message,
        author=author,
        event_type=event_type,
        status_from=status_from,
        status_to=status_to,
    )
    db.add(msg)


def _extract_pr_url(output: str) -> str | None:
    """Extract a GitHub pull request URL from dispatch output text."""
    # Match patterns like https://github.com/<owner>/<repo>/pull/<number>
    match = re.search(r"https://github\.com/[^\s]+/pull/\d+", output)
    return match.group(0) if match else None


def _send_dispatch_email(
    status: str,
    task_title: str,
    dispatch_id: int,
    output: str = "",
    error_reason: str = "",
    output_summary: str = "",
):
    """Fire-and-forget email notification for dispatch status changes.

    Runs synchronously but is fast (~1-2s for SMTP).
    Failures are logged but never block the callback response.
    """
    try:
        svc = EmailService()
        if not svc.app_password:
            logger.debug("Email not configured (no GOOGLE_APP_PASSWORD) — skipping notification")
            return

        if status == "completed":
            pr_url = _extract_pr_url(output)
            if pr_url:
                svc.send_pr_notification(
                    task_title=task_title,
                    pr_url=pr_url,
                    dispatch_id=dispatch_id,
                    output_summary=output_summary[-300:] if output_summary else "",
                )
            else:
                # Completed but no PR URL found — send a completion-only email
                svc.send(
                    subject=f"✅ Task Completed: {task_title}",
                    html_body=svc._build_completed_html(
                        task_title=task_title,
                        dispatch_id=dispatch_id,
                        output_summary=output_summary[-300:] if output_summary else "",
                    ),
                )

        elif status in ("failed", "stopped"):
            svc.send_dispatch_status(
                task_title=task_title,
                status=status,
                dispatch_id=dispatch_id,
                error_reason=error_reason,
                output_summary=output_summary[-300:] if output_summary else "",
            )
    except Exception as e:
        logger.error(f"Email notification failed (non-blocking): {e}")


def _build_video_editing_prompt(task_meta: dict, task_title: str) -> str:
    """Generate a Video Editor skill prompt from task_meta fields."""
    input_files = task_meta.get("input_files", [])
    description = task_meta.get("description", task_title)
    target_size_mb = task_meta.get("target_size_mb", 8)
    target_duration_s = task_meta.get("target_duration_s", 90)
    output_path = task_meta.get("output_path", "/tmp/video-edit-output/final_output.mp4")

    files_list = "\n".join(f"  - {f}" for f in input_files) if input_files else "  (no input files specified)"

    return (
        f"You are a video editor. Follow the Video Editor pipeline from the skill at {VIDEO_EDITOR_SKILL_PATH}.\n\n"
        f"INPUT FILES:\n{files_list}\n\n"
        f"DESCRIPTION: {description}\n\n"
        f"OUTPUT: {output_path}\n"
        f"TARGET: <{target_size_mb}MB, ~{target_duration_s}s duration\n\n"
        "Follow all steps in the Video Editor skill: probe, extract frames, analyze, cut segments, "
        "normalize, generate captions, concat, and compress.\n\n"
        "When completely finished, run:\n"
        f'openclaw system event --text "Done: Video editing complete. Output: {output_path}" --mode now'
    )


# ============================================================
# STATIC PATH ROUTES FIRST (before parameterized /{id} routes)
# ============================================================


@router.get("/pending", response_model=list[DispatchResponse])
async def list_pending(db: AsyncSession = Depends(get_db)):
    """Return all queued dispatches for the host watcher to pick up."""
    result = await db.execute(
        select(Dispatch)
        .where(Dispatch.status == "queued")
        .order_by(Dispatch.created_at)
    )
    return result.scalars().all()


@router.get("/active", response_model=list[DispatchResponse])
async def list_active(db: AsyncSession = Depends(get_db)):
    """Return all active (queued + running) dispatches."""
    result = await db.execute(
        select(Dispatch)
        .where(or_(Dispatch.status == "queued", Dispatch.status == "running"))
        .order_by(Dispatch.created_at.desc())
    )
    return result.scalars().all()


@router.get("/history", response_model=list[DispatchResponse])
async def list_history(
    task_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return dispatch history, optionally filtered by task_id."""
    q = select(Dispatch).order_by(Dispatch.created_at.desc()).limit(limit)
    if task_id:
        q = q.where(Dispatch.task_id == task_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.put("/output/{dispatch_id}", response_model=DispatchResponse)
async def update_output(
    dispatch_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Stream/update output for a running dispatch.

    Called periodically by dispatch-watcher.sh to push partial output to the DB
    so the frontend can show live progress. This replaces the fragile shared-file
    approach with a DB-centric one.

    Body: {"output": "...", "append": false}
      - append=false (default): replace output entirely (snapshot mode)
      - append=true: append to existing output (streaming mode)
    """
    result = await db.execute(select(Dispatch).where(Dispatch.id == dispatch_id))
    dispatch = result.scalar_one_or_none()
    if not dispatch:
        raise HTTPException(404, f"Dispatch #{dispatch_id} not found")

    new_output = body.get("output", "")
    append = body.get("append", False)

    if append and dispatch.output:
        dispatch.output = (dispatch.output + new_output)[-10000:]
    else:
        dispatch.output = new_output[-10000:] if new_output else new_output

    await db.commit()
    await db.refresh(dispatch)
    return dispatch


@router.post("/timeout-stale", response_model=list[DispatchResponse])
async def timeout_stale_dispatches(
    timeout_minutes: int = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Auto-fail dispatches that have been 'running' longer than the timeout.

    This catches cases where Claude Code crashes without firing the callback
    (e.g., API credit errors, OOM, network issues). The dispatch-runner should
    call this before checking for queued work.

    Returns the list of dispatches that were timed out.
    """
    timeout = timeout_minutes or STALE_TIMEOUT_MINUTES
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout)

    result = await db.execute(
        select(Dispatch).where(
            Dispatch.status == "running",
            Dispatch.started_at < cutoff,
        )
    )
    stale = result.scalars().all()

    timed_out = []
    for dispatch in stale:
        dispatch.status = "failed"
        dispatch.completed_at = datetime.now(timezone.utc)
        dispatch.error_reason = (
            f"Timed out: running for >{timeout} minutes with no response. "
            "Likely crashed before callback could fire."
        )

        if dispatch.task_id:
            # Move task back to planned so scanner can re-dispatch
            task_result = await db.execute(
                select(Task).where(Task.id == dispatch.task_id)
            )
            task = task_result.scalar_one_or_none()
            if task and task.status == "in_progress":
                task.status = "planned"
                await _log_task_message(
                    db, dispatch.task_id,
                    message=(
                        f"⏰ Dispatch #{dispatch.id} timed out after {timeout} min — "
                        f"marking as failed and returning task to planned for retry"
                    ),
                    author="system",
                    event_type="status_change",
                    status_from="in_progress",
                    status_to="planned",
                )
            elif task:
                await _log_task_message(
                    db, dispatch.task_id,
                    message=(
                        f"⏰ Dispatch #{dispatch.id} timed out after {timeout} min — "
                        f"marking dispatch as failed"
                    ),
                    author="system",
                    event_type="comment",
                )

        timed_out.append(dispatch)

    if timed_out:
        await db.commit()
        for d in timed_out:
            await db.refresh(d)

    return timed_out


@router.post("/callback", response_model=DispatchResponse)
async def dispatch_callback(
    body: DispatchCallback,
    db: AsyncSession = Depends(get_db),
):
    """Called by the Claude Code Stop hook when a dispatch finishes.

    Status transitions:
      - completed (exit_code=0) → task moves in_progress → testing
      - failed    (exit_code≠0) → task stays in_progress, error logged
      - stopped   (interrupted) → task stays in_progress, reason logged
    """
    result = await db.execute(select(Dispatch).where(Dispatch.id == body.dispatch_id))
    dispatch = result.scalar_one_or_none()
    if not dispatch:
        raise HTTPException(404, f"Dispatch #{body.dispatch_id} not found")

    # Allow output update on already-completed dispatches (the dispatch-watcher.sh
    # sends the authoritative callback AFTER tee finishes; the hook may have sent
    # an earlier callback with empty output due to pipe-flush race)
    if dispatch.status in ("completed", "failed", "stopped"):
        if body.output and len(body.output.strip()) > len((dispatch.output or "").strip()):
            dispatch.output = body.output[:10000]
            await db.commit()
            await db.refresh(dispatch)
        return dispatch

    dispatch.status = body.status
    dispatch.completed_at = datetime.now(timezone.utc)
    dispatch.exit_code = body.exit_code
    if body.output:
        dispatch.output = body.output[:10000]
    if body.error_reason:
        dispatch.error_reason = body.error_reason
    if body.session_id:
        dispatch.session_id = body.session_id

    task_id = body.task_id or dispatch.task_id
    if not task_id:
        await db.commit()
        await db.refresh(dispatch)
        return dispatch

    task_result = await db.execute(select(Task).where(Task.id == task_id))
    task = task_result.scalar_one_or_none()

    if not task:
        await db.commit()
        await db.refresh(dispatch)
        return dispatch

    output_summary = ""
    if body.output:
        output_summary = body.output[-500:].strip()

    if body.status == "completed":
        old_status = task.status
        task.status = "testing"
        msg = f"✅ Claude Code completed (dispatch #{dispatch.id})"
        if output_summary:
            msg += f"\n\n📝 Output summary:\n```\n{output_summary}\n```"
        await _log_task_message(
            db, task_id,
            message=msg,
            author="claude-code",
            event_type="status_change",
            status_from=old_status,
            status_to="testing",
        )

    elif body.status == "failed":
        reason = body.error_reason or f"Exit code: {body.exit_code}"
        msg = f"❌ Claude Code failed (dispatch #{dispatch.id})\n\n"
        msg += f"**Reason:** {reason}"
        if output_summary:
            msg += f"\n\n📝 Last output:\n```\n{output_summary}\n```"

        # Always move task back to planned for auto-retry
        old_status = task.status
        task.status = "planned"
        msg += f"\n\n🔄 Task moved back to **planned** for auto-retry (attempt {dispatch.retry_count + 1})"
        await _log_task_message(
            db, task_id,
            message=msg,
            author="claude-code",
            event_type="status_change",
            status_from=old_status,
            status_to="planned",
        )

    elif body.status == "stopped":
        reason = body.error_reason or "Task was stopped (possible budget limit or connection loss)"
        msg = f"⏸️ Claude Code stopped (dispatch #{dispatch.id})\n\n"
        msg += f"**Reason:** {reason}"
        if output_summary:
            msg += f"\n\n📝 Last output:\n```\n{output_summary}\n```"
        await _log_task_message(
            db, task_id,
            message=msg,
            author="claude-code",
            event_type="comment",
        )

    # ── Email Notification ──────────────────────────────────────
    _send_dispatch_email(
        status=body.status,
        task_title=task.title if task else f"Task #{task_id}",
        dispatch_id=dispatch.id,
        output=body.output or "",
        error_reason=body.error_reason or "",
        output_summary=output_summary,
    )

    await db.commit()
    await db.refresh(dispatch)
    return dispatch


@router.post("/run-now")
async def run_now_trigger():
    """Write a trigger file so the host watcher picks up queued dispatches immediately.

    The host mounts ~/Projects/Moltbot_ClaudeCode/data as /data in the API container.
    The dispatch-watcher.sh polls this file every second during its sleep interval.
    """
    import pathlib
    trigger = pathlib.Path("/data/dispatch-trigger")
    try:
        trigger.parent.mkdir(parents=True, exist_ok=True)
        trigger.touch()
        return {"triggered": True, "message": "Dispatch watcher will run within 1 second"}
    except Exception as e:
        return {"triggered": False, "message": str(e)}


# ============================================================
# PARAMETERIZED ROUTES (/{id} patterns — must come AFTER static routes)
# ============================================================


@router.post("/{task_id}", response_model=DispatchResponse, status_code=201)
async def create_dispatch(
    task_id: int,
    body: DispatchCreate,
    db: AsyncSession = Depends(get_db),
):
    """Queue a task for Claude Code execution."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    dispatchable = {"planned", "planning", "in_progress"}
    if task.status not in dispatchable:
        raise HTTPException(
            400,
            f"Task is in '{task.status}' — can only dispatch from: {dispatchable}",
        )

    active_check = await db.execute(
        select(Dispatch).where(
            Dispatch.task_id == task_id,
            or_(Dispatch.status == "queued", Dispatch.status == "running"),
        )
    )
    if active_check.scalar_one_or_none():
        raise HTTPException(409, "Task already has an active dispatch")

    agent_mode = body.agent_mode or "dev-task"
    if agent_mode not in VALID_AGENT_MODES:
        raise HTTPException(400, f"agent_mode must be one of: {VALID_AGENT_MODES}")

    # For video-editing tasks, auto-generate prompt from task_meta
    is_video_editing = getattr(task, "task_type", "coding") == "video-editing"

    if is_video_editing and not body.prompt:
        task_meta = getattr(task, "task_meta", None) or {}
        prompt = _build_video_editing_prompt(task_meta, task.title)
    else:
        prompt = body.prompt or task.description or task.title

    if not prompt.strip():
        raise HTTPException(400, "No prompt available — add a description or provide a prompt")

    # Resolve project_name early (needed for git strategy lookup below)
    project_name = body.project_name or task.project_name

    # Look up project git strategy from project_settings table
    project_key = project_name or None
    git_strategy = "direct_commit"
    default_branch = "main"
    if project_key:
        ps_result = await db.execute(
            select(ProjectSettings).where(ProjectSettings.project_key == project_key)
        )
        ps = ps_result.scalar_one_or_none()
        if ps:
            git_strategy = ps.git_strategy
            default_branch = ps.default_branch

    # Build git workflow instructions based on strategy
    if git_strategy == "pull_request":
        git_instructions = (
            "\n\n---\n"
            "## MANDATORY: Git & PR Workflow\n\n"
            f"### Step 1: BEFORE writing any code — sync and branch\n"
            "Run this FIRST, before making any changes:\n"
            "```bash\n"
            f"git checkout {default_branch} && git pull origin {default_branch} && "
            "git checkout -b feat/task-{{TASK_ID}}-<short-description>\n"
            "```\n\n"
            "### Step 2: Do your work\n"
            "Make all code changes on the feature branch.\n\n"
            "### Step 3: Commit\n"
            "```bash\n"
            "git add -A && git commit -m \"<type>: <description>\"\n"
            "```\n\n"
            "### Step 4: Push the branch\n"
            "GITHUB_TOKEN is available in your environment. Use it directly for git push:\n"
            "```bash\n"
            "REPO=$(git remote get-url origin | sed 's|.*github.com[:/]||;s|\\.git$||')\n"
            "git push https://x-access-token:${GITHUB_TOKEN}@github.com/${REPO}.git HEAD\n"
            "```\n"
            "If GITHUB_TOKEN is empty, try: git push -u origin HEAD\n\n"
            "### Step 5: Create PR via API\n"
            "**DO NOT use `gh` CLI. Use this curl command:**\n"
            "```bash\n"
            "REPO=$(git remote get-url origin | sed 's|.*github.com[:/]||;s|\\.git$||')\n"
            "BRANCH=$(git rev-parse --abbrev-ref HEAD)\n"
            "curl -sf -X POST http://localhost:8100/api/github/pr \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            f"  -d \"{{\\\"repo\\\":\\\"$REPO\\\",\\\"head\\\":\\\"$BRANCH\\\",\\\"base\\\":\\\"{default_branch}\\\","
            "\\\"title\\\":\\\"feat: <title>\\\",\\\"body\\\":\\\"## Summary\\\\n<describe changes>\\\\n\\\\n"
            "Generated by Claude Code via OpenClaw\\\"}}\"\n"
            "```\n\n"
            "The API returns JSON with `number` and `html_url` of the created PR.\n"
            f"NEVER push directly to `{default_branch}`. Always use a feature branch.\n\n"
            "### Step 6: Mark Task as Completed\n"
            "**MANDATORY:** You must report your success to the ClawBoard API so the task moves to testing.\n"
            "```bash\n"
            "curl -sf -X POST http://localhost:8100/api/dispatch/callback \\\n"
            "  -H \"Content-Type: application/json\" \\\n"
            "  -d \"{\\\"dispatch_id\\\": {{DISPATCH_ID}}, \\\"status\\\": \\\"completed\\\", \\\"exit_code\\\": 0}\"\n"
            "```\n"
        )
    else:
        git_instructions = (
            "\n\n---\n"
            f"## MANDATORY: Git Workflow (Direct Commit to {default_branch})\n\n"
            f"### Step 1: BEFORE writing any code — sync {default_branch}\n"
            "Run this FIRST, before making any changes:\n"
            "```bash\n"
            f"git checkout {default_branch} && git pull origin {default_branch} 2>/dev/null || git checkout {default_branch}\n"
            "```\n\n"
            "### Step 2: Do your work\n"
            f"Make all code changes directly on {default_branch}.\n\n"
            "### Step 3: Commit\n"
            "```bash\n"
            "git add -A && git commit -m \"<type>: <description>\"\n"
            "```\n\n"
            f"### Step 4: Push to {default_branch}\n"
            "GITHUB_TOKEN is available in your environment. Push directly:\n"
            "```bash\n"
            "REPO=$(git remote get-url origin | sed 's|.*github.com[:/]||;s|\\.git$||')\n"
            f"git push https://x-access-token:${{GITHUB_TOKEN}}@github.com/${{REPO}}.git {default_branch}\n"
            "```\n"
            f"If GITHUB_TOKEN is empty, try: git push origin {default_branch}\n\n"
            f"**IMPORTANT: Push directly to {default_branch}. Do NOT create feature branches or PRs.**\n\n"
            "### Step 5: Mark Task as Completed\n"
            "**MANDATORY:** You must report your success to the ClawBoard API so the task moves to testing.\n"
            "```bash\n"
            "curl -sf -X POST http://localhost:8100/api/dispatch/callback \\\n"
            "  -H \"Content-Type: application/json\" \\\n"
            "  -d \"{\\\"dispatch_id\\\": {{DISPATCH_ID}}, \\\"status\\\": \\\"completed\\\", \\\"exit_code\\\": 0}\"\n"
            "```\n"
        )

    # Calculate retry_count: count previous failed dispatches for this task (informational only, no cap)
    prev_failed = await db.execute(
        select(func.count(Dispatch.id))
        .where(
            Dispatch.task_id == task_id,
            Dispatch.status == "failed",
        )
    )
    failed_count = prev_failed.scalar() or 0

    workdir = None
    # project_name already resolved above for git strategy lookup
    if project_name:
        workdir = f"{HOST_PROJECTS_ROOT}/{project_name}"

    dispatch = Dispatch(
        task_id=task_id,
        status="queued",
        prompt=prompt,  # We will append instructions after getting the ID
        project_name=project_name,
        workdir=workdir,
        agent_mode=agent_mode,
        retry_count=failed_count,
    )
    db.add(dispatch)
    await db.flush()

    # Inject the actual dispatch/task ID into the instructions (skip for non-coding tasks)
    if is_video_editing:
        dispatch.prompt = prompt
    else:
        final_instructions = git_instructions.replace(
            "{{DISPATCH_ID}}", str(dispatch.id)
        ).replace(
            "{{TASK_ID}}", str(task_id)
        )
        dispatch.prompt = prompt + final_instructions

    old_status = task.status
    if old_status != "in_progress":
        task.status = "in_progress"
        await _log_task_message(
            db, task_id,
            message=f"Dispatched to Claude Code ({agent_mode}) — dispatch #{dispatch.id}",
            author="openclaw",
            event_type="status_change",
            status_from=old_status,
            status_to="in_progress",
        )
    else:
        await _log_task_message(
            db, task_id,
            message=f"Re-dispatched to Claude Code ({agent_mode}) — dispatch #{dispatch.id}",
            author="openclaw",
            event_type="comment",
        )

    await db.commit()
    await db.refresh(dispatch)
    return dispatch


@router.put("/{dispatch_id}/start", response_model=DispatchResponse)
async def mark_started(
    dispatch_id: int,
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Host watcher calls this when it picks up a dispatch and starts Claude Code."""
    result = await db.execute(select(Dispatch).where(Dispatch.id == dispatch_id))
    dispatch = result.scalar_one_or_none()
    if not dispatch:
        raise HTTPException(404, "Dispatch not found")

    dispatch.status = "running"
    dispatch.started_at = datetime.now(timezone.utc)
    if session_id:
        dispatch.session_id = session_id

    if dispatch.task_id:
        await _log_task_message(
            db, dispatch.task_id,
            message=f"🚀 Claude Code started working (dispatch #{dispatch.id})",
            author="claude-code",
            event_type="comment",
        )

    await db.commit()
    await db.refresh(dispatch)
    return dispatch


@router.get("/{dispatch_id}", response_model=DispatchResponse)
async def get_dispatch(dispatch_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single dispatch record with full output."""
    result = await db.execute(select(Dispatch).where(Dispatch.id == dispatch_id))
    dispatch = result.scalar_one_or_none()
    if not dispatch:
        raise HTTPException(404, "Dispatch not found")
    return dispatch
