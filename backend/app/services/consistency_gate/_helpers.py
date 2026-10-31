"""一致性门控 — 辅助函数与保存点装饰器

ADR-FHIC-14 第 2~3 点。
- 辅助函数不吞异常：返回 None 只表示真实无数据，异常上抛给 @_guarded。
- `_probe_wp`：检测底稿存在性，返回 WpDataProbe。
- `_guarded`：保存点包装装饰器，异常 → error 不污染事务。
"""
from __future__ import annotations

import functools
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import (
    FinancialReport,
    FinancialReportType,
)
from app.services.consistency_gate._models import CheckItem, _error

logger = logging.getLogger(__name__)

# 容差：金额比较允许 0.01 元误差
TOLERANCE = Decimal("0.01")


# ---------------------------------------------------------------------------
# WpDataProbe — 底稿探测结果
# ---------------------------------------------------------------------------

WpState = Literal["present", "empty", "empty_form", "trimmed", "absent"]


@dataclass(frozen=True, slots=True)
class WpDataProbe:
    state: WpState
    parsed_data: dict | None = None


async def _probe_wp(
    db: AsyncSession, project_id: UUID, wp_code: str
) -> WpDataProbe:
    """检测底稿是否存在及其状态（不吞异常）。

    - absent: wp_index 无行
    - trimmed: wp_index 有行但无未删 working_paper 且有已删记录
    - empty_form: parsed_data 为空但有 checklist_responses 行
    - empty: parsed_data 为空且无 checklist_responses 行
    - present: parsed_data 非空
    """
    from app.models.workpaper_models import WorkingPaper, WpIndex

    # 1. 查 wp_index
    idx_stmt = select(WpIndex.id).where(
        WpIndex.project_id == project_id,
        WpIndex.wp_code == wp_code,
        WpIndex.is_deleted == sa.false(),
    ).limit(1)
    idx_row = (await db.execute(idx_stmt)).scalar_one_or_none()
    if idx_row is None:
        return WpDataProbe(state="absent")

    wp_index_id = idx_row

    # 2. 查未删 working_paper
    wp_stmt = (
        select(WorkingPaper.id, WorkingPaper.parsed_data)
        .where(
            WorkingPaper.wp_index_id == wp_index_id,
            WorkingPaper.is_deleted == sa.false(),
        )
        .order_by(WorkingPaper.updated_at.desc())
        .limit(1)
    )
    wp_hit = (await db.execute(wp_stmt)).first()

    if wp_hit is None:
        # 无未删 working_paper — 检查是否有已删记录（裁剪）
        del_stmt = select(sa.func.count()).select_from(WorkingPaper).where(
            WorkingPaper.wp_index_id == wp_index_id,
            WorkingPaper.is_deleted == sa.true(),
        )
        del_count = (await db.execute(del_stmt)).scalar() or 0
        if del_count > 0:
            return WpDataProbe(state="trimmed")
        return WpDataProbe(state="empty")

    wp_id, wp_row = wp_hit
    parsed = wp_row if isinstance(wp_row, dict) else None
    if parsed:
        return WpDataProbe(state="present", parsed_data=parsed)

    # parsed_data 为空 — 检查 checklist_responses（该表无 ORM 模型，走裸 SQL；wp_id 外键指向 working_paper.id，不是 wp_index）
    cr_stmt = sa.text("SELECT count(*) FROM checklist_responses WHERE wp_id = :wp_id")
    cr_count = (await db.execute(cr_stmt, {"wp_id": wp_id})).scalar() or 0
    if cr_count > 0:
        return WpDataProbe(state="empty_form")
    return WpDataProbe(state="empty")


# ---------------------------------------------------------------------------
# @_guarded — 保存点包装装饰器
# ---------------------------------------------------------------------------

def _guarded(check_id: str):
    """保存点包装：async with db.begin_nested() 包住方法体。

    异常 → 回滚到保存点，产出 error CheckItem，后续检查不受影响。
    check_id 必须是字符串字面量（AST 守卫验证）。
    """
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(self, *args, **kwargs):
            try:
                async with self.db.begin_nested():
                    return await fn(self, *args, **kwargs)
            except Exception as exc:
                # 回滚到保存点后产出 error — 不污染外层事务
                logger.warning(
                    "consistency_gate %s 异常: %s: %s",
                    check_id, type(exc).__name__, str(exc)[:200],
                )
                check_name = check_id.replace("_", " ").strip()
                return _error(
                    check_name,
                    branch_id=f"{check_id}.exception",
                    reason=f"检查异常：{type(exc).__name__}：{str(exc)[:200]}",
                    severity="warning",
                )
        wrapper._guarded_check_id = check_id  # AST 守卫读取
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# HelpersMixin — 共享辅助方法（不吞异常）
# ---------------------------------------------------------------------------

