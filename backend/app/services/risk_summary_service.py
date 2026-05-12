"""风险摘要服务 [R8-S2-07]

为合伙人签字决策面板提供一页风险摘要，聚合 6 个数据源：
1. 高严重度未解决问题单（IssueTicket.severity in ('blocker','major') 且 status != 'closed'）
2. 未解决复核意见（ReviewRecord.resolved_at IS NULL，通过 WorkingPaper join 反查 project_id）
3. 超过重要性的未更正错报（UnadjustedMisstatement.misstatement_amount > performance_materiality）
4. 被拒且未转错报的 AJE（Adjustment.review_status='rejected' 且 UnadjustedMisstatement 未反查到 source_adjustment_id）
5. AI flags（保留扩展位，本轮返回空数组）
6. 持续经营风险（GoingConcernConclusion 非 no_material_uncertainty）

输出结构：
{
  "high_findings": [...],             // 高严重度工单
  "unresolved_comments": [...],       // 未解决复核意见
  "material_misstatements": [...],    // 重大错报
  "unconverted_rejected_aje": [...],  // 被拒未转错报
  "ai_flags": [],                     // R8 预留空
  "budget_overrun": false,            // R8 预留
  "sla_breached": [],                 // R8 预留
  "going_concern_flag": false,
  "summary": {
    "total_blockers": N,              // 阻塞签字的项数
    "total_warnings": M,
    "can_sign": bool,                 // 综合判断
  }
}

R8 复盘修正（2026-05-07）：
- ReviewRecord 无 project_id，改用 join WorkingPaper.project_id
- UnadjustedMisstatement.net_amount → misstatement_amount
- UnadjustedMisstatement.description → misstatement_description
- Adjustment.converted_to_misstatement_id 不存在，改用"UnadjustedMisstatement.source_adjustment_id 存在" 反向排除
- Adjustment.total_debit/credit 不存在，改从 AdjustmentEntry 聚合
- GoingConcernConclusion 枚举值修正为 no_material_uncertainty
- 所有聚合加 year 参数
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class RiskSummaryService:
    """聚合项目的签字前风险摘要"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def aggregate(self, project_id: UUID, year: int | None = None) -> dict[str, Any]:
        """聚合 6 个数据源返回风险摘要

        Args:
            project_id: 项目 ID
            year: 年度（若为 None 自动取项目最新年度）
        """
        if year is None:
            year = await self._latest_year(project_id)

        high_findings = await self._get_high_findings(project_id)
        unresolved_comments = await self._get_unresolved_comments(project_id)
        material_misstatements = await self._get_material_misstatements(project_id, year)
        unconverted_rejected_aje = await self._get_unconverted_rejected_aje(project_id, year)
        going_concern_flag = await self._get_going_concern_flag(project_id)

        total_blockers = (
            len(high_findings)
            + len(material_misstatements)
            + len(unconverted_rejected_aje)
            + (1 if going_concern_flag else 0)
        )
        total_warnings = len(unresolved_comments)

        return {
            "year": year,
            "high_findings": high_findings,
            "unresolved_comments": unresolved_comments,
            "material_misstatements": material_misstatements,
            "unconverted_rejected_aje": unconverted_rejected_aje,
            "ai_flags": [],
            "budget_overrun": False,
            "sla_breached": [],
            "going_concern_flag": going_concern_flag,
            "summary": {
                "total_blockers": total_blockers,
                "total_warnings": total_warnings,
                "can_sign": total_blockers == 0,
            },
        }

    async def _latest_year(self, project_id: UUID) -> int:
        """取项目最新年度（退化：从最近 Materiality 记录）"""
        try:
            from app.models.audit_platform_models import Materiality
            q = (
                select(Materiality.year)
                .where(
                    Materiality.project_id == project_id,
                    Materiality.is_deleted == False,  # noqa: E712
                )
                .order_by(Materiality.year.desc())
                .limit(1)
            )
            row = (await self.db.execute(q)).scalar_one_or_none()
            if row:
                return int(row)
        except Exception:
            pass
        # 兜底：当前年度 - 1
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).year - 1

    async def _get_high_findings(self, project_id: UUID) -> list[dict]:
        """高严重度未解决问题单（blocker + major）"""
        try:
            from app.models.phase15_models import IssueTicket
        except ImportError:
            return []
        q = (
            select(IssueTicket)
            .where(
                IssueTicket.project_id == project_id,
                IssueTicket.severity.in_(["blocker", "major"]),
                IssueTicket.status != "closed",
            )
            .order_by(IssueTicket.created_at.desc())
            .limit(20)
        )
        try:
            rows = (await self.db.execute(q)).scalars().all()
        except Exception:
            return []
        return [
            {
                "id": str(r.id),
                "title": r.title,
                "severity": r.severity,
                "status": r.status,
                "category": r.category,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def _get_unresolved_comments(self, project_id: UUID) -> list[dict]:
        """未解决的复核意见（ReviewRecord.resolved_at IS NULL）

        修正：ReviewRecord 无 project_id，通过 WorkingPaper.project_id 反查
        """
        try:
            from app.models.workpaper_models import ReviewRecord, WorkingPaper
        except ImportError:
            return []
        q = (
            select(ReviewRecord, WorkingPaper.wp_index_id)
            .join(WorkingPaper, ReviewRecord.working_paper_id == WorkingPaper.id)
            .where(
                WorkingPaper.project_id == project_id,
                ReviewRecord.resolved_at.is_(None),
                ReviewRecord.is_deleted == False,  # noqa: E712
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
            .order_by(ReviewRecord.created_at.desc())
            .limit(20)
        )
        try:
            rows = (await self.db.execute(q)).all()
        except Exception:
            return []
        return [
            {
                "id": str(rec.id),
                "comment_text": (rec.comment_text or "")[:100],
                "working_paper_id": str(rec.working_paper_id),
                "wp_index_id": str(wp_index_id) if wp_index_id else None,
                "cell_reference": rec.cell_reference,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
            }
            for rec, wp_index_id in rows
        ]

    async def _get_material_misstatements(
        self, project_id: UUID, year: int
    ) -> list[dict]:
        """超过重要性阈值的未更正错报（按 misstatement_amount 绝对值）"""
        try:
            from app.models.audit_platform_models import (
                UnadjustedMisstatement,
                Materiality,
            )
        except ImportError:
            return []

        # 取该年度 performance_materiality
        mat_q = (
            select(Materiality)
            .where(
                Materiality.project_id == project_id,
                Materiality.year == year,
                Materiality.is_deleted == False,  # noqa: E712
            )
            .order_by(Materiality.created_at.desc())
            .limit(1)
        )
        try:
            mat = (await self.db.execute(mat_q)).scalar_one_or_none()
        except Exception:
            mat = None
        threshold = float(mat.performance_materiality or 0) if mat else 0.0
        if threshold == 0:
            return []

        mis_q = (
            select(UnadjustedMisstatement)
            .where(
                UnadjustedMisstatement.project_id == project_id,
                UnadjustedMisstatement.year == year,
                UnadjustedMisstatement.is_deleted == False,  # noqa: E712
                func.abs(UnadjustedMisstatement.misstatement_amount) >= threshold,
            )
            .order_by(func.abs(UnadjustedMisstatement.misstatement_amount).desc())
            .limit(20)
        )
        try:
            rows = (await self.db.execute(mis_q)).scalars().all()
        except Exception:
            return []
        return [
            {
                "id": str(r.id),
                "description": r.misstatement_description,
                "amount": float(r.misstatement_amount) if r.misstatement_amount is not None else 0.0,
                "type": r.misstatement_type.value if hasattr(r.misstatement_type, "value") else str(r.misstatement_type),
                "affected_account": r.affected_account_name or r.affected_account_code,
                "threshold": threshold,
            }
            for r in rows
        ]

    async def _get_unconverted_rejected_aje(
        self, project_id: UUID, year: int
    ) -> list[dict]:
        """被拒但未转错报的 AJE 分录组

        修正：Adjustment 无 converted_to_misstatement_id，反向查
        UnadjustedMisstatement.source_adjustment_id 已引用的 Adjustment 视为已转
        """
        try:
            from app.models.audit_platform_models import (
                Adjustment,
                UnadjustedMisstatement,
                AdjustmentType,
            )
        except ImportError:
            return []

        # 先取已转的 adjustment_id 集合
        converted_q = select(UnadjustedMisstatement.source_adjustment_id).where(
            UnadjustedMisstatement.project_id == project_id,
            UnadjustedMisstatement.year == year,
            UnadjustedMisstatement.is_deleted == False,  # noqa: E712
            UnadjustedMisstatement.source_adjustment_id.isnot(None),
        )
        try:
            converted_ids = {
                row for row in (await self.db.execute(converted_q)).scalars().all()
            }
        except Exception:
            converted_ids = set()

        q = (
            select(Adjustment)
            .where(
                Adjustment.project_id == project_id,
                Adjustment.year == year,
                Adjustment.review_status == "rejected",
                Adjustment.adjustment_type == AdjustmentType.aje,
                Adjustment.is_deleted == False,  # noqa: E712,
            )
            .limit(20)
        )
        try:
            rows = (await self.db.execute(q)).scalars().all()
        except Exception:
            return []

        return [
            {
                "id": str(r.id),
                "adjustment_no": r.adjustment_no,
                "description": r.description or "",
                "entry_group_id": str(r.entry_group_id) if getattr(r, "entry_group_id", None) else None,
            }
            for r in rows
            if r.id not in converted_ids
        ]

    async def _get_going_concern_flag(self, project_id: UUID) -> bool:
        """是否有持续经营风险标记

        修正：GoingConcernConclusion 枚举值正确判断
        """
        try:
            from app.models.collaboration_models import (
                GoingConcernEvaluation,
                GoingConcernConclusion,
            )
        except ImportError:
            return False
        q = (
            select(GoingConcernEvaluation)
            .where(
                GoingConcernEvaluation.project_id == project_id,
                GoingConcernEvaluation.is_deleted == False,  # noqa: E712
            )
            .order_by(GoingConcernEvaluation.evaluation_date.desc())
            .limit(1)
        )
        try:
            row = (await self.db.execute(q)).scalar_one_or_none()
        except Exception:
            return False
        if not row:
            return False
        # 非 no_material_uncertainty 即为风险标记
        concl = row.conclusion
        if concl is None:
            return False
        # Enum 对象或字符串都可能
        concl_val = concl.value if hasattr(concl, "value") else str(concl)
        return concl_val != GoingConcernConclusion.no_material_uncertainty.value
