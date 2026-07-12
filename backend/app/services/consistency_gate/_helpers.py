"""一致性门控 — 共享辅助方法 mixin"""
from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import (
    FinancialReport,
    FinancialReportType,
)

from app.services.consistency_gate._models import CheckItem

logger = logging.getLogger(__name__)

# 容差：金额比较允许 0.01 元误差（四舍五入）
TOLERANCE = Decimal("0.01")


class HelpersMixin:
    """共享辅助方法（被 E1/D4/Cycle 检查依赖）"""

    db: AsyncSession

    async def _get_dynamic_tolerance(self, project_id: UUID, year: int) -> Decimal:
        """计算动态容差: max(1.0, 重要性水平 × 0.001)"""
        try:
            from app.models.audit_platform_models import Materiality

            stmt = select(Materiality.overall_materiality).where(
                Materiality.project_id == project_id,
                Materiality.year == year,
                Materiality.is_deleted == False,  # noqa: E712
            ).order_by(Materiality.created_at.desc()).limit(1)
            result = await self.db.execute(stmt)
            mat_amount = result.scalar()
            if mat_amount is None:
                return Decimal("1.0")
            dynamic = Decimal(str(mat_amount)) * Decimal("0.001")
            return max(Decimal("1.0"), dynamic)
        except Exception as e:
            logger.warning("_get_dynamic_tolerance fallback to 1.0: %s", e)
            return Decimal("1.0")

    async def _get_e1_audited_amount(self, project_id: UUID, year: int) -> Decimal | None:
        """从 financial_report 取货币资金审定数(BS 行)"""
        try:
            stmt = select(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == FinancialReportType.balance_sheet,
                FinancialReport.is_deleted == False,  # noqa: E712
                FinancialReport.is_total_row == False,  # noqa: E712
            )
            result = await self.db.execute(stmt)
            for row in result.scalars().all():
                if "货币资金" in (row.row_name or ""):
                    return Decimal(str(row.current_period_amount or 0))
            return None
        except Exception as e:
            logger.warning("_get_e1_audited_amount failed: %s", e)
            return None

    async def _get_cfs_ending_cash(self, project_id: UUID, year: int) -> Decimal | None:
        """从 financial_report 取 CFS 期末现金及现金等价物余额"""
        try:
            stmt = select(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == FinancialReportType.cash_flow_statement,
                FinancialReport.is_deleted == False,  # noqa: E712
            )
            result = await self.db.execute(stmt)
            for row in result.scalars().all():
                name = (row.row_name or "").strip()
                if ("期末" in name) and (
                    "现金及现金等价物" in name
                    or "现金等价物" in name
                ):
                    return Decimal(str(row.current_period_amount or 0))
            return None
        except Exception as e:
            logger.warning("_get_cfs_ending_cash failed: %s", e)
            return None

    async def _get_cfs_net_change(self, project_id: UUID, year: int) -> Decimal | None:
        """从 financial_report 取 CFS 现金及现金等价物净增加额"""
        try:
            stmt = select(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == FinancialReportType.cash_flow_statement,
                FinancialReport.is_deleted == False,  # noqa: E712
            )
            result = await self.db.execute(stmt)
            for row in result.scalars().all():
                name = (row.row_name or "").strip()
                if ("现金及现金等价物" in name or "现金等价物" in name) and (
                    "净增加" in name or "净变动" in name or "净流" in name
                ):
                    return Decimal(str(row.current_period_amount or 0))
            return None
        except Exception as e:
            logger.warning("_get_cfs_net_change failed: %s", e)
            return None

    async def _get_e1_period_change(self, project_id: UUID, year: int) -> Decimal | None:
        """E1 期末审定数 - 期初余额 = 货币资金本期变动额"""
        try:
            stmt = select(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == FinancialReportType.balance_sheet,
                FinancialReport.is_deleted == False,  # noqa: E712
                FinancialReport.is_total_row == False,  # noqa: E712
            )
            result = await self.db.execute(stmt)
            for row in result.scalars().all():
                if "货币资金" in (row.row_name or ""):
                    cur = Decimal(str(row.current_period_amount or 0))
                    prior = Decimal(str(row.prior_period_amount or 0))
                    return cur - prior
            return None
        except Exception as e:
            logger.warning("_get_e1_period_change failed: %s", e)
            return None

    async def _get_tb_cash_total(self, project_id: UUID, year: int) -> Decimal | None:
        """从 trial_balance 取 1001/1002/1012/1502 期末审定数合计"""
        try:
            from app.models.audit_platform_models import TrialBalance

            cash_codes = ("1001", "1002", "1012", "1502")
            stmt = select(
                func.sum(TrialBalance.audited_amount)
            ).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == False,  # noqa: E712
                TrialBalance.standard_account_code.in_(cash_codes),
            )
            result = await self.db.execute(stmt)
            val = result.scalar()
            return Decimal(str(val)) if val is not None else None
        except Exception as e:
            logger.warning("_get_tb_cash_total failed: %s", e)
            return None

    async def _get_wp_parsed_data(self, project_id: UUID, wp_code: str) -> dict | None:
        """获取指定底稿的 parsed_data"""
        try:
            from app.models.workpaper_models import WorkingPaper, WpIndex

            stmt = (
                sa.select(WorkingPaper.parsed_data)
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(
                    WpIndex.project_id == project_id,
                    WpIndex.wp_code == wp_code,
                    WpIndex.is_deleted == False,  # noqa: E712
                    WorkingPaper.is_deleted == False,  # noqa: E712
                )
                .order_by(WorkingPaper.updated_at.desc())
                .limit(1)
            )
            result = await self.db.execute(stmt)
            row = result.scalar_one_or_none()
            return row if isinstance(row, dict) else None
        except Exception as e:
            logger.warning("_get_wp_parsed_data(%s) failed: %s", wp_code, e)
            return None

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
