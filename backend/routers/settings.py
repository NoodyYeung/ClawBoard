"""System Settings API — read/write key-value config stored in DB.

Endpoints:
  GET  /api/settings        → dict of all settings {key: value}
  PUT  /api/settings        → batch-update {settings: {key: value}}
  GET  /api/settings/{key}  → single SettingResponse
  PUT  /api/settings/{key}  → update single setting value
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import SystemSetting
from schemas import SettingResponse, SettingUpdate, SettingsBatchUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED_KEYS = {"llm_provider", "minimax_api_key", "minimax_base_url", "minimax_model"}
VALID_PROVIDERS = {"claude", "minimax"}


@router.get("", response_model=dict[str, str])
async def get_all_settings(db: AsyncSession = Depends(get_db)):
    """Return all settings as a flat {key: value} dict for easy consumption."""
    result = await db.execute(select(SystemSetting))
    rows = result.scalars().all()
    return {row.key: row.value for row in rows}


@router.put("", response_model=dict[str, str])
async def batch_update_settings(
    body: SettingsBatchUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple settings at once."""
    unknown = set(body.settings.keys()) - ALLOWED_KEYS
    if unknown:
        raise HTTPException(400, f"Unknown setting keys: {unknown}")

    if "llm_provider" in body.settings:
        if body.settings["llm_provider"] not in VALID_PROVIDERS:
            raise HTTPException(400, f"llm_provider must be one of: {VALID_PROVIDERS}")

    for key, value in body.settings.items():
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = value
            row.updated_at = datetime.now(timezone.utc)
        else:
            db.add(SystemSetting(key=key, value=value))

    await db.commit()

    result = await db.execute(select(SystemSetting))
    rows = result.scalars().all()
    return {row.key: row.value for row in rows}


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(key: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, f"Setting '{key}' not found")
    return row


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(key: str, body: SettingUpdate, db: AsyncSession = Depends(get_db)):
    if key not in ALLOWED_KEYS:
        raise HTTPException(400, f"Unknown setting key: '{key}'. Allowed: {ALLOWED_KEYS}")

    if key == "llm_provider" and body.value not in VALID_PROVIDERS:
        raise HTTPException(400, f"llm_provider must be one of: {VALID_PROVIDERS}")

    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, f"Setting '{key}' not found")

    row.value = body.value
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row
