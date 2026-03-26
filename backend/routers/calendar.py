"""Calendar API — independent OpenClaw calendar events + cron job overlay."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import CalendarEventModel, EventTag
from schemas import (
    CalendarEventCreate,
    CalendarEventResponse,
    CalendarEventUpdate,
    CalendarViewEvent,
    EventTagCreate,
    EventTagResponse,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

# Internal cron jobs hidden from the calendar frontend
HIDDEN_CRON_JOBS = {"clawboard-event-scanner", "clawboard-dispatch-runner"}

# OpenClaw cron jobs file
CRON_JOBS_PATH = os.environ.get(
    "OPENCLAW_CRON_PATH",
    str(Path.home() / ".openclaw" / "cron" / "jobs.json"),
)


def _read_cron_jobs() -> list[dict]:
    """Read OpenClaw cron jobs from jobs.json."""
    try:
        with open(CRON_JOBS_PATH, "r") as f:
            data = json.load(f)
        return data.get("jobs", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _expand_cron_occurrences(
    cron_expr: str,
    start: datetime,
    end: datetime,
) -> list[datetime]:
    """Expand a cron expression into concrete occurrences within [start, end]."""
    try:
        cron = croniter(cron_expr, start)
        occurrences = []
        while True:
            nxt = cron.get_next(datetime)
            if nxt > end:
                break
            occurrences.append(nxt)
            if len(occurrences) > 200:
                break
        return occurrences
    except (ValueError, KeyError):
        return []


# ===== Event Tags CRUD =====


@router.get("/tags", response_model=list[EventTagResponse])
async def list_tags(db: AsyncSession = Depends(get_db)):
    """List all event tags."""
    result = await db.execute(select(EventTag).order_by(EventTag.name))
    return result.scalars().all()


@router.post("/tags", response_model=EventTagResponse, status_code=201)
async def create_tag(tag: EventTagCreate, db: AsyncSession = Depends(get_db)):
    """Create a new event tag."""
    obj = EventTag(name=tag.name, color=tag.color)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an event tag."""
    result = await db.execute(select(EventTag).where(EventTag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.commit()


# ===== Calendar Events CRUD =====


@router.get("/items", response_model=list[CalendarEventResponse])
async def list_events(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    tag_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List calendar events, optionally filtered by date range and tag."""
    q = select(CalendarEventModel, EventTag).outerjoin(
        EventTag, CalendarEventModel.tag_id == EventTag.id
    )

    filters = []
    if start:
        range_start = datetime.fromisoformat(start)
        if range_start.tzinfo is None:
            range_start = range_start.replace(tzinfo=timezone.utc)
        filters.append(CalendarEventModel.scheduled_at >= range_start)
    if end:
        range_end = datetime.fromisoformat(end)
        if range_end.tzinfo is None:
            range_end = range_end.replace(tzinfo=timezone.utc)
        filters.append(CalendarEventModel.scheduled_at <= range_end)
    if tag_id:
        filters.append(CalendarEventModel.tag_id == tag_id)

    if filters:
        q = q.where(and_(*filters))

    q = q.order_by(CalendarEventModel.scheduled_at)
    result = await db.execute(q)

    events = []
    for row in result.all():
        evt = row[0]
        tag = row[1]
        events.append(CalendarEventResponse(
            id=evt.id,
            title=evt.title,
            prompt=evt.prompt,
            tag_id=evt.tag_id,
            tag_name=tag.name if tag else None,
            tag_color=tag.color if tag else None,
            scheduled_at=evt.scheduled_at,
            scheduled_end=evt.scheduled_end,
            is_triggered=evt.is_triggered,
            created_at=evt.created_at,
            updated_at=evt.updated_at,
        ))
    return events


@router.post("/items", response_model=CalendarEventResponse, status_code=201)
async def create_event(
    data: CalendarEventCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new calendar event."""
    obj = CalendarEventModel(
        title=data.title,
        prompt=data.prompt,
        tag_id=data.tag_id,
        scheduled_at=data.scheduled_at,
        scheduled_end=data.scheduled_end,
        is_triggered=data.is_triggered,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)

    tag = None
    if obj.tag_id:
        result = await db.execute(select(EventTag).where(EventTag.id == obj.tag_id))
        tag = result.scalar_one_or_none()

    return CalendarEventResponse(
        id=obj.id,
        title=obj.title,
        prompt=obj.prompt,
        tag_id=obj.tag_id,
        tag_name=tag.name if tag else None,
        tag_color=tag.color if tag else None,
        scheduled_at=obj.scheduled_at,
        scheduled_end=obj.scheduled_end,
        is_triggered=obj.is_triggered,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


@router.get("/items/{event_id}", response_model=CalendarEventResponse)
async def get_event(event_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single calendar event."""
    result = await db.execute(
        select(CalendarEventModel, EventTag)
        .outerjoin(EventTag, CalendarEventModel.tag_id == EventTag.id)
        .where(CalendarEventModel.id == event_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    evt, tag = row
    return CalendarEventResponse(
        id=evt.id,
        title=evt.title,
        prompt=evt.prompt,
        tag_id=evt.tag_id,
        tag_name=tag.name if tag else None,
        tag_color=tag.color if tag else None,
        scheduled_at=evt.scheduled_at,
        scheduled_end=evt.scheduled_end,
        is_triggered=evt.is_triggered,
        created_at=evt.created_at,
        updated_at=evt.updated_at,
    )


@router.put("/items/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    event_id: int, data: CalendarEventUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a calendar event."""
    result = await db.execute(
        select(CalendarEventModel).where(CalendarEventModel.id == event_id)
    )
    evt = result.scalar_one_or_none()
    if not evt:
        raise HTTPException(status_code=404, detail="Event not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(evt, field, value)

    await db.commit()
    await db.refresh(evt)

    tag = None
    if evt.tag_id:
        tag_result = await db.execute(select(EventTag).where(EventTag.id == evt.tag_id))
        tag = tag_result.scalar_one_or_none()

    return CalendarEventResponse(
        id=evt.id,
        title=evt.title,
        prompt=evt.prompt,
        tag_id=evt.tag_id,
        tag_name=tag.name if tag else None,
        tag_color=tag.color if tag else None,
        scheduled_at=evt.scheduled_at,
        scheduled_end=evt.scheduled_end,
        is_triggered=evt.is_triggered,
        created_at=evt.created_at,
        updated_at=evt.updated_at,
    )


@router.delete("/items/{event_id}", status_code=204)
async def delete_event(event_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a calendar event."""
    result = await db.execute(
        select(CalendarEventModel).where(CalendarEventModel.id == event_id)
    )
    evt = result.scalar_one_or_none()
    if not evt:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(evt)
    await db.commit()


# ===== Merged view: calendar events + OpenClaw cron =====


@router.get("/events", response_model=list[CalendarViewEvent])
async def get_calendar_view(
    start: Optional[str] = Query(None, description="ISO date start range"),
    end: Optional[str] = Query(None, description="ISO date end range"),
    include_cron: bool = Query(True, description="Include OpenClaw cron jobs"),
    tag_id: Optional[int] = Query(None, description="Filter by tag ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Merged calendar view:
    1. Calendar events (OpenClaw prompts) from the DB
    2. OpenClaw cron jobs (expanded into occurrences)
    """
    now = datetime.now(timezone.utc)
    if start:
        range_start = datetime.fromisoformat(start)
    else:
        range_start = now.replace(day=1) - timedelta(days=7)
    if end:
        range_end = datetime.fromisoformat(end)
    else:
        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
        range_end = next_month + timedelta(days=7)

    if range_start.tzinfo is None:
        range_start = range_start.replace(tzinfo=timezone.utc)
    if range_end.tzinfo is None:
        range_end = range_end.replace(tzinfo=timezone.utc)

    events: list[CalendarViewEvent] = []

    # ---- Source 1: Calendar events from DB ----
    q = select(CalendarEventModel, EventTag).outerjoin(
        EventTag, CalendarEventModel.tag_id == EventTag.id
    ).where(
        and_(
            CalendarEventModel.scheduled_at >= range_start,
            CalendarEventModel.scheduled_at <= range_end,
        )
    )
    if tag_id:
        q = q.where(CalendarEventModel.tag_id == tag_id)

    result = await db.execute(q)

    for row in result.all():
        evt, tag = row
        events.append(
            CalendarViewEvent(
                id=f"event-{evt.id}",
                title=evt.title,
                description=evt.prompt or "",
                start=evt.scheduled_at,
                end=evt.scheduled_end,
                source="event",
                tag_name=tag.name if tag else None,
                tag_color=tag.color if tag else None,
                color=tag.color if tag else "#6b7280",
                event_id=evt.id,
                is_triggered=evt.is_triggered,
            )
        )

    # ---- Source 2: OpenClaw cron jobs ----
    if include_cron and not tag_id:
        cron_jobs = _read_cron_jobs()
        for job in cron_jobs:
            if not job.get("enabled", True):
                continue

            name = job.get("name", "unnamed")
            is_scanner = name in HIDDEN_CRON_JOBS
            description = job.get("description", name)
            message = ""
            payload = job.get("payload", {})
            if isinstance(payload, dict):
                message = payload.get("message", "")

            schedule = job.get("schedule", {})
            schedule_kind = schedule.get("kind", "")

            cron_expr = schedule.get("expr") if schedule_kind == "cron" else None
            every_ms = schedule.get("everyMs") if schedule_kind == "every" else None
            at_ms = schedule.get("atMs") if schedule_kind == "at" else None

            if cron_expr:
                occurrences = _expand_cron_occurrences(cron_expr, range_start, range_end)
                for occ in occurrences:
                    events.append(
                        CalendarViewEvent(
                            id=f"cron-{name}-{occ.isoformat()}",
                            title=f"🔄 {description}",
                            description=message,
                            start=occ,
                            end=occ + timedelta(minutes=30),
                            source="cron",
                            cron_name=name,
                            cron_expr=cron_expr,
                            color="#8b5cf6" if not is_scanner else "#4b5563",
                            is_scanner=is_scanner,
                        )
                    )
            elif every_ms:
                interval = timedelta(milliseconds=every_ms)
                anchor_ms = schedule.get("anchorMs", 0)
                anchor = datetime.fromtimestamp(anchor_ms / 1000, tz=timezone.utc)

                if anchor < range_start:
                    intervals_skipped = int(
                        (range_start - anchor).total_seconds() * 1000 / every_ms
                    )
                    current = anchor + timedelta(milliseconds=intervals_skipped * every_ms)
                else:
                    current = anchor

                count = 0
                while current <= range_end and count < 200:
                    if current >= range_start:
                        if every_ms >= 86400000:
                            interval_label = f"every {every_ms // 86400000}d"
                        elif every_ms >= 3600000:
                            interval_label = f"every {every_ms // 3600000}h"
                        else:
                            interval_label = f"every {every_ms // 60000}m"

                        events.append(
                            CalendarViewEvent(
                                id=f"cron-{name}-{current.isoformat()}",
                                title=f"🔄 {description}",
                                description=message,
                                start=current,
                                end=current + timedelta(minutes=5),
                                source="cron",
                                cron_name=name,
                                cron_expr=interval_label,
                                color="#8b5cf6" if not is_scanner else "#4b5563",
                                is_scanner=is_scanner,
                            )
                        )
                        count += 1
                    current += interval
            elif at_ms:
                try:
                    at_dt = datetime.fromtimestamp(at_ms / 1000, tz=timezone.utc)
                    if range_start <= at_dt <= range_end:
                        events.append(
                            CalendarViewEvent(
                                id=f"cron-{name}-once",
                                title=f"⏰ {description}",
                                description=message,
                                start=at_dt,
                                end=at_dt + timedelta(minutes=30),
                                source="cron",
                                cron_name=name,
                                color="#f59e0b",
                                is_scanner=is_scanner,
                            )
                        )
                except (ValueError, TypeError, OSError):
                    pass

    events.sort(key=lambda e: e.start)
    return events


@router.get("/cron-jobs")
async def list_cron_jobs():
    """List raw OpenClaw cron jobs."""
    return _read_cron_jobs()