class HelpersMixin:
    """共享辅助方法。异常不在此处捕获，由 @_guarded 统一处理。"""

    db: AsyncSession

    async def _get_dynamic_tolerance(self, project_id: UUID, year: int) -> Decimal:
        """计算动态容差：max(1.0, 重要性水平 × 0.001)"""
        from app.models.audit_platform_models import Materiality

        stmt = (
            select(Materiality.overall_materiality)
            .where(
                Materiality.project_id == project_id,
                Materiality.year == year,
                Materiality.is_deleted == sa.false(),
            )
            .order_by(Materiality.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        mat_amount = result.scalar()
        if mat_amount is None:
            return Decimal("1.0")
        dynamic = Decimal(str(mat_amount)) * Decimal("0.001")
        return max(Decimal("1.0"), dynamic)

    async def _get_e1_audited_amount(self, project_id: UUID, year: int) -> Decimal | None:
        """从 financial_report 取货币资金审定数（BS 行）"""
        stmt = select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == FinancialReportType.balance_sheet,
            FinancialReport.is_deleted == sa.false(),
            FinancialReport.is_total_row == sa.false(),
        )
        result = await self.db.execute(stmt)
        for row in result.scalars().all():
            if "货币资金" in (row.row_name or ""):
                return Decimal(str(row.current_period_amount or 0))
        return None

    async def _get_cfs_ending_cash(self, project_id: UUID, year: int) -> Decimal | None:
        """从 financial_report 取 CFS 期末现金及现金等价物余额"""
        stmt = select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == FinancialReportType.cash_flow_statement,
            FinancialReport.is_deleted == sa.false(),
        )
        result = await self.db.execute(stmt)
        for row in result.scalars().all():
            name = (row.row_name or "").strip()
            if ("期末" in name) and (
                "现金及现金等价物" in name or "现金等价物" in name
            ):
                return Decimal(str(row.current_period_amount or 0))
        return None

    async def _get_cfs_net_change(self, project_id: UUID, year: int) -> Decimal | None:
        """从 financial_report 取 CFS 现金及现金等价物净增加额"""
        stmt = select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == FinancialReportType.cash_flow_statement,
            FinancialReport.is_deleted == sa.false(),
        )
        result = await self.db.execute(stmt)
        for row in result.scalars().all():
            name = (row.row_name or "").strip()
            if ("现金及现金等价物" in name or "现金等价物" in name) and (
                "净增加" in name or "净变动" in name or "净流" in name
            ):
                return Decimal(str(row.current_period_amount or 0))
        return None

    async def _get_e1_period_change(self, project_id: UUID, year: int) -> Decimal | None:
        """E1 期末审定数 − 期初余额 = 货币资金本期变动额"""
        stmt = select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == FinancialReportType.balance_sheet,
            FinancialReport.is_deleted == sa.false(),
            FinancialReport.is_total_row == sa.false(),
        )
        result = await self.db.execute(stmt)
        for row in result.scalars().all():
            if "货币资金" in (row.row_name or ""):
                cur = Decimal(str(row.current_period_amount or 0))
                prior = Decimal(str(row.prior_period_amount or 0))
                return cur - prior
        return None

    async def _get_tb_cash_total(self, project_id: UUID, year: int) -> Decimal | None:
        """从 trial_balance 取 1001/1002/1012/1502 期末审定数合计"""
        from app.models.audit_platform_models import TrialBalance

        cash_codes = ("1001", "1002", "1012", "1502")
        stmt = select(
            func.sum(TrialBalance.audited_amount)
        ).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
            TrialBalance.standard_account_code.in_(cash_codes),
        )
        result = await self.db.execute(stmt)
        val = result.scalar()
        return Decimal(str(val)) if val is not None else None

    async def _get_wp_parsed_data(self, project_id: UUID, wp_code: str) -> dict | None:
        """获取指定底稿的 parsed_data（不吞异常）"""
        from app.models.workpaper_models import WorkingPaper, WpIndex

        stmt = (
            sa.select(WorkingPaper.parsed_data)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WpIndex.project_id == project_id,
                WpIndex.wp_code == wp_code,
                WpIndex.is_deleted == sa.false(),
                WorkingPaper.is_deleted == sa.false(),
            )
            .order_by(WorkingPaper.updated_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return row if isinstance(row, dict) else None

    @staticmethod
    def _extract_decimal(data: dict | None, key: str) -> Decimal | None:
        """从 parsed_data 中安全提取 Decimal 值"""
        if not data:
            return None
        val = data.get(key)
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None
