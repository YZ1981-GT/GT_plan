"""Feature flags API（DB-backed，admin 认证）。

# Feature: zero-downtime-deployment, Component 8

此 API 提供基于数据库的 feature flag 灰度管理（区别于旧 app/routers/feature_flags.py 的内存开关）。
DB 为唯一权威源，支持百分比灰度、白名单、即时生效（≤5s TTL）。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.feature_flag_service import FeatureFlagService

router = APIRouter(prefix="/api/feature-flags-v2", tags=["Feature Flags V2"])


class FeatureFlagResponse(BaseModel):
    flag_key: str
    description: str | None = None
    enabled: bool
    rollout_percentage: int
    whitelist_user_ids: list[str] | None = None

    class Config:
        from_attributes = True


class FeatureFlagUpdate(BaseModel):
    enabled: bool | None = None
    rollout_percentage: int | None = None
    whitelist_user_ids: list[str] | None = None
    description: str | None = None


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Admin 权限校验依赖。仅 admin/partner 可管理 DB feature flags。"""
    if current_user.role.value not in ("admin", "partner"):
        raise HTTPException(status_code=403, detail="权限不足")
    return current_user


@router.get("")
async def list_flags(
    _user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """列出所有 DB feature flags。"""
    flags = await FeatureFlagService.list_all(db)
    return [FeatureFlagResponse.model_validate(f) for f in flags]


@router.get("/{key}")
async def get_flag(
    key: str,
    _user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取单个 flag。"""
    flag = await FeatureFlagService.get_by_key(db, key)
    if flag is None:
        raise HTTPException(status_code=404, detail=f"Flag '{key}' not found")
    return FeatureFlagResponse.model_validate(flag)


@router.put("/{key}")
async def update_flag(
    key: str,
    body: FeatureFlagUpdate,
    _user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """设置 flag（即时生效 ≤ TTL 无需重部署）。"""
    flag = await FeatureFlagService.upsert(
        db, key,
        enabled=body.enabled,
        rollout_percentage=body.rollout_percentage,
        whitelist_user_ids=body.whitelist_user_ids,
        description=body.description,
    )
    await db.commit()
    return FeatureFlagResponse.model_validate(flag)
