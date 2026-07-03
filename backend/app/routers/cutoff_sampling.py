"""截止测试自动提取 API 路由

- POST /api/projects/{pid}/sampling/cutoff-extract  — 按条件提取凭证
- GET  /api/projects/{pid}/sampling/cutoff-history  — 提取历史列表
- POST /api/projects/{pid}/sampling/cutoff-undo     — 撤销提取
- POST /api/projects/{pid}/sampling/cutoff-fill     — 记录填充日志

Validates: Requirements 2.1, 2.12, 5.2, 5.5, 5.6
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import WorkpaperExtractionLog
from app.models.core import User
from app.services.ledger_sampling_service import (
    CutoffExtractRequest,
    ExtractionLogCreate,
    LedgerQueryFilters,
    LedgerSamplingService,
)
from app.services.version_trail_service import VersionTrailService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{pid}/sampling",
    tags=["sampling"],
)


# ─── Request / Response schemas ──────────────────────────────────────────────


class CutoffFillRequest(BaseModel):
    """截止测试填充请求 — 记录日志"""

    workpaper_id: UUID
    extraction_type: str = "cutoff"
    extraction_criteria: dict
    total_matched: int
    filled_count: int
    fill_mode: str  # "append" | "replace" | "merge"
    before_data: Optional[list[dict]] = None
    filled_voucher_nos: list[str] = Field(default_factory=list)


# ─── POST /cutoff-extract ─────────────────────────────────────────────────────


@router.post("/cutoff-extract")
async def cutoff_extract(
    pid: UUID,
    req: CutoffExtractRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按截止测试条件提取凭证

    日期窗口计算：cutoff_date - days_before 至 cutoff_date + days_after
    exclude_extracted=true 时排除已填充的凭证号
    """
    try:
        # 1. 计算日期窗口
        date_start = req.cutoff_date - timedelta(days=req.days_before)
        date_end = req.cutoff_date + timedelta(days=req.days_after)

        # 2. 排除已提取凭证号（从 workpaper_extraction_log 获取）
        exclude_voucher_nos: list[str] = []
        if req.exclude_extracted:
            exclude_voucher_nos = await _get_extracted_voucher_nos(
                db, req.workpaper_id
            )

        # 3. 构建过滤条件
        filters = LedgerQueryFilters(
            date_start=date_start,
            date_end=date_end,
            account_codes=req.account_codes,
            amount_threshold=req.amount_threshold,
            direction_filter=req.direction_filter,
            voucher_type_filter=req.voucher_type_filter,
            summary_keyword=req.summary_keyword,
            exclude_voucher_nos=exclude_voucher_nos,
        )

        # 4. 构建查询（year 从 cutoff_date 推导）
        year = req.cutoff_date.year
        query = await LedgerSamplingService.build_ledger_query(
            db, pid, year, filters
        )

        # 5. 执行查询并获取统计
        items, stats = await LedgerSamplingService.execute_with_stats(
            db, query, req.page, req.page_size
        )

        return {
            "items": items,
            "stats": stats.model_dump(),
            "page": req.page,
            "page_size": req.page_size,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── GET /cutoff-history ──────────────────────────────────────────────────────


@router.get("/cutoff-history")
async def cutoff_history(
    pid: UUID,
    wp_id: UUID = Query(..., description="底稿ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定底稿的提取历史列表（按时间倒序）"""
    try:
        history = await LedgerSamplingService.get_extraction_history(db, wp_id)
        return history
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── POST /cutoff-undo ────────────────────────────────────────────────────────


@router.post("/cutoff-undo")
async def cutoff_undo(
    pid: UUID,
    log_id: UUID = Query(..., description="要撤销的日志记录ID"),
    wp_id: UUID = Query(..., description="底稿ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """撤销指定提取记录，返回 before_data"""
    try:
        result = await LedgerSamplingService.undo_extraction(db, log_id, wp_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── POST /cutoff-fill ────────────────────────────────────────────────────────


@router.post("/cutoff-fill")
async def cutoff_fill(
    pid: UUID,
    req: CutoffFillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """记录填充日志（含 before_data 快照）

    filled_voucher_nos 存入 extraction_criteria 以支持 exclude_extracted 功能
    """
    try:
        # ── 版本链：填充前自动快照 ──
        snapshot_type = "auto_sampling"
        desc_parts = [f"截止测试填充: {req.extraction_type}"]
        if req.filled_count:
            desc_parts.append(f"填充{req.filled_count}笔")
        if req.fill_mode:
            desc_parts.append(f"模式={req.fill_mode}")
        await VersionTrailService.create_snapshot_fire_and_forget(
            db=db,
            project_id=pid,
            workpaper_id=req.workpaper_id,
            user_id=current_user.id,
            snapshot_type=snapshot_type,
            description="，".join(desc_parts),
        )

        # 将 filled_voucher_nos 合并到 extraction_criteria 中
        criteria = dict(req.extraction_criteria)
        if req.filled_voucher_nos:
            criteria["filled_voucher_nos"] = req.filled_voucher_nos

        log_data = ExtractionLogCreate(
            project_id=pid,
            workpaper_id=req.workpaper_id,
            user_id=current_user.id,
            extraction_type=req.extraction_type,
            extraction_criteria=criteria,
            total_matched=req.total_matched,
            filled_count=req.filled_count,
            fill_mode=req.fill_mode,
            before_data=req.before_data,
        )

        result = await LedgerSamplingService.record_extraction_log(db, log_data)
        await db.commit()
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Helper ───────────────────────────────────────────────────────────────────


async def _get_extracted_voucher_nos(
    db: AsyncSession,
    workpaper_id: UUID,
) -> list[str]:
    """从非撤销的提取日志中收集所有已填充的凭证号

    查询 workpaper_extraction_log 中 is_undone=False 的记录，
    从 extraction_criteria.filled_voucher_nos 提取凭证号列表。
    """
    stmt = select(
        WorkpaperExtractionLog.extraction_criteria
    ).where(
        WorkpaperExtractionLog.workpaper_id == workpaper_id,
        WorkpaperExtractionLog.is_undone == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    voucher_nos: list[str] = []
    for criteria in rows:
        if criteria and isinstance(criteria, dict):
            filled = criteria.get("filled_voucher_nos", [])
            if isinstance(filled, list):
                voucher_nos.extend(filled)

    # 去重
    return list(set(voucher_nos))
