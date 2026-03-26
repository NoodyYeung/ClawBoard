from pydantic import BaseModel
from datetime import datetime
from typing import Any, Optional

VALID_TASK_TYPES = ["coding", "video-editing", "research", "design"]


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "planned"
    project_name: Optional[str] = None
    task_type: str = "coding"
    task_meta: Optional[dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    position: Optional[int] = None
    is_archived: Optional[bool] = None
    project_name: Optional[str] = None
    task_type: Optional[str] = None
    task_meta: Optional[dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    status: str
    position: int
    is_archived: bool
    project_name: Optional[str] = None
    task_type: str = "coding"
    task_meta: Optional[dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    cron_job_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskMove(BaseModel):
    status: str
    position: int
    message: Optional[str] = None
    author: Optional[str] = "system"


class StatusSummary(BaseModel):
    planning: int = 0
    planned: int = 0
    in_progress: int = 0
    testing: int = 0
    review: int = 0
    done: int = 0
    archived: int = 0


# ---- Event Tags ----

class EventTagCreate(BaseModel):
    name: str
    color: str = "#3b82f6"


class EventTagResponse(BaseModel):
    id: int
    name: str
    color: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Calendar Events (OpenClaw scheduler) ----

class CalendarEventCreate(BaseModel):
    title: str
    prompt: str = ""
    tag_id: Optional[int] = None
    scheduled_at: datetime
    scheduled_end: Optional[datetime] = None
    is_triggered: bool = False


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    prompt: Optional[str] = None
    tag_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    is_triggered: Optional[bool] = None


class CalendarEventResponse(BaseModel):
    id: int
    title: str
    prompt: str
    tag_id: Optional[int] = None
    tag_name: Optional[str] = None
    tag_color: Optional[str] = None
    scheduled_at: datetime
    scheduled_end: Optional[datetime] = None
    is_triggered: bool
    created_at: datetime
    updated_at: datetime


# ---- Merged calendar view (events + cron) ----

class CalendarViewEvent(BaseModel):
    id: str  # "event-{id}" or "cron-{name}"
    title: str
    description: str = ""
    start: datetime
    end: Optional[datetime] = None
    source: str  # "event" or "cron"
    tag_name: Optional[str] = None
    tag_color: Optional[str] = None
    cron_name: Optional[str] = None
    cron_expr: Optional[str] = None
    color: Optional[str] = None
    is_scanner: bool = False
    event_id: Optional[int] = None
    is_triggered: bool = False


# ---- Task Messages (append-only activity log) ----

class TaskMessageCreate(BaseModel):
    message: str
    author: str = "user"
    event_type: str = "comment"


class TaskMessageResponse(BaseModel):
    id: int
    task_id: int
    message: str
    author: str
    event_type: str
    status_from: Optional[str] = None
    status_to: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Dispatch (ClawBoard ↔ Claude Code) ----

class DispatchCreate(BaseModel):
    prompt: Optional[str] = None  # override task description
    project_name: Optional[str] = None
    agent_mode: str = "dev-task"  # dev-task | claude-teams


class DispatchResponse(BaseModel):
    id: int
    task_id: Optional[int] = None
    status: str
    prompt: str
    project_name: Optional[str] = None
    workdir: Optional[str] = None
    agent_mode: str
    session_id: Optional[str] = None
    exit_code: Optional[int] = None
    output: Optional[str] = None
    error_reason: Optional[str] = None
    retry_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DispatchCallback(BaseModel):
    dispatch_id: int
    task_id: Optional[int] = None
    status: str  # completed | failed | stopped
    output: Optional[str] = None
    exit_code: Optional[int] = None
    error_reason: Optional[str] = None
    session_id: Optional[str] = None


# ---- Project Settings (git strategy) ----

VALID_GIT_STRATEGIES = ["direct_commit", "pull_request"]


class ProjectSettingsResponse(BaseModel):
    project_key: str
    git_strategy: str = "direct_commit"
    default_branch: str = "main"

    model_config = {"from_attributes": True}


class ProjectSettingsUpdate(BaseModel):
    git_strategy: str = "direct_commit"
    default_branch: str = "main"


# ---- System Settings ----

class SettingResponse(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class SettingUpdate(BaseModel):
    value: str


class SettingsBatchUpdate(BaseModel):
    """Update multiple settings at once: {key: value, ...}"""
    settings: dict[str, str]
