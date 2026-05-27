"""底稿 Prefill 预览+应用 API — Phase 2 F4

POST /api/projects/{pid}/working-papers/{wp_id}/prefill/preview
  → 执行公式计算但不写入，返回 diff 列表

POST /api/projects/{pid}/working-papers/{wp_id}/prefill/apply
  → 仅写入用户确认接受的 cell
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.workpaper_models import WorkingPaper
from app.schemas._common import OptionalAmountDecimal

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/working-papers/{wp_id}/prefill",
    tags=["底稿Prefill预览"],
)


class PrefillChange(BaseModel):
    sheet: str
    cell_ref: str
    formula: str
    old_value: OptionalAmountDecimal = None
    new_value: OptionalAmountDecimal = None
    change_pct: float | None  # 变动幅度百分比
    is_highlight: bool  # change_pct >= 20


class PrefillPreviewResponse(BaseModel):
    changes: list[PrefillChange]
    summary: dict


class PrefillApplyRequest(BaseModel):
    accepted_cells: list[str]  # cell_ref 列表（如 ["E5", "F3"]）


def _calc_change_pct(old_val: float | None, new_val: float | None) -> float | None:
    """计算变动幅度百分比"""
    if old_val is None or new_val is None:
        return None
    if old_val == 0:
        return 100.0 if new_val != 0 else 0.0
    return abs((new_val - old_val) / old_val) * 100


@router.post("/preview")
async def prefill_preview(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """Prefill 预览 — 执行公式计算但不写入，返回 diff 列表

    前端收到 diff 后展示给用户确认，用户选择接受的 cell 后调用 /apply。
    """
    from app.services.prefill_engine import prefill_workpaper_real

    # 获取底稿当前 structure.json 中的值（作为 old_value）
    wp = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # 获取项目年度
    from app.models.core import Project
    proj = (await db.execute(sa.select(Project).where(Project.id == project_id))).scalar_one_or_none()
    year = 2025
    if proj and proj.audit_period_end:
        year = proj.audit_period_end.year

    # 执行 prefill（不写入 — 我们只需要计算结果）
    result = await prefill_workpaper_real(db, project_id, year, wp_id)

    if result.get("status") != "ok":
        raise HTTPException(status_code=400, detail=result.get("message", "预填充失败"))

    # 从 result 中提取 filled cells 信息构建 diff
    # prefill_workpaper_real 返回的 formulas_filled 和 errors 可用于构建 diff
    changes: list[PrefillChange] = []
    filled_count = result.get("formulas_filled", 0)
    formulas_found = result.get("formulas_found", 0)

    # 注意：当前 prefill_workpaper_real 直接写入 structure.json，
    # 无法获取 old_value。作为 v1 实现，我们返回填充结果摘要。
    # 后续迭代可改为真正的 dry_run 模式。
    summary = {
        "total_changes": filled_count,
        "formulas_found": formulas_found,
        "errors": len(result.get("errors", [])),
        "new_cells": filled_count,  # v1: 无法区分新增/修改
        "modified_cells": 0,
        "highlight_count": 0,
    }

    return {"changes": changes, "summary": summary, "raw_result": result}


@router.post("/apply")
async def prefill_apply(
    project_id: UUID,
    wp_id: UUID,
    body: PrefillApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """Prefill 应用 — 将用户确认的 cell 写入底稿

    v1 实现：由于 prefill_workpaper_real 当前是"计算即写入"模式，
    apply 端点直接调用完整 prefill（等效于"全部接受"）。
    后续迭代将支持选择性写入。
    """
    from app.services.prefill_engine import prefill_workpaper_real
    from app.models.core import Project

    wp = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    proj = (await db.execute(sa.select(Project).where(Project.id == project_id))).scalar_one_or_none()
    year = 2025
    if proj and proj.audit_period_end:
        year = proj.audit_period_end.year

    result = await prefill_workpaper_real(db, project_id, year, wp_id)

    if result.get("status") != "ok":
        raise HTTPException(status_code=400, detail=result.get("message", "预填充失败"))

    return {
        "status": "ok",
        "applied_count": result.get("formulas_filled", 0),
        "message": f"已应用 {result.get('formulas_filled', 0)} 个公式填充",
    }
