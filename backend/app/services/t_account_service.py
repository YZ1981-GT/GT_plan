"""T型账户服务

功能：创建T型账户、添加分录、计算净变动、与资产负债表勾稽、集成到现金流量表

Validates: Requirements 10.1-10.6
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.t_account_models import TAccount, TAccountEntry, T_ACCOUNT_TEMPLATES


class TAccountService:

    async def create_t_account(
        self, db: AsyncSession, project_id: UUID, data: dict[str, Any],
        created_by: UUID | None = None,
    ) -> dict:
        """创建T型账户"""
        account = TAccount(
            project_id=project_id,
            account_code=data["account_code"],
            account_name=data["account_name"],
            account_type=data.get("account_type", "asset"),
            opening_balance=Decimal(str(data.get("opening_balance", 0))),
            description=data.get("description"),
            created_by=created_by,
        )
        db.add(account)
        await db.flush()
        return self._account_to_dict(account, [], Decimal("0"), Decimal("0"))

    async def add_entry(
        self, db: AsyncSession, t_account_id: UUID, data: dict[str, Any],
    ) -> dict:
        """添加分录（debit/credit）"""
        entry_type = data.get("entry_type", "debit")
        if entry_type not in ("debit", "credit"):
            raise ValueError("entry_type 必须为 debit 或 credit")

        amount = Decimal(str(data.get("amount", 0)))
        if amount <= 0:
            raise ValueError("金额必须大于0")

        entry = TAccountEntry(
            t_account_id=t_account_id,
            entry_type=entry_type,
            amount=amount,
            description=data.get("description"),
            reference_id=data.get("reference_id"),
        )
        db.add(entry)
        await db.flush()
        return {
            "id": str(entry.id),
            "t_account_id": str(entry.t_account_id),
            "entry_type": entry.entry_type,
            "amount": float(entry.amount),
            "description": entry.description,
        }

    async def get_t_account(self, db: AsyncSession, t_account_id: UUID) -> dict | None:
        """获取T型账户详情（含所有分录和计算结果）"""
        result = await db.execute(
            sa.select(TAccount).where(TAccount.id == t_account_id, TAccount.is_deleted == sa.false())
        )
        account = result.scalar_one_or_none()
        if not account:
            return None

        entries_result = await db.execute(
            sa.select(TAccountEntry)
            .where(TAccountEntry.t_account_id == t_account_id, TAccountEntry.is_deleted == sa.false())
            .order_by(TAccountEntry.created_at)
        )
        entries = entries_result.scalars().all()

        debit_total = sum(e.amount for e in entries if e.entry_type == "debit")
        credit_total = sum(e.amount for e in entries if e.entry_type == "credit")

        return self._account_to_dict(account, entries, debit_total, credit_total)

    async def list_t_accounts(self, db: AsyncSession, project_id: UUID) -> list[dict]:
        """获取项目所有T型账户"""
        result = await db.execute(
            sa.select(TAccount)
            .where(TAccount.project_id == project_id, TAccount.is_deleted == sa.false())
            .order_by(TAccount.account_code)
        )
        accounts = result.scalars().all()
        items = []
        for acc in accounts:
            entries_result = await db.execute(
                sa.select(TAccountEntry)
                .where(TAccountEntry.t_account_id == acc.id, TAccountEntry.is_deleted == sa.false())
            )
            entries = entries_result.scalars().all()
            dt = sum(e.amount for e in entries if e.entry_type == "debit")
            ct = sum(e.amount for e in entries if e.entry_type == "credit")
            items.append(self._account_to_dict(acc, entries, dt, ct))
        return items

    async def calculate_net_change(self, db: AsyncSession, t_account_id: UUID) -> dict:
        """计算净变动"""
        detail = await self.get_t_account(db, t_account_id)
        if not detail:
            raise ValueError("T型账户不存在")

        return {
            "account_code": detail["account_code"],
            "account_name": detail["account_name"],
            "account_type": detail["account_type"],
            "opening_balance": detail["opening_balance"],
            "debit_total": detail["debit_total"],
            "credit_total": detail["credit_total"],
            "net_change": detail["net_change"],
            "closing_balance": detail["closing_balance"],
        }

    async def reconcile_with_balance_sheet(
        self, db: AsyncSession, t_account_id: UUID,
        bs_opening: Decimal, bs_closing: Decimal,
    ) -> dict:
        """与资产负债表勾稽"""
        detail = await self.get_t_account(db, t_account_id)
        if not detail:
            raise ValueError("T型账户不存在")

        bs_change = bs_closing - bs_opening
        t_change = Decimal(str(detail["net_change"]))
        diff = abs(bs_change - t_change)
        is_reconciled = diff < Decimal("0.01")

        return {
            "account_code": detail["account_code"],
            "bs_opening": float(bs_opening),
            "bs_closing": float(bs_closing),
            "bs_change": float(bs_change),
            "t_account_net_change": detail["net_change"],
            "difference": float(diff),
            "is_reconciled": is_reconciled,
            "message": "勾稽一致" if is_reconciled else f"差异 {float(diff):.2f}，请检查",
        }

    async def integrate_to_cfs(self, db: AsyncSession, t_account_id: UUID) -> dict:
        """集成到现金流量表（返回可用于CFS工作底稿的调整数据）"""
        detail = await self.get_t_account(db, t_account_id)
        if not detail:
            raise ValueError("T型账户不存在")

        # 按分录描述分类，生成CFS调整项
        cfs_items = []
        for entry in detail["entries"]:
            cfs_items.append({
                "description": entry["description"] or f"{detail['account_name']}调整",
                "entry_type": entry["entry_type"],
                "amount": entry["amount"],
            })

        return {
            "account_code": detail["account_code"],
            "account_name": detail["account_name"],
            "net_change": detail["net_change"],
            "cfs_adjustment_items": cfs_items,
            "message": f"已生成 {len(cfs_items)} 条CFS调整项",
        }

    def get_templates(self) -> list[dict]:
        """获取T型账户模版"""
        return T_ACCOUNT_TEMPLATES

    def _account_to_dict(
        self, account: TAccount, entries: list, debit_total: Decimal, credit_total: Decimal,
    ) -> dict:
        opening = account.opening_balance or Decimal("0")
        # 资产类：期末 = 期初 + 借方 - 贷方
        # 负债/权益类：期末 = 期初 + 贷方 - 借方
        if account.account_type in ("asset", "expense"):
            net_change = debit_total - credit_total
        else:
            net_change = credit_total - debit_total
        closing = opening + net_change

        return {
            "id": str(account.id),
            "project_id": str(account.project_id),
            "account_code": account.account_code,
            "account_name": account.account_name,
            "account_type": account.account_type,
            "opening_balance": float(opening),
            "debit_total": float(debit_total),
            "credit_total": float(credit_total),
            "net_change": float(net_change),
            "closing_balance": float(closing),
            "description": account.description,
            "entries": [
                {
                    "id": str(e.id),
                    "entry_type": e.entry_type,
                    "amount": float(e.amount),
                    "description": e.description,
                }
                for e in entries
            ],
        }
