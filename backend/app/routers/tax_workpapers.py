"""税审底稿接口（spec tax-workpaper-data-fetch）。

- GET  /api/projects/{project_id}/tax-workpapers/params?year=           表头参数（项目默认 + 手工）
- PUT  /api/projects/{project_id}/tax-workpapers/params?year=           保存表头参数
- GET  /api/projects/{project_id}/tax-workpapers/sheets/{code}?year=    取数 + 公式计算后的本表值
- PUT  /api/projects/{project_id}/tax-workpapers/sheets/{code}?year=    保存手工值，返回重算结果
- GET  /api/projects/{project_id}/tax-workpapers/account-map?year=      客户科目 → 取数用到它的税审底稿（底稿映射页）
- GET  /api/projects/{project_id}/tax-workpapers/adjustment-summary?year=  纳税调整汇总表（二~五类底稿的纳税调整逐项 + 验算）

读只读权限、写编辑权限；保存带版本号，冲突 409。写接口另需账号开通「允许修改」（spec citar-manual-edit-permission）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services import tax_adjustment_summary
from app.services import tax_workpaper_service as svc
from app.services.manual_edit_permission import assert_manual_edit

router = APIRouter(prefix="/api/projects/{project_id}/tax-workpapers", tags=["税审底稿"])


class SheetSaveBody(BaseModel):
    version: int = Field(..., ge=0)
    inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ParamsSaveBody(BaseModel):
    version: int = Field(..., ge=0)
    values: dict[str, Any] = Field(default_factory=dict)


@router.get("/params")
async def get_params(
    project_id: UUID,
    year: int = Query(..., ge=1990, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await svc.get_params(db, project_id, year)


@router.put("/params")
async def put_params(
    project_id: UUID,
    body: ParamsSaveBody,
    year: int = Query(..., ge=1990, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    assert_manual_edit(current_user)
    await svc.save_params(db, project_id, year, body.version, body.values, current_user.id)
    await db.commit()
    return await svc.get_params(db, project_id, year)


@router.get("/account-map")
async def get_account_map(
    project_id: UUID,
    year: int = Query(..., ge=1990, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await svc.account_workpaper_map(db, project_id, year)


@router.get("/adjustment-summary")
async def get_adjustment_summary(
    project_id: UUID,
    year: int = Query(..., ge=1990, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await tax_adjustment_summary.build(db, project_id, year)


@router.get("/sheets/{code}")
async def get_sheet(
    project_id: UUID,
    code: str,
    year: int = Query(..., ge=1990, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await svc.compute_sheet(db, project_id, year, code)


@router.put("/sheets/{code}")
async def put_sheet(
    project_id: UUID,
    code: str,
    body: SheetSaveBody,
    year: int = Query(..., ge=1990, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    assert_manual_edit(current_user)
    await svc.save_sheet_inputs(db, project_id, year, code, body.version, body.inputs, current_user.id)
    await db.commit()
    return await svc.compute_sheet(db, project_id, year, code)
