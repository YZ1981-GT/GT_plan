"""报告复核溯源服务 — Phase 10 Task 9.1"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger, TrialBalance

logger = logging.getLogger(__name__)


class ReportTraceService:
    """报告复核溯源"""

    async def trace_section(
        self, db: AsyncSession, project_id: UUID, section_number: str,
    ) -> dict[str, Any]:
        """溯源查询：附注科目 → 底稿 → 试算表 → 序时账"""
        trace = {
            "section_number": section_number,
            "note_data": None,
            "workpaper_data": None,
            "trial_balance_data": None,
            "top_ledger_entries": [],
        }

        # 1. 查附注-底稿映射
        try:
            mapping_result = await db.execute(sa.text(
                "SELECT wp_code, account_codes, note_title "
                "FROM note_wp_mapping "
                "WHERE project_id = :pid AND note_section = :sec "
                "LIMIT 1"
            ), {"pid": str(project_id), "sec": section_number})
            mapping = mapping_result.first()
            if mapping:
                trace["note_data"] = {
                    "wp_code": mapping.wp_code,
                    "account_codes": mapping.account_codes,
                    "note_title": mapping.note_title,
                }
                # 2. 查底稿 parsed_data
                wp_result = await db.execute(sa.text(
                    "SELECT wp.parsed_data FROM working_papers wp "
                    "JOIN wp_index wi ON wp.wp_index_id = wi.id "
                    "WHERE wi.project_id = :pid AND wi.wp_code = :code "
                    "LIMIT 1"
                ), {"pid": str(project_id), "code": mapping.wp_code})
                wp_row = wp_result.first()
                if wp_row and wp_row.parsed_data:
                    trace["workpaper_data"] = wp_row.parsed_data
        except Exception as e:
            logger.warning("溯源映射查询失败: %s", e)

        # 3. 查试算表
        try:
            tb_result = await db.execute(
                sa.select(TrialBalance)
                .where(TrialBalance.project_id == project_id, TrialBalance.is_deleted == sa.false())
                .limit(5)
            )
            tb_rows = tb_result.scalars().all()
            if tb_rows:
                trace["trial_balance_data"] = [
                    {
                        "account_code": t.standard_account_code,
                        "account_name": t.account_name,
                        "opening": float(t.opening_balance or 0),
                        "audited": float(t.audited_amount or 0) if hasattr(t, "audited_amount") else 0,
                    }
                    for t in tb_rows[:5]
                ]
        except Exception:
            pass

        # 4. 查大额序时账
        try:
            ledger_result = await db.execute(
                sa.select(TbLedger)
                .where(TbLedger.project_id == project_id, TbLedger.is_deleted == sa.false())
                .order_by(TbLedger.debit_amount.desc().nullslast())
                .limit(10)
            )
            for r in ledger_result.scalars().all():
                trace["top_ledger_entries"].append({
                    "voucher_no": r.voucher_no,
                    "date": r.voucher_date.isoformat() if r.voucher_date else None,
                    "debit": float(r.debit_amount or 0),
                    "credit": float(r.credit_amount or 0),
                    "summary": r.summary or "",
                })
        except Exception:
            pass

        return trace

    async def get_findings_summary(
        self, db: AsyncSession, project_id: UUID,
    ) -> dict[str, Any]:
        """统一 findings 视图"""
        # 汇总各来源的 findings
        summary = {"llm_findings": 0, "manual_findings": 0, "total": 0}
        try:
            # AI 内容 findings
            ai_result = await db.execute(sa.text(
                "SELECT COUNT(*) FROM ai_contents "
                "WHERE project_id = :pid AND confirmation_status = 'pending'"
            ), {"pid": str(project_id)})
            summary["llm_findings"] = ai_result.scalar() or 0
        except Exception:
            pass
        try:
            # 批注 findings
            ann_result = await db.execute(sa.text(
                "SELECT COUNT(*) FROM cell_annotations "
                "WHERE project_id = :pid AND status = 'pending' AND is_deleted = false"
            ), {"pid": str(project_id)})
            summary["manual_findings"] = ann_result.scalar() or 0
        except Exception:
            pass
        summary["total"] = summary["llm_findings"] + summary["manual_findings"]
        return summary
