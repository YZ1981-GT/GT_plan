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
    apply_incremental,
    compute_incremental_diff,
    delete_ledger_data,
    detect_existing_periods,
    list_trash,
    restore_ledger_data,
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
    hard_delete: bool = Field(
        False,
        description="硬删除（S7-10 默认软删，进回收站可恢复；硬删不可恢复）",
    )


class RestoreLedgerRequest(BaseModel):
    """S7-10 恢复请求。"""
    year: int
    tables: Optional[list[str]] = None
    periods: Optional[list[int]] = None


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
            hard_delete=request.hard_delete,
        )
        total = sum(v for v in deleted.values() if v >= 0)
        mode = "hard" if request.hard_delete else "soft"
        logger.info(
            "ledger %s-delete by user=%s project=%s year=%d periods=%s total=%d",
            mode, current_user.id, project_id, request.year, request.periods, total,
        )
        return {
            "success": True,
            "deleted": deleted,
            "total_deleted": total,
            "year": request.year,
            "periods": request.periods,
            "mode": mode,
            "recoverable": not request.hard_delete,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("delete ledger data failed")
        raise HTTPException(status_code=500, detail=f"删除失败: {exc}")


@router.get("/trash")
async def get_trash(
    project_id: UUID,
    year: Optional[int] = Query(None, description="只查某一年（None 则全部）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """S7-10: 列出回收站中已软删除的数据。"""
    try:
        return await list_trash(db, project_id=project_id, year=year)
    except Exception as exc:
        logger.exception("list_trash failed")
        raise HTTPException(status_code=500, detail=f"查询回收站失败: {exc}")


@router.post("/restore")
async def restore_ledger(
    project_id: UUID,
    request: RestoreLedgerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """S7-10: 从回收站恢复数据（is_deleted=true → false）。"""
    if current_user.role not in ("admin", "partner", "manager"):
        raise HTTPException(status_code=403, detail="仅项目经理及以上可恢复账表数据")

    try:
        restored = await restore_ledger_data(
            db,
            project_id=project_id,
            year=request.year,
            tables=request.tables,
            periods=request.periods,
        )
        total = sum(v for v in restored.values() if v >= 0)
        logger.info(
            "ledger restore by user=%s project=%s year=%d periods=%s total=%d",
            current_user.id, project_id, request.year, request.periods, total,
        )
        return {
            "success": True,
            "restored": restored,
            "total_restored": total,
            "year": request.year,
            "periods": request.periods,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("restore ledger failed")
        raise HTTPException(status_code=500, detail=f"恢复失败: {exc}")


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


class IncrementalApplyRequest(BaseModel):
    """增量追加执行（S6-15）。"""
    year: int
    file_periods: list[int] = Field(..., description="文件中的月份列表")
    overlap_strategy: str = Field(
        "skip",
        description="重叠月份策略：skip=跳过/overwrite=覆盖",
    )
    confirmed: bool = Field(False, description="二次确认（overwrite 策略必填）")


@router.post("/incremental/apply")
async def apply_incremental_endpoint(
    project_id: UUID,
    request: IncrementalApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """S6-15: 增量追加执行——按策略清理将被覆盖的期间。

    清理完成后，前端继续走正常的 `/ledger-import/submit` 触发新导入；
    或者本端点不变，由前端分两步调用（先 detect，再本端点清理旧月）。

    overlap_strategy:
      - skip: 跳过重叠月份（不删除）
      - overwrite: 删除重叠月份（必须 confirmed=True）
    """
    # 权限校验
    if current_user.role not in ("admin", "partner", "manager"):
        raise HTTPException(status_code=403, detail="仅项目经理及以上可执行增量追加")

    if request.overlap_strategy == "overwrite" and not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="overwrite 策略必须显式确认（confirmed=true）",
        )

    try:
        result = await apply_incremental(
            db,
            project_id=project_id,
            year=request.year,
            file_periods=request.file_periods,
            overlap_strategy=request.overlap_strategy,
        )
        logger.info(
            "incremental apply by user=%s project=%s year=%d strategy=%s executed=%s",
            current_user.id, project_id, request.year,
            request.overlap_strategy, result.get("executed"),
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("apply_incremental failed")
        raise HTTPException(status_code=500, detail=f"增量追加失败: {exc}")


__all__ = ["router"]
