"""账表数据管理路由 — 查询 / 删除 / 增量追加。

端点：
- GET /api/projects/{pid}/ledger-data/summary       查询已导入数据概览
- DELETE /api/projects/{pid}/ledger-data            按维度删除
- POST /api/projects/{pid}/ledger-data/incremental/detect  增量追加前预检（返回期间差异）
- POST /api/projects/{pid}/ledger-data/incremental        执行增量追加

权限：项目成员可查询，manager/partner 可删除/追加。
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.ledger_data_service import (
    LEDGER_TABLES,
    compute_incremental_diff,
    delete_ledger_data,
    detect_existing_periods,
    summarize_ledger_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/ledger-data", tags=["ledger-data"])


class DeleteLedgerRequest(BaseModel):
    """删除请求。"""
    year: int = Field(..., description="目标年度")
    tables: Optional[list[str]] = Field(
        None,
        description="指定表名（默认全部四表）",
    )
    periods: Optional[list[int]] = Field(
        None,
        description="月份列表（仅对 tb_ledger/tb_aux_ledger 生效；不传则删整年）",
    )
    confirmed: bool = Field(
        False,
        description="二次确认（防止误操作）",
    )


class IncrementalDetectRequest(BaseModel):
    """增量导入预检。"""
    year: int
    file_periods: list[int] = Field(..., description="文件中的月份列表")


@router.get("/summary")
async def get_ledger_summary(
    project_id: UUID,
    year: Optional[int] = Query(None, description="只查某一年（None 则全部）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """查询项目已导入账表数据概览。"""
    try:
        return await summarize_ledger_data(db, project_id=project_id, year=year)
    except Exception as exc:
        logger.exception("summarize ledger data failed")
        raise HTTPException(status_code=500, detail=f"查询失败: {exc}")


@router.delete("")
async def delete_ledger(
    project_id: UUID,
    request: DeleteLedgerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """按维度删除账表数据。

    必须 confirmed=True 才执行（防误操作）。
    """
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="删除操作必须显式确认（confirmed=true）",
        )

    # 权限校验
    if current_user.role not in ("admin", "partner", "manager"):
        raise HTTPException(status_code=403, detail="仅项目经理及以上可删除账表数据")

    try:
        deleted = await delete_ledger_data(
            db,
            project_id=project_id,
            year=request.year,
            tables=request.tables,
            periods=request.periods,
        )
        total = sum(v for v in deleted.values() if v >= 0)
        logger.info(
            "ledger delete by user=%s project=%s year=%d periods=%s total=%d",
            current_user.id, project_id, request.year, request.periods, total,
        )
        return {
            "success": True,
            "deleted": deleted,
            "total_deleted": total,
            "year": request.year,
            "periods": request.periods,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("delete ledger data failed")
        raise HTTPException(status_code=500, detail=f"删除失败: {exc}")


@router.post("/incremental/detect")
async def detect_incremental(
    project_id: UUID,
    request: IncrementalDetectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """增量追加预检：返回期间差异。

    前端在增量导入前调用此端点，根据 diff 结果决定：
    - 只有 new 月份 → 直接追加
    - 有 overlap → 提示用户"将覆盖 X 月数据"，需确认
    """
    existing = await detect_existing_periods(
        db, project_id=project_id, year=request.year
    )
    file_periods_set = set(request.file_periods)
    diff = compute_incremental_diff(existing, file_periods_set)
    return {
        "year": request.year,
        "existing_periods": sorted(existing),
        "file_periods": sorted(file_periods_set),
        "diff": diff,
        "can_append_safely": len(diff["overlap"]) == 0,
        "requires_confirm": len(diff["overlap"]) > 0,
    }


__all__ = ["router"]
