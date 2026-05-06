"""AI 辅助底稿编制服务

Phase 9 Task 9.8: 分析性复核 + 函证对象提取 + 审定表核对
R3 Sprint 4 Task 21: AI 内容统一结构化
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def wrap_ai_content(
    value: str | dict,
    source_model: str,
    confidence: float,
    confirmed_by: UUID | None = None,
    confirmed_at: datetime | None = None,
) -> dict:
    """将 AI 输出包装为统一结构化格式。

    R3 Sprint 4 Task 21: 所有 AI 输出必须包装为此结构，
    以便门禁规则 AIContentMustBeConfirmedRule 检查确认状态。

    Args:
        value: AI 生成的原始内容（文本或结构化数据）
        source_model: 生成该内容的模型标识（如 'qwen3.5-27b'）
        confidence: 模型置信度 [0.0, 1.0]
        confirmed_by: 确认人 UUID（未确认时为 None）
        confirmed_at: 确认时间（未确认时为 None）

    Returns:
        统一结构化 dict
    """
    return {
        "type": "ai_generated",
        "source_model": source_model,
        "confidence": confidence,
        "confirmed_by": str(confirmed_by) if confirmed_by else None,
        "confirmed_at": confirmed_at.isoformat() if confirmed_at else None,
        "value": value,
    }


class WpAIService:
    """AI 辅助底稿编制"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analytical_review(self, project_id: UUID, account_code: str, year: int) -> dict:
        """分析性复核：变动分析 + LLM 生成分析文本"""
        from app.models.audit_platform_models import TrialBalance
        from app.services.task_center import create_task, update_task, TaskType, TaskStatus

        task_id = create_task(
            TaskType.ai_analysis,
            project_id=str(project_id),
            params={"account_code": account_code, "year": year, "action": "analytical_review"},
        )
        update_task(task_id, TaskStatus.processing)

        try:
            q = sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.year == year,
                TrialBalance.is_deleted == False,  # noqa
            )
            tb = (await self.db.execute(q)).scalar_one_or_none()
            if not tb:
                update_task(task_id, TaskStatus.failed, error="科目未找到")
                return {"error": f"科目 {account_code} 未找到"}

            current = float(tb.audited_debit or 0) - float(tb.audited_credit or 0)
            prior = float(tb.unadjusted_debit or 0) - float(tb.unadjusted_credit or 0)
            change = current - prior
            rate = round(change / prior * 100, 2) if prior != 0 else None
            is_significant = abs(rate or 0) > 20 if rate is not None else abs(change) > 0

            # 调用 LLM 生成分析文本（RAG: 参照上年底稿分析结论）
            from app.services.llm_client import chat_completion
            from app.services.reference_doc_service import ReferenceDocService

            context_docs = await ReferenceDocService.load_context(
                self.db, project_id, year,
                source_type="prior_year_workpaper",
                wp_code=None,  # 按科目匹配
                knowledge_keywords=[account_code],
            )

            prompt = f"科目 {account_code}，本期余额 {current:,.2f}，上期余额 {prior:,.2f}，变动额 {change:,.2f}，变动率 {rate}%。请用一句话分析变动原因。"
            try:
                ai_text = await chat_completion([
                    {"role": "system", "content": "你是审计分析师，请简洁分析科目余额变动原因。如有上年分析参照请对比。"},
                    {"role": "user", "content": prompt},
                ], context_documents=context_docs if context_docs else None)
                source_model = "qwen3.5-27b"
            except Exception:
                ai_text = f"该科目余额变动 {change:,.2f}，变动率 {rate}%。"
                source_model = "fallback"

            # R3 Sprint 4: AI 输出统一结构化
            ai_analysis_wrapped = wrap_ai_content(
                value=ai_text,
                source_model=source_model,
                confidence=0.8 if source_model != "fallback" else 0.0,
            )

            update_task(task_id, TaskStatus.success)
            return {
                "account_code": account_code,
                "current_balance": current,
                "prior_balance": prior,
                "change_amount": change,
                "change_rate": rate,
                "is_significant": is_significant,
                "ai_analysis": ai_analysis_wrapped,
                "recommended_procedures": [],
                "task_id": task_id,
            }
        except Exception as e:
            update_task(task_id, TaskStatus.failed, error=str(e))
            raise

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
