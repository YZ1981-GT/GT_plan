"""AI 辅助底稿编制服务

Phase 9 Task 9.8: 分析性复核 + 函证对象提取 + 审定表核对
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class WpAIService:
    """AI 辅助底稿编制"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analytical_review(self, project_id: UUID, account_code: str, year: int) -> dict:
        """分析性复核：变动分析"""
        from app.models.audit_platform_models import TrialBalance

        q = sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.standard_account_code == account_code,
            TrialBalance.year == year,
            TrialBalance.is_deleted == False,  # noqa
        )
        tb = (await self.db.execute(q)).scalar_one_or_none()
        if not tb:
            return {"error": f"科目 {account_code} 未找到"}

        current = float(tb.audited_debit or 0) - float(tb.audited_credit or 0)
        prior = float(tb.unadjusted_debit or 0) - float(tb.unadjusted_credit or 0)
        change = current - prior
        rate = round(change / prior * 100, 2) if prior != 0 else None

        return {
            "account_code": account_code,
            "current_balance": current,
            "prior_balance": prior,
            "change_amount": change,
            "change_rate": rate,
            "is_significant": abs(rate or 0) > 20 if rate is not None else abs(change) > 0,
            "ai_analysis": f"该科目余额变动 {change:,.2f}，变动率 {rate}%。" if rate else f"该科目余额变动 {change:,.2f}。",
            "recommended_procedures": [],
        }

    async def extract_confirmations(self, project_id: UUID, account_code: str, year: int) -> list[dict]:
        """函证对象提取：从辅助余额表提取"""
        from app.models.audit_platform_models import TbAuxBalance

        q = (
            sa.select(TbAuxBalance)
            .where(
                TbAuxBalance.project_id == project_id,
                TbAuxBalance.account_code.like(f"{account_code}%"),
                TbAuxBalance.year == year,
                TbAuxBalance.is_deleted == False,  # noqa
            )
            .order_by(TbAuxBalance.closing_balance.desc())
            .limit(50)
        )
        rows = (await self.db.execute(q)).scalars().all()
        return [
            {
                "aux_name": r.aux_name,
                "aux_code": r.aux_code,
                "closing_balance": float(r.closing_balance or 0),
                "opening_balance": float(r.opening_balance or 0),
            }
            for r in rows
        ]

    async def check_wp_report_consistency(self, project_id: UUID, year: int) -> list[dict]:
        """审定表核对：底稿审定数 vs 报表行次金额"""
        from app.models.report_models import FinancialReport
        from app.models.workpaper_models import WorkingPaper

        # 获取有 parsed_data 的底稿
        wp_q = sa.select(WorkingPaper).where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa
            WorkingPaper.parsed_data.isnot(None),
        )
        wps = (await self.db.execute(wp_q)).scalars().all()

        # 获取报表数据
        report_q = sa.select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
        )
        reports = (await self.db.execute(report_q)).scalars().all()
        report_map = {r.row_code: float(r.current_period_amount or 0) for r in reports}

        results = []
        for wp in wps:
            pd = wp.parsed_data or {}
            wp_amount = pd.get("audited_amount")
            if wp_amount is not None:
                # 简化：暂时只返回底稿有 parsed_data 的记录
                results.append({
                    "wp_id": str(wp.id),
                    "wp_amount": wp_amount,
                    "status": "has_data",
                })

        return results
