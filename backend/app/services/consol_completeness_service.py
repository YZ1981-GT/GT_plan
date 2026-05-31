"""子公司数据完整度前置校验（consol-phase3-frontend-drilldown / 需求 6 / 属性 T5）.

一键刷新（Phase 2 refresh-all）前检查各子公司：
  - TB 审定数（audited_amount 非全 0/全空）
  - 附注是否已生成（disclosure_notes 存在）

设计定位（T5 / EH5）：
- **warning 不阻断**：返回 warnings 列表，前端提示但仍允许刷新（warnings 非 error）。
- **异步 + 超时降级**：子公司过多时整体校验设超时，超时返回部分结果 + "校验未完成"提示，
  不阻断刷新（EH5）。

主要 API:
- check_subsidiary_completeness(db, parent_project_id, year, timeout=...) -> dict
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 默认整体校验超时（秒）；子公司过多时超时降级（EH5）
DEFAULT_TIMEOUT_SECONDS = 8.0


async def check_subsidiary_completeness(
    db: AsyncSession,
    parent_project_id: UUID,
    year: int,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """检查合并项目各子公司数据完整度（warning 不阻断）.

    Returns:
        {
          "warnings": [str, ...],          # 不完整项的中文提示（非 error）
          "checked_count": int,            # 已校验子公司数
          "total_count": int,              # 子公司总数
          "completed": bool,               # 校验是否跑完（超时则 False）
          "can_refresh": True,             # 恒为 True（T5：不阻断刷新）
        }
    """
    from app.services.consol_tree_service import build_tree, get_descendants

    try:
        tree = await build_tree(db, parent_project_id)
    except Exception as err:
        logger.warning("check_subsidiary_completeness build_tree failed: %s", err)
        return {
            "warnings": [],
            "checked_count": 0,
            "total_count": 0,
            "completed": False,
            "can_refresh": True,
        }

    if tree is None:
        return {
            "warnings": [],
            "checked_count": 0,
            "total_count": 0,
            "completed": True,
            "can_refresh": True,
        }

    leaves = [n for n in get_descendants(tree)]  # 所有后代（子公司）
    total = len(leaves)

    try:
        result = await asyncio.wait_for(
            _check_all(db, leaves, year), timeout=timeout
        )
        warnings, checked = result
        completed = True
    except asyncio.TimeoutError:
        # EH5：超时降级 — 返回部分结果 + 提示，不阻断
        logger.warning(
            "check_subsidiary_completeness timed out for project %s (%d subs)",
            parent_project_id, total,
        )
        warnings = ["子公司数量较多，完整度校验未完成（不影响刷新，可稍后重试）"]
        checked = 0
        completed = False

    return {
        "warnings": warnings,
        "checked_count": checked,
        "total_count": total,
        "completed": completed,
        "can_refresh": True,
    }


async def _check_all(db: AsyncSession, leaves: list, year: int) -> tuple[list[str], int]:
    """逐子公司检查 TB 审定数 + 附注生成状态，返回 (warnings, checked_count)."""
    warnings: list[str] = []
    checked = 0
    for leaf in leaves:
        checked += 1
        name = leaf.company_name or leaf.company_code
        if not await _has_audited_tb(db, leaf.project_id, year):
            warnings.append(f"子公司 {name} 无审定试算数据，合并结果可能不准确")
        if not await _has_notes(db, leaf.project_id, year):
            warnings.append(f"子公司 {name} 未生成附注")
    return warnings, checked


async def _has_audited_tb(db: AsyncSession, project_id: UUID, year: int) -> bool:
    """子公司当年 trial_balance 是否有非全 0 的审定数（audited_amount）."""
    from app.models.audit_platform_models import TrialBalance

    result = await db.execute(
        sa.select(sa.func.count())
        .select_from(TrialBalance)
        .where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.audited_amount.isnot(None),
            TrialBalance.audited_amount != 0,
        )
    )
    return (result.scalar() or 0) > 0


async def _has_notes(db: AsyncSession, project_id: UUID, year: int) -> bool:
    """子公司当年 disclosure_notes 是否已生成（存在未删除记录）."""
    from app.models.report_models import DisclosureNote

    result = await db.execute(
        sa.select(sa.func.count())
        .select_from(DisclosureNote)
        .where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    return (result.scalar() or 0) > 0
