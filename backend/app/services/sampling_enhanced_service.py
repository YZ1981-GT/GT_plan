"""抽样程序增强服务 — Phase 10 Task 6.1-6.4

截止性测试、账龄分析（FIFO）、月度明细填充、抽样结果与底稿关联。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger, TbAuxLedger
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)


class CutoffTestService:
    """截止性测试"""

    async def run_cutoff_test(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        account_codes: list[str],
        days_before: int = 5,
        days_after: int = 5,
        amount_threshold: float = 10000,
    ) -> dict[str, Any]:
        """从 tb_ledger 提取期末前后 N 天交易"""
        period_end = date(year, 12, 31)
        start_date = period_end - timedelta(days=days_before)
        end_date = period_end + timedelta(days=days_after)

        stmt = (
            sa.select(TbLedger)
            .where(
                await get_active_filter(db, TbLedger.__table__, project_id, year),
                TbLedger.account_code.in_(account_codes),
                TbLedger.voucher_date >= start_date,
                TbLedger.voucher_date <= end_date,
                sa.or_(
                    TbLedger.debit_amount > amount_threshold,
                    TbLedger.credit_amount > amount_threshold,
                ),
            )
            .order_by(TbLedger.voucher_date, TbLedger.voucher_no)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        entries = []
        for r in rows:
            entries.append({
                "voucher_no": r.voucher_no,
                "voucher_date": r.voucher_date.isoformat() if r.voucher_date else None,
                "account_code": r.account_code,
                "account_name": r.account_name or "",
                "debit_amount": float(r.debit_amount or 0),
                "credit_amount": float(r.credit_amount or 0),
                "summary": r.summary or "",
                "is_before_cutoff": r.voucher_date <= period_end if r.voucher_date else True,
            })

        return {
            "period_end": period_end.isoformat(),
            "window": f"{start_date.isoformat()} ~ {end_date.isoformat()}",
            "threshold": amount_threshold,
            "total_entries": len(entries),
            "before_cutoff": sum(1 for e in entries if e["is_before_cutoff"]),
            "after_cutoff": sum(1 for e in entries if not e["is_before_cutoff"]),
            "entries": entries,
        }


class AgingAnalysisService:
    """账龄分析 — FIFO 先进先出核销算法"""

    async def analyze_aging(
        self,
        db: AsyncSession,
        project_id: UUID,
        account_code: str,
        aging_brackets: list[dict[str, Any]],
        base_date: str,
        year: int | None = None,
    ) -> dict[str, Any]:
        """FIFO 账龄分析

        aging_brackets: [{"label": "1年以内", "min_days": 0, "max_days": 365}, ...]
        """
        base = date.fromisoformat(base_date)

        # 查询辅助明细账
        if year:
            conditions = [
                await get_active_filter(db, TbAuxLedger.__table__, project_id, year),
                TbAuxLedger.account_code == account_code,
            ]
        else:
            conditions = [
                TbAuxLedger.project_id == project_id,
                TbAuxLedger.account_code == account_code,
                TbAuxLedger.is_deleted == sa.false(),
            ]

        stmt = (
            sa.select(TbAuxLedger)
            .where(*conditions)
            .order_by(TbAuxLedger.aux_code, TbAuxLedger.voucher_date)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return {"account_code": account_code, "base_date": base_date, "details": [], "summary": []}

        # 按辅助维度分组
        groups: dict[str, list] = {}
        for r in rows:
            key = r.aux_code or r.aux_name or "未分类"
            groups.setdefault(key, []).append(r)

        details = []
        for aux_key, entries in groups.items():
            aux_name = entries[0].aux_name or aux_key
            aging_result = self._fifo_aging(entries, base, aging_brackets)
            details.append({
                "aux_code": aux_key,
                "aux_name": aux_name,
                "total_balance": aging_result["total"],
                "brackets": aging_result["brackets"],
            })

        # 汇总
        summary = self._summarize_brackets(details, aging_brackets)

        return {
            "account_code": account_code,
            "base_date": base_date,
            "total_aux_count": len(details),
            "details": details,
            "summary": summary,
        }

    def _fifo_aging(
        self,
        entries: list,
        base_date: date,
        brackets: list[dict],
    ) -> dict[str, Any]:
        """FIFO 先进先出核销"""
        # 分离借方（形成应收）和贷方（回款核销）
        debits = []  # (date, amount)
        credits = []  # (date, amount)

        for e in entries:
            d_amt = float(e.debit_amount or 0)
            c_amt = float(e.credit_amount or 0)
            v_date = e.voucher_date
            if not v_date:
                continue
            if d_amt > 0:
                debits.append({"date": v_date, "remaining": d_amt})
            if c_amt > 0:
                credits.append({"date": v_date, "amount": c_amt})

        # 按日期正序排列
        debits.sort(key=lambda x: x["date"])
        credits.sort(key=lambda x: x["date"])

        # 贷方按 FIFO 核销最早的借方
        for credit in credits:
            remaining_credit = credit["amount"]
            for debit in debits:
                if remaining_credit <= 0:
                    break
                if debit["remaining"] <= 0:
                    continue
                offset = min(debit["remaining"], remaining_credit)
                debit["remaining"] -= offset
                remaining_credit -= offset

        # 计算未核销借方的账龄
        bracket_amounts = {b["label"]: 0.0 for b in brackets}
        total = 0.0

        for debit in debits:
            if debit["remaining"] <= 0:
                continue
            days = (base_date - debit["date"]).days
            total += debit["remaining"]
            placed = False
            for b in brackets:
                min_d = b.get("min_days", 0)
                max_d = b.get("max_days")
                if max_d is None:
                    if days >= min_d:
                        bracket_amounts[b["label"]] += debit["remaining"]
                        placed = True
                        break
                elif min_d <= days <= max_d:
                    bracket_amounts[b["label"]] += debit["remaining"]
                    placed = True
                    break
            if not placed and brackets:
                bracket_amounts[brackets[-1]["label"]] += debit["remaining"]

        return {
            "total": round(total, 2),
            "brackets": [
                {"label": b["label"], "amount": round(bracket_amounts[b["label"]], 2)}
                for b in brackets
            ],
        }

    def _summarize_brackets(
        self, details: list[dict], brackets: list[dict]
    ) -> list[dict]:
        """汇总所有辅助维度的账龄"""
        summary = {b["label"]: 0.0 for b in brackets}
        for d in details:
            for b in d["brackets"]:
                summary[b["label"]] = summary.get(b["label"], 0) + b["amount"]
        return [{"label": k, "amount": round(v, 2)} for k, v in summary.items()]


class MonthlyDetailService:
    """月度明细填充"""

    async def generate_monthly_detail(
        self,
        db: AsyncSession,
        project_id: UUID,
        account_code: str,
        year: int,
    ) -> dict[str, Any]:
        """按月汇总 tb_ledger 数据"""
        stmt = (
            sa.select(
                TbLedger.accounting_period,
                sa.func.sum(TbLedger.debit_amount).label("total_debit"),
                sa.func.sum(TbLedger.credit_amount).label("total_credit"),
                sa.func.count().label("entry_count"),
            )
            .where(
                await get_active_filter(db, TbLedger.__table__, project_id, year),
                TbLedger.account_code == account_code,
            )
            .group_by(TbLedger.accounting_period)
            .order_by(TbLedger.accounting_period)
        )
        result = await db.execute(stmt)
        rows = result.fetchall()

        months = []
        cumulative_balance = Decimal(0)
        for r in rows:
            period = r.accounting_period or 0
            debit = float(r.total_debit or 0)
            credit = float(r.total_credit or 0)
            net = debit - credit
            cumulative_balance += Decimal(str(net))
            months.append({
                "period": period,
                "debit_total": round(debit, 2),
                "credit_total": round(credit, 2),
                "net_change": round(net, 2),
                "cumulative": round(float(cumulative_balance), 2),
                "entry_count": r.entry_count,
            })

        return {
            "account_code": account_code,
            "year": year,
            "months": months,
            "total_debit": round(sum(m["debit_total"] for m in months), 2),
            "total_credit": round(sum(m["credit_total"] for m in months), 2),
        }
