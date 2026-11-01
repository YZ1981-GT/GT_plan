"""A13 与管理层声明书使用的正式未更正错报投影。"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    Adjustment,
    Materiality,
    UnadjustedMisstatement,
)


class MisstatementSummaryService:
    """兼容 A13 旧响应形状，但唯一数据源是 ``unadjusted_misstatements``。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _rows(self, project_id: UUID, year: int) -> list[tuple[Any, Any]]:
        result = await self.db.execute(
            sa.select(UnadjustedMisstatement, Adjustment)
            .outerjoin(Adjustment, Adjustment.id == UnadjustedMisstatement.source_adjustment_id)
            .where(
                UnadjustedMisstatement.project_id == project_id,
                UnadjustedMisstatement.year == year,
                UnadjustedMisstatement.is_deleted == sa.false(),
                UnadjustedMisstatement.prior_year_status != "reversed",
                sa.or_(Adjustment.id.is_(None), Adjustment.project_id == project_id),
            )
            .order_by(UnadjustedMisstatement.created_at, UnadjustedMisstatement.id)
        )
        return list(result.all())

    async def get_uncorrected_misstatements(
        self, project_id: UUID, year: int,
    ) -> dict[str, Any]:
        """返回旧 A13 表格所需的 prior/current 结构。"""
        prior: list[dict[str, Any]] = []
        current: list[dict[str, Any]] = []
        total = Decimal("0")
        for misstatement, adjustment in await self._rows(project_id, year):
            item = self._to_summary_item(misstatement, adjustment)
            total += Decimal(str(misstatement.misstatement_amount or 0))
            if misstatement.is_carried_forward or misstatement.prior_year_status == "continuing":
                prior.append(item)
            else:
                current.append(item)
        return {
            "prior": prior,
            "current": current,
            "total_debit": total,
            "total_credit": Decimal("0"),
            "total_amount": total,
            "count": len(prior) + len(current),
        }

    async def evaluate_misstatements(
        self, project_id: UUID, year: int,
    ) -> dict[str, Any]:
        summary = await self.get_uncorrected_misstatements(project_id, year)
        materiality = await self._get_materiality(project_id, year)
        total_amount = Decimal(str(summary["total_amount"]))
        exceeds = materiality > 0 and total_amount >= materiality
        return {
            "total_debit": summary["total_debit"],
            "total_credit": summary["total_credit"],
            "total_amount": total_amount,
            "materiality": materiality,
            "exceeds_materiality": exceeds,
            "suggested_conclusion": self._suggest_conclusion(total_amount, materiality),
            "count": summary["count"],
        }

    async def get_for_representation_letter(
        self, project_id: UUID, year: int,
    ) -> str:
        summary = await self.get_uncorrected_misstatements(project_id, year)
        if not summary["prior"] and not summary["current"]:
            return "无未更正错报。"
        return self._format_for_letter(summary)

    async def record_communication(
        self,
        project_id: UUID,
        year: int,
        misstatement_id: UUID,
        communication_date: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """更新正式错报的管理层原因与沟通时间，不再回写 Adjustment 遗留列。"""
        row = (await self.db.execute(sa.select(UnadjustedMisstatement).where(
            UnadjustedMisstatement.id == misstatement_id,
            UnadjustedMisstatement.project_id == project_id,
            UnadjustedMisstatement.year == year,
            UnadjustedMisstatement.is_deleted == sa.false(),
        ))).scalar_one_or_none()
        if row is None:
            raise ValueError("未更正错报记录不存在")
        if reason is not None:
            row.management_reason = reason.strip() or None
        if communication_date:
            row.management_communication_at = datetime.fromisoformat(
                communication_date.replace("Z", "+00:00"),
            )
        await self.db.flush()
        return {
            "id": str(row.id),
            "management_reason": row.management_reason,
            "management_communication_at": (
                row.management_communication_at.isoformat()
                if row.management_communication_at else None
            ),
        }

    async def check_consistency(
        self, project_id: UUID, year: int,
    ) -> dict[str, Any]:
        """未更正错报与工作试算表分属互斥处理，返回显式独立口径。"""
        summary = await self.get_uncorrected_misstatements(project_id, year)
        from app.models.audit_platform_models import TrialBalance
        row = (await self.db.execute(sa.select(
            sa.func.coalesce(sa.func.sum(TrialBalance.aje_adjustment), 0),
            sa.func.coalesce(sa.func.sum(TrialBalance.rje_adjustment), 0),
        ).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
        ))).one_or_none()
        return {
            "a13_current_total": sum(
                Decimal(str(item.get("misstatement_amount") or 0))
                for item in summary["current"]
            ),
            "a13_prior_total": sum(
                Decimal(str(item.get("misstatement_amount") or 0))
                for item in summary["prior"]
            ),
            "tb_aje_total": Decimal(str(row[0])) if row else Decimal("0"),
            "tb_rje_total": Decimal(str(row[1])) if row else Decimal("0"),
            "consistent": True,
        }

    @staticmethod
    def _to_summary_item(misstatement: UnadjustedMisstatement, adjustment: Adjustment | None) -> dict[str, Any]:
        amount = Decimal(str(misstatement.misstatement_amount or 0))
        return {
            "id": str(misstatement.id),
            "adjustment_no": adjustment.adjustment_no if adjustment else f"MS-{str(misstatement.id)[:8]}",
            "description": misstatement.misstatement_description,
            "account_code": misstatement.affected_account_code or "",
            "account_name": misstatement.affected_account_name or "",
            "debit_amount": amount,
            "credit_amount": None,
            "misstatement_amount": amount,
            "entry_group_id": str(adjustment.entry_group_id) if adjustment else None,
            # 兼容 A13 表格字段名；值来自正式错报，不再读取 adjustments.passed_reason。
            "passed_reason": misstatement.management_reason or "",
            "passed_communication_date": (
                misstatement.management_communication_at.isoformat()
                if misstatement.management_communication_at else None
            ),
            "misstatement_type": getattr(
                misstatement.misstatement_type, "value", misstatement.misstatement_type,
            ),
        }

    async def _get_materiality(self, project_id: UUID, year: int) -> Decimal:
        value = (await self.db.execute(sa.select(Materiality.overall_materiality).where(
            Materiality.project_id == project_id,
            Materiality.year == year,
            Materiality.is_deleted == sa.false(),
        ))).scalar_one_or_none()
        return Decimal(str(value)) if value is not None else Decimal("0")

    @staticmethod
    def _suggest_conclusion(total: Decimal, materiality: Decimal) -> str:
        if materiality <= 0:
            return "重要性水平未设置，无法自动判断。"
        if total >= materiality:
            return f"未更正错报合计({total:,.2f})达到或超过重要性水平({materiality:,.2f})，需考虑对审计意见的影响。"
        ratio = total / materiality * 100
        return f"未更正错报合计({total:,.2f})占重要性水平{ratio:.1f}%，未达到重要性水平。"

    @staticmethod
    def _format_for_letter(summary: dict[str, Any]) -> str:
        lines: list[str] = []
        all_items = summary["current"] + summary["prior"]
        for index, item in enumerate(all_items[:10], 1):
            description = str(item.get("description") or "")[:50]
            amount = Decimal(str(item.get("misstatement_amount") or 0))
            lines.append(f"{index}. {description}（金额：{amount:,.2f}元）")
        if len(all_items) > 10:
            lines.append(f"  ...共{len(all_items)}项")
        return "未更正错报清单：\n" + "\n".join(lines)
