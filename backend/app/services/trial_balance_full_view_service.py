"""试算表完整视图服务 — 科目级调整分列聚合（spec citar-report-analysis §2.4 / §2.5）。

- 完整视图：未审 + AJE + RJE + 底稿调整 + 其他 = 审定
- 平衡校验：「其他调整」= 审定 − 各已知分量，是**倒挤数**，拿它再去验平衡必然成立
  （旧实现即如此，平衡恒为真）。现改判「没有科目存在说不清来源的调整」，并列出这些科目
- 期初核对：本年期初 vs 上年项目审定。上年项目按平台单一来源 ``prior_year_context.find_prior_project``；
  找不到写原因，不再把上年审定当 0 列出满屏假差异

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

_TOLERANCE = Decimal("0.01")


class TrialBalanceFullViewService:
    """TB 完整视图"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_full_view(
        self, project_id: UUID, year: int
    ) -> list[dict[str, Any]]:
        """科目级完整视图；``balance_ok`` = 本科目没有说不清来源的调整（其他调整为 0）。"""
        stmt = (
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
            .order_by(TrialBalance.standard_account_code)
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        view = []
        for row in rows:
            unadjusted = row.unadjusted_amount or Decimal("0")
            aje = row.aje_adjustment or Decimal("0")
            rje = row.rje_adjustment or Decimal("0")
            wp_adj = row.wp_adjustment or Decimal("0")
            audited = row.audited_amount if row.audited_amount is not None else unadjusted + aje + rje + wp_adj
            other_adj = audited - unadjusted - aje - rje - wp_adj
            view.append({
                "account_code": row.standard_account_code,
                "account_name": row.account_name,
                "unadjusted": unadjusted,
                "aje_adjustment": aje,
                "rje_adjustment": rje,
                "wp_adjustment": wp_adj,
                "other_adjustment": other_adj,
                "audited": audited,
                "opening_balance": row.opening_balance or Decimal("0"),
                "balance_ok": abs(other_adj) < _TOLERANCE,
            })
        return view

    async def check_balance_formula(
        self, project_id: UUID, year: int
    ) -> dict[str, Any]:
        """平衡校验：未审 + AJE + RJE + 底稿调整 是否逐科目等于审定数。"""
        view = await self.get_full_view(project_id, year)
        total_unadj = sum((r["unadjusted"] for r in view), Decimal("0"))
        total_aje = sum((r["aje_adjustment"] for r in view), Decimal("0"))
        total_rje = sum((r["rje_adjustment"] for r in view), Decimal("0"))
        total_wp_adj = sum((r["wp_adjustment"] for r in view), Decimal("0"))
        total_other = sum((r["other_adjustment"] for r in view), Decimal("0"))
        total_audited = sum((r["audited"] for r in view), Decimal("0"))

        computed = total_unadj + total_aje + total_rje + total_wp_adj
        unexplained = [
            {"account_code": r["account_code"], "account_name": r["account_name"],
             "amount": r["other_adjustment"]}
            for r in view if not r["balance_ok"]
        ]
        return {
            "total_unadjusted": total_unadj,
            "total_aje": total_aje,
            "total_rje": total_rje,
            "total_wp_adjustment": total_wp_adj,
            "total_other": total_other,
            "total_audited": total_audited,
            "computed_total": computed,
            "difference": abs(computed - total_audited),
            "balanced": not unexplained,
            "unexplained": unexplained,
            "account_count": len(view),
        }

    async def reconcile_opening_balance(
        self, project_id: UUID, year: int, prior_project_id: UUID | None = None
    ) -> dict[str, Any]:
        """期初核对：本年试算表期初 vs 上年项目 ``year-1`` 审定数。"""
        current = await self._tb_amounts(project_id, year, opening=True)

        prior_pid = prior_project_id
        reason = ""
        if prior_pid is None:
            from app.services.prior_year_context import find_prior_project

            found = await find_prior_project(self.db, project_id, year)
            prior_pid, reason = found.project_id, found.reason
        base = {
            "total_accounts": len(current),
            "prior_project_id": str(prior_pid) if prior_pid else None,
        }
        if prior_pid is None:
            return {**base, "has_prior": False, "reason": reason, "matched": 0,
                    "differences": [], "reconciled": None}

        prior = await self._tb_amounts(prior_pid, year - 1, opening=False)
        if not prior:
            return {**base, "has_prior": False,
                    "reason": f"上年项目没有 {year - 1} 年试算表",
                    "matched": 0, "differences": [], "reconciled": None}

        differences = []
        matched = 0
        for code in sorted(set(current) | set(prior)):
            cur = current.get(code)
            pri = prior.get(code)
            cur_amt = cur[1] if cur else Decimal("0")
            pri_amt = pri[1] if pri else Decimal("0")
            diff = cur_amt - pri_amt
            if abs(diff) < _TOLERANCE:
                matched += 1
                continue
            differences.append({
                "account_code": code,
                "account_name": (cur or pri)[0],
                "current_opening": cur_amt,
                "prior_audited": pri_amt,
                "difference": diff,
                "note": "本年无此科目" if cur is None else ("上年无此科目" if pri is None else ""),
            })
        return {**base, "total_accounts": len(set(current) | set(prior)),
                "has_prior": True, "reason": "", "matched": matched,
                "differences": differences, "reconciled": not differences}

    async def _tb_amounts(
        self, project_id: UUID, year: int, *, opening: bool
    ) -> dict[str, tuple[str | None, Decimal]]:
        col = TrialBalance.opening_balance if opening else TrialBalance.audited_amount
        rows = (await self.db.execute(
            sa.select(TrialBalance.standard_account_code, TrialBalance.account_name, col).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )).all()
        return {code: (name, amount or Decimal("0")) for code, name, amount in rows}
