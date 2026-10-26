"""统一字段覆盖存储 API 路由

前缀：/api/workpapers/field-overrides
提供 GET（批量获取 scope 下所有覆盖值）和 POST（upsert 单个覆盖值）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user
from app.models.core import User
from app.services.field_override_service import FieldOverrideService
from app.services.wp_visibility.program_row_guard import assert_program_override_allowed

router = APIRouter(prefix="/api/workpapers/field-overrides")


# ─── Schemas ────────────────────────────────────────────────────────────────


class FieldOverrideSetRequest(BaseModel):
    """设置覆盖值请求"""
    project_id: UUID
    year: int
    scope: str = Field(max_length=50)
    item_key: str = Field(max_length=100)
    field: str = Field(max_length=50)
    value: Any = None


class FieldOverrideSetResponse(BaseModel):
    """设置覆盖值响应"""
    id: UUID
    project_id: UUID
    year: int
    scope: str
    item_key: str
    field: str
    value: Any


# ─── Endpoints ──────────────────────────────────────────────────────────────


@router.get("")
async def get_field_overrides(
    project_id: UUID = Query(...),
    year: int = Query(...),
    scope: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, dict[str, Any]]:
    """获取指定 scope 下所有覆盖值（项目成员可读；原先只校验登录，可读任意项目）"""
    await assert_project_permission(db, _user, project_id, "readonly")
    svc = FieldOverrideService(db)
    return await svc.get_batch(project_id, year, scope)


@router.post("", status_code=200)
async def set_field_override(
    body: FieldOverrideSetRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FieldOverrideSetResponse:
    """Upsert 单个覆盖值（项目 edit 级；程序表行只能写派给本人的，spec procedure-trim-generation-delegation-chain 需求 7.3）"""
    await assert_project_permission(db, user, body.project_id, "edit")
    await assert_program_override_allowed(
        db, user, body.project_id, body.scope, body.item_key, body.field, body.value,
    )
    svc = FieldOverrideService(db)
    override = await svc.set(
        project_id=body.project_id,
        year=body.year,
        scope=body.scope,
        item_key=body.item_key,
        field=body.field,
        value=body.value,
        user_id=user.id,
    )
    await db.commit()
    return FieldOverrideSetResponse(
        id=override.id,
        project_id=override.project_id,
        year=override.year,
        scope=override.scope,
        item_key=override.item_key,
        field=override.field,
        value=override.value,
    )
