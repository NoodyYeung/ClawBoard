"""Project Settings API — per-project git strategy configuration."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import ProjectSettings
from schemas import ProjectSettingsResponse, ProjectSettingsUpdate, VALID_GIT_STRATEGIES

router = APIRouter(prefix="/api/project-settings", tags=["project-settings"])


@router.get("/{project_key}", response_model=ProjectSettingsResponse)
async def get_project_settings(project_key: str, db: AsyncSession = Depends(get_db)):
    """Get git strategy settings for a project. Returns defaults if not configured."""
    result = await db.execute(
        select(ProjectSettings).where(ProjectSettings.project_key == project_key)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        return ProjectSettingsResponse(project_key=project_key)
    return settings


@router.put("/{project_key}", response_model=ProjectSettingsResponse)
async def upsert_project_settings(
    project_key: str,
    body: ProjectSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Create or update git strategy settings for a project."""
    if body.git_strategy not in VALID_GIT_STRATEGIES:
        raise HTTPException(
            400,
            f"git_strategy must be one of: {VALID_GIT_STRATEGIES}",
        )

    result = await db.execute(
        select(ProjectSettings).where(ProjectSettings.project_key == project_key)
    )
    settings = result.scalar_one_or_none()

    if settings:
        settings.git_strategy = body.git_strategy
        settings.default_branch = body.default_branch
    else:
        settings = ProjectSettings(
            project_key=project_key,
            git_strategy=body.git_strategy,
            default_branch=body.default_branch,
        )
        db.add(settings)

    await db.commit()
    await db.refresh(settings)
    return settings
