"""试算表完整视图服务 — 科目级调整分列聚合

提供 TB 完整视图（原报+AJE+RJE+其他调整=审定），
平衡公式校验，期初核对。

Requirements: 1.1~1.5, 2.1~2.4
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance

_logger = logging.getLogger(__name__)


class TrialBalanceFullViewService:
    """TB 完整视图"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_full_view(
        self, project_id: UUID, year: int
    ) -> list[dict[str, Any]]:
        """返回科目级完整视图：未审+AJE+RJE+审定，含平衡校验标记。"""
        stmt = (
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
            )
            .order_by(TrialBalance.standard_account_code)
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        view = []
        for row in rows:
            unadjusted = row.unadjusted_amount or Decimal("0")
            aje = row.aje_adjustment or Decimal("0")
            rje = row.rje_adjustment or Decimal("0")
            audited = row.audited_amount or Decimal("0")
            other_adj = audited - unadjusted - aje - rje
            balance_ok = abs(unadjusted + aje + rje + other_adj - audited) < Decimal("0.01")

            view.append({
                "account_code": row.standard_account_code,
                "account_name": row.account_name,
                "unadjusted": unadjusted,
                "aje_adjustment": aje,
                "rje_adjustment": rje,
                "other_adjustment": other_adj,
                "audited": audited,
                "opening_balance": row.opening_balance or Decimal("0"),
                "balance_ok": balance_ok,
            })
        return view

    async def check_balance_formula(
        self, project_id: UUID, year: int
    ) -> dict[str, Any]:
        """平衡公式校验：SUM(未审+AJE+RJE+其他) == SUM(审定)"""
        view = await self.get_full_view(project_id, year)
        total_unadj = sum(r["unadjusted"] for r in view)
        total_aje = sum(r["aje_adjustment"] for r in view)
        total_rje = sum(r["rje_adjustment"] for r in view)
        total_other = sum(r["other_adjustment"] for r in view)
        total_audited = sum(r["audited"] for r in view)

        computed = total_unadj + total_aje + total_rje + total_other
        diff = abs(computed - total_audited)

        return {
            "total_unadjusted": total_unadj,
            "total_aje": total_aje,
            "total_rje": total_rje,
            "total_other": total_other,
            "total_audited": total_audited,
            "computed_total": computed,
            "difference": diff,
            "balanced": diff < Decimal("0.01"),
            "account_count": len(view),
        }

    async def reconcile_opening_balance(
        self, project_id: UUID, year: int, prior_project_id: UUID | None = None
    ) -> dict[str, Any]:
        """期初核对：本年期初 vs 上年审定差异列表。"""
        # 本年期初
        stmt = sa.select(
            TrialBalance.standard_account_code,
            TrialBalance.account_name,
            TrialBalance.opening_balance,
        ).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
        )
        result = await self.db.execute(stmt)
        current_opening: dict[str, dict] = {}
        for code, name, opening in result.all():
            current_opening[code] = {"name": name, "opening": opening or Decimal("0")}

        # 上年审定（如果有 prior_project_id）
        prior_audited: dict[str, Decimal] = {}
        if prior_project_id:
            stmt2 = sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.audited_amount,
            ).where(
                TrialBalance.project_id == prior_project_id,
                TrialBalance.year == year - 1,
            )
            result2 = await self.db.execute(stmt2)
            for code, audited in result2.all():
                prior_audited[code] = audited or Decimal("0")

        # 差异
        differences = []
        matched = 0
        for code, info in current_opening.items():
            prior_val = prior_audited.get(code, Decimal("0"))
            diff = info["opening"] - prior_val
            if abs(diff) > Decimal("0.01"):
                differences.append({
                    "account_code": code,
                    "account_name": info["name"],
                    "current_opening": info["opening"],
                    "prior_audited": prior_val,
                    "difference": diff,
                })
            else:
                matched += 1

        return {
            "total_accounts": len(current_opening),
            "matched": matched,
            "differences": differences,
            "has_prior": prior_project_id is not None,
            "reconciled": len(differences) == 0,
        }
