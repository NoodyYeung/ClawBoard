from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from database import get_db
from models import Task, TaskMessage
from schemas import (
    TaskCreate, TaskUpdate, TaskResponse, TaskMove, StatusSummary,
    TaskMessageCreate, TaskMessageResponse, VALID_TASK_TYPES,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

VALID_STATUSES = ["planning", "planned", "in_progress", "testing", "review", "done"]


# ---- helper: append a message to the activity log ----
async def _add_message(
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


@router.get("/summary", response_model=StatusSummary)
async def status_summary(db: AsyncSession = Depends(get_db)):
    counts: dict[str, int] = {}
    for status in VALID_STATUSES:
        result = await db.execute(
            select(func.count(Task.id)).where(
                Task.status == status, Task.is_archived == False  # noqa: E712
            )
        )
        counts[status] = result.scalar() or 0

    archived_result = await db.execute(
        select(func.count(Task.id)).where(Task.is_archived == True)  # noqa: E712
    )
    counts["archived"] = archived_result.scalar() or 0
    return StatusSummary(**counts)


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    archived: bool = False,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Task).where(Task.is_archived == archived)  # noqa: E712
    if status:
        query = query.where(Task.status == status)
    if task_type:
        query = query.where(Task.task_type == task_type)
    query = query.order_by(Task.position, Task.created_at)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db)):
    if task.status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {VALID_STATUSES}")
    if task.task_type not in VALID_TASK_TYPES:
        raise HTTPException(400, f"Invalid task_type. Must be one of: {VALID_TASK_TYPES}")

    # Get max position for this status
    result = await db.execute(
        select(func.coalesce(func.max(Task.position), -1)).where(
            Task.status == task.status, Task.is_archived == False  # noqa: E712
        )
    )
    max_pos = result.scalar() or 0

    db_task = Task(
        title=task.title,
        description=task.description,
        status=task.status,
        position=max_pos + 1,
        project_name=task.project_name,
        task_type=task.task_type,
        task_meta=task.task_meta,
        scheduled_at=task.scheduled_at,
        scheduled_end=task.scheduled_end,
    )
    db.add(db_task)
    await db.flush()  # get the id

    await _add_message(db, db_task.id, "Task created", event_type="created")

    await db.commit()
    await db.refresh(db_task)
    return db_task


# ---- STATIC PUT ROUTES (must come before /{task_id} parametric routes) ----


@router.put("/reorder", response_model=list[TaskResponse])
async def reorder_tasks(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Bulk reorder tasks within a column.

    Body: { "task_ids": [3, 1, 5, 2] }
    Sets position = index for each task_id in the list.
    """
    task_ids = body.get("task_ids", [])
    if not task_ids or not isinstance(task_ids, list):
        raise HTTPException(400, "task_ids must be a non-empty list")

    updated = []
    for idx, tid in enumerate(task_ids):
        result = await db.execute(select(Task).where(Task.id == int(tid)))
        task = result.scalar_one_or_none()
        if task:
            task.position = idx
            updated.append(task)

    await db.commit()
    for t in updated:
        await db.refresh(t)
    return updated


# ---- PARAMETRIC ROUTES (/{task_id} patterns) ----


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int, task: TaskUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    db_task = result.scalar_one_or_none()
    if not db_task:
        raise HTTPException(404, "Task not found")

    update_data = task.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {VALID_STATUSES}")
    if "task_type" in update_data and update_data["task_type"] not in VALID_TASK_TYPES:
        raise HTTPException(400, f"Invalid task_type. Must be one of: {VALID_TASK_TYPES}")

    for key, value in update_data.items():
        setattr(db_task, key, value)

    await db.commit()
    await db.refresh(db_task)
    return db_task


@router.delete("/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    db_task = result.scalar_one_or_none()
    if not db_task:
        raise HTTPException(404, "Task not found")

    await db.delete(db_task)
    await db.commit()
    return {"ok": True}


@router.put("/{task_id}/move", response_model=TaskResponse)
async def move_task(
    task_id: int, move: TaskMove, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    db_task = result.scalar_one_or_none()
    if not db_task:
        raise HTTPException(404, "Task not found")

    if move.status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status")

    old_status = db_task.status
    db_task.status = move.status
    db_task.position = move.position
    db_task.is_archived = False

    # Auto-log the status change
    label_map = {
        "planning": "Planning", "planned": "Planned", "in_progress": "In Progress",
        "testing": "Testing", "review": "Review", "done": "Done",
    }
    auto_msg = f"Moved from {label_map.get(old_status, old_status)} → {label_map.get(move.status, move.status)}"
    if move.message:
        auto_msg += f": {move.message}"

    await _add_message(
        db, task_id,
        message=auto_msg,
        author=move.author or "system",
        event_type="status_change",
        status_from=old_status,
        status_to=move.status,
    )

    await db.commit()
    await db.refresh(db_task)
    return db_task


@router.put("/{task_id}/archive", response_model=TaskResponse)
async def archive_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    db_task = result.scalar_one_or_none()
    if not db_task:
        raise HTTPException(404, "Task not found")

    was_archived = db_task.is_archived
    db_task.is_archived = not db_task.is_archived

    action = "Restored from archive" if was_archived else "Archived"
    await _add_message(db, task_id, action, event_type="archive")

    await db.commit()
    await db.refresh(db_task)
    return db_task


# ---- Task Messages endpoints ----

@router.get("/{task_id}/messages", response_model=list[TaskMessageResponse])
async def list_messages(task_id: int, db: AsyncSession = Depends(get_db)):
    # Verify task exists
    task_result = await db.execute(select(Task).where(Task.id == task_id))
    if not task_result.scalar_one_or_none():
        raise HTTPException(404, "Task not found")

    result = await db.execute(
        select(TaskMessage)
        .where(TaskMessage.task_id == task_id)
        .order_by(TaskMessage.created_at.asc())
    )
    return result.scalars().all()


@router.post("/{task_id}/messages", response_model=TaskMessageResponse, status_code=201)
async def add_message(
    task_id: int, msg: TaskMessageCreate, db: AsyncSession = Depends(get_db)
):
    """Append a message to a task's activity log. Never replaces existing messages."""
    task_result = await db.execute(select(Task).where(Task.id == task_id))
    if not task_result.scalar_one_or_none():
        raise HTTPException(404, "Task not found")

    db_msg = TaskMessage(
        task_id=task_id,
        message=msg.message,
        author=msg.author,
        event_type=msg.event_type,
    )
    db.add(db_msg)
    await db.commit()
    await db.refresh(db_msg)
    return db_msg
