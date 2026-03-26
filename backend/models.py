from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(String(50), nullable=False, default="planned")
    position = Column(Integer, nullable=False, default=0)
    is_archived = Column(Boolean, nullable=False, default=False)
    project_name = Column(String(255), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_end = Column(DateTime(timezone=True), nullable=True)
    task_type = Column(String(50), nullable=False, default="coding", server_default="coding")
    task_meta = Column(JSONB, nullable=True)
    cron_job_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TaskMessage(Base):
    __tablename__ = "task_messages"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    message = Column(Text, nullable=False)
    author = Column(String(100), nullable=False, default="system")
    event_type = Column(String(50), nullable=False, default="comment")
    status_from = Column(String(50), nullable=True)
    status_to = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EventTag(Base):
    __tablename__ = "event_tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(60), nullable=False, unique=True)
    color = Column(String(9), nullable=False, default="#3b82f6")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CalendarEventModel(Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    prompt = Column(Text, nullable=False, default="")
    tag_id = Column(Integer, ForeignKey("event_tags.id", ondelete="SET NULL"), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    scheduled_end = Column(DateTime(timezone=True), nullable=True)
    is_triggered = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False, default="")
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProjectSettings(Base):
    __tablename__ = "project_settings"

    id = Column(Integer, primary_key=True, index=True)
    project_key = Column(String(500), nullable=False, unique=True)
    git_strategy = Column(String(50), nullable=False, default="direct_commit")
    default_branch = Column(String(100), nullable=False, default="main")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Dispatch(Base):
    __tablename__ = "dispatches"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), nullable=False, default="queued")
    prompt = Column(Text, nullable=False, default="")
    project_name = Column(String(255), nullable=True)
    workdir = Column(String(500), nullable=True)
    agent_mode = Column(String(50), nullable=False, default="dev-task")
    session_id = Column(String(100), nullable=True)
    exit_code = Column(Integer, nullable=True)
    output = Column(Text, nullable=True)
    error_reason = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
