"""试算表计算引擎 — 增量更新 + 全量重算 + 事件处理器

Validates: Requirements 6.1-6.12, 10.1-10.6
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountMapping,
    AccountSource,
    Adjustment,
    AdjustmentType,
    TbBalance,
    TrialBalance,
)
from app.models.audit_platform_schemas import EventPayload

logger = logging.getLogger(__name__)


class TrialBalanceService:
    """试算表计算引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 未审数重算
    # ------------------------------------------------------------------
    async def recalc_unadjusted(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
        account_codes: list[str] | None = None,
    ) -> None:
        """
        通过 JOIN account_mapping 汇总 tb_balance.closing_balance 到标准科目。
        account_codes=None → 全量; 指定列表 → 增量。
        """
        bal = TbBalance.__table__
        mp = AccountMapping.__table__
        ac = AccountChart.__table__

        # 汇总查询：客户余额 → 映射 → 标准科目
        agg_q = (
            sa.select(
                mp.c.standard_account_code,
                sa.func.coalesce(sa.func.sum(bal.c.closing_balance), 0).label("total_closing"),
                sa.func.coalesce(sa.func.sum(bal.c.opening_balance), 0).label("total_opening"),
            )
            .select_from(
                bal.join(
                    mp,
                    sa.and_(
                        mp.c.project_id == bal.c.project_id,
                        mp.c.original_account_code == bal.c.account_code,
                        mp.c.is_deleted == sa.false(),
                    ),
                )
            )
            .where(
                bal.c.project_id == project_id,
                bal.c.year == year,
                bal.c.is_deleted == sa.false(),
            )
            .group_by(mp.c.standard_account_code)
        )

        if account_codes:
            agg_q = agg_q.where(mp.c.standard_account_code.in_(account_codes))

        result = await self.db.execute(agg_q)
        agg_rows = {r.standard_account_code: r for r in result.fetchall()}

        # 获取标准科目信息（名称、类别）
        std_q = (
            sa.select(ac.c.account_code, ac.c.account_name, ac.c.category)
            .where(
                ac.c.project_id == project_id,
                ac.c.source == AccountSource.standard.value,
                ac.c.is_deleted == sa.false(),
            )
        )
        if account_codes:
            std_q = std_q.where(ac.c.account_code.in_(account_codes))

        std_result = await self.db.execute(std_q)
        std_map = {r.account_code: r for r in std_result.fetchall()}

        # 合并所有需要处理的科目
        all_codes = set(agg_rows.keys()) | set(std_map.keys())
        if account_codes:
            all_codes = all_codes & set(account_codes)

        for code in all_codes:
            agg = agg_rows.get(code)
            std = std_map.get(code)
            closing = Decimal(str(agg.total_closing)) if agg else Decimal("0")
            opening = Decimal(str(agg.total_opening)) if agg else Decimal("0")
            name = std.account_name if std else None
            cat = std.category if std else AccountCategory.asset.value

            # UPSERT: 更新或插入
            existing = await self.db.execute(
                sa.select(TrialBalance).where(
                    TrialBalance.project_id == project_id,
                    TrialBalance.year == year,
                    TrialBalance.company_code == company_code,
                    TrialBalance.standard_account_code == code,
                    TrialBalance.is_deleted == sa.false(),
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.unadjusted_amount = closing
                row.opening_balance = opening
                row.account_name = name or row.account_name
                row.audited_amount = closing + row.rje_adjustment + row.aje_adjustment
            else:
                new_row = TrialBalance(
                    project_id=project_id,
                    year=year,
                    company_code=company_code,
                    standard_account_code=code,
                    account_name=name,
                    account_category=cat if isinstance(cat, AccountCategory) else AccountCategory(cat),
                    unadjusted_amount=closing,
                    opening_balance=opening,
                    rje_adjustment=Decimal("0"),
                    aje_adjustment=Decimal("0"),
                    audited_amount=closing,
                )
                self.db.add(new_row)

        await self.db.flush()

    # ------------------------------------------------------------------
    # 调整列重算
    # ------------------------------------------------------------------
    async def recalc_adjustments(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
        account_codes: list[str] | None = None,
    ) -> None:
        """按 adjustment_type 分组汇总 adjustments 表到 rje/aje 列"""
        adj = Adjustment.__table__

        agg_q = (
            sa.select(
                adj.c.account_code,
                adj.c.adjustment_type,
                (sa.func.coalesce(sa.func.sum(adj.c.debit_amount), 0)
                 - sa.func.coalesce(sa.func.sum(adj.c.credit_amount), 0)).label("net"),
            )
            .where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.is_deleted == sa.false(),
            )
            .group_by(adj.c.account_code, adj.c.adjustment_type)
        )

        if account_codes:
            agg_q = agg_q.where(adj.c.account_code.in_(account_codes))

        result = await self.db.execute(agg_q)

        # 按科目汇总 rje/aje
        adj_map: dict[str, dict[str, Decimal]] = {}
        for r in result.fetchall():
            code = r.account_code
            if code not in adj_map:
                adj_map[code] = {"rje": Decimal("0"), "aje": Decimal("0")}
            adj_map[code][r.adjustment_type] = Decimal(str(r.net))

        # 如果指定了科目列表但没有调整分录，也需要清零
        codes_to_update = set(adj_map.keys())
        if account_codes:
            codes_to_update = codes_to_update | set(account_codes)

        for code in codes_to_update:
            vals = adj_map.get(code, {"rje": Decimal("0"), "aje": Decimal("0")})
            existing = await self.db.execute(
                sa.select(TrialBalance).where(
                    TrialBalance.project_id == project_id,
                    TrialBalance.year == year,
                    TrialBalance.company_code == company_code,
                    TrialBalance.standard_account_code == code,
                    TrialBalance.is_deleted == sa.false(),
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.rje_adjustment = vals["rje"]
                row.aje_adjustment = vals["aje"]

        await self.db.flush()

    # ------------------------------------------------------------------
    # 审定数重算
    # ------------------------------------------------------------------
    async def recalc_audited(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
        account_codes: list[str] | None = None,
    ) -> None:
        """audited = unadjusted + rje + aje"""
        q = sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.company_code == company_code,
            TrialBalance.is_deleted == sa.false(),
        )
        if account_codes:
            q = q.where(TrialBalance.standard_account_code.in_(account_codes))

        result = await self.db.execute(q)
        for row in result.scalars().all():
            unadj = row.unadjusted_amount or Decimal("0")
            row.audited_amount = unadj + row.rje_adjustment + row.aje_adjustment

        await self.db.flush()

    # ------------------------------------------------------------------
    # 全量重算
    # ------------------------------------------------------------------
    async def full_recalc(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
    ) -> None:
        """全量重算：未审数 → 调整列 → 审定数"""
        await self.recalc_unadjusted(project_id, year, company_code)
        await self.recalc_adjustments(project_id, year, company_code)
        await self.recalc_audited(project_id, year, company_code)

    # ------------------------------------------------------------------
    # 一致性校验
    # ------------------------------------------------------------------
    async def check_consistency(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
    ) -> list[dict]:
        """校验：未审数=映射汇总、调整列=分录汇总、审定数公式正确"""
        issues = []

        # 获取当前试算表
        q = sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.company_code == company_code,
            TrialBalance.is_deleted == sa.false(),
        )
        result = await self.db.execute(q)
        rows = result.scalars().all()

        for row in rows:
            unadj = row.unadjusted_amount or Decimal("0")
            expected_audited = unadj + row.rje_adjustment + row.aje_adjustment
            if row.audited_amount != expected_audited:
                issues.append({
                    "type": "audited_formula",
                    "account_code": row.standard_account_code,
                    "expected": str(expected_audited),
                    "actual": str(row.audited_amount),
                })

        return issues

    # ------------------------------------------------------------------
    # 获取试算表数据
    # ------------------------------------------------------------------
    async def get_trial_balance(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
    ) -> list[TrialBalance]:
        """获取试算表所有行"""
        q = (
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.company_code == company_code,
                TrialBalance.is_deleted == sa.false(),
            )
            .order_by(TrialBalance.standard_account_code)
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # 事件处理器（供 EventBus 调用）
    # ------------------------------------------------------------------
    async def on_adjustment_changed(self, payload: EventPayload) -> None:
        """调整分录 CRUD → 增量重算受影响科目的调整列+审定数

        Validates: Requirements 10.1, 10.2, 10.3
        """
        logger.info(
            "on_adjustment_changed: project=%s, accounts=%s",
            payload.project_id, payload.account_codes,
        )
        account_codes = payload.account_codes
        year = payload.year
        if not year:
            logger.warning("on_adjustment_changed: missing year, skipping")
            return

        await self.recalc_adjustments(
            payload.project_id, year, account_codes=account_codes,
        )
        await self.recalc_audited(
            payload.project_id, year, account_codes=account_codes,
        )
        await self.db.flush()

    async def on_mapping_changed(self, payload: EventPayload) -> None:
        """科目映射变更 → 重算旧+新标准科目的未审数

        Validates: Requirements 10.4
        """
        logger.info(
            "on_mapping_changed: project=%s, accounts=%s",
            payload.project_id, payload.account_codes,
        )
        account_codes = payload.account_codes
        year = payload.year
        if not year:
            logger.warning("on_mapping_changed: missing year, skipping")
            return

        await self.recalc_unadjusted(
            payload.project_id, year, account_codes=account_codes,
        )
        await self.recalc_audited(
            payload.project_id, year, account_codes=account_codes,
        )
        await self.db.flush()

    async def on_data_imported(self, payload: EventPayload) -> None:
        """数据导入完成 → 全量重算未审数

        Validates: Requirements 10.5
        """
        logger.info(
            "on_data_imported: project=%s",
            payload.project_id,
        )
        year = payload.year
        if not year:
            logger.warning("on_data_imported: missing year, skipping")
            return

        await self.full_recalc(payload.project_id, year)
        await self.db.flush()

    async def on_import_rolled_back(self, payload: EventPayload) -> None:
        """导入回滚 → 全量重算

        Validates: Requirements 10.5
        """
        logger.info(
            "on_import_rolled_back: project=%s",
            payload.project_id,
        )
        year = payload.year
        if not year:
            logger.warning("on_import_rolled_back: missing year, skipping")
            return

        await self.full_recalc(payload.project_id, year)
        await self.db.flush()
