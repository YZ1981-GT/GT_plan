"""四表联动穿透查询服务"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    AccountSource,
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
)
from app.models.audit_platform_schemas import (
    AuxBalanceRow,
    AuxLedgerRow,
    BalanceFilter,
    BalanceRow,
    LedgerFilter,
    LedgerRow,
    PageResult,
)


class DrilldownService:
    """四表联动穿透查询"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_balance_list(
        self, project_id: UUID, year: int, filters: BalanceFilter
    ) -> PageResult:
        """科目余额表分页+筛选，支持科目类别、层级、关键词"""
        # 基础查询：tb_balance LEFT JOIN account_chart 获取 category/level
        bal = TbBalance.__table__
        ac = AccountChart.__table__

        # 子查询：检查科目是否有辅助核算数据
        has_aux_subq = (
            sa.select(sa.literal(True))
            .select_from(TbAuxBalance.__table__)
            .where(
                TbAuxBalance.project_id == project_id,
                TbAuxBalance.year == year,
                TbAuxBalance.account_code == bal.c.account_code,
                TbAuxBalance.is_deleted == sa.false(),
            )
            .correlate(bal)
            .exists()
        )

        base_q = (
            sa.select(
                bal.c.account_code,
                bal.c.account_name,
                bal.c.opening_balance,
                bal.c.debit_amount,
                bal.c.credit_amount,
                bal.c.closing_balance,
                has_aux_subq.label("has_aux"),
            )
            .select_from(
                bal.outerjoin(
                    ac,
                    sa.and_(
                        ac.c.project_id == bal.c.project_id,
                        ac.c.account_code == bal.c.account_code,
                        ac.c.source == AccountSource.client.value,
                        ac.c.is_deleted == sa.false(),
                    ),
                )
            )
            .where(
                bal.c.project_id == project_id,
                bal.c.year == year,
                bal.c.is_deleted == sa.false(),
            )
        )

        # 应用筛选条件
        if filters.category is not None:
            base_q = base_q.where(ac.c.category == filters.category.value)
        if filters.level is not None:
            base_q = base_q.where(ac.c.level == filters.level)
        if filters.keyword:
            kw = f"%{filters.keyword}%"
            base_q = base_q.where(
                sa.or_(
                    bal.c.account_code.ilike(kw),
                    bal.c.account_name.ilike(kw),
                )
            )

        # 计算总数
        count_q = sa.select(sa.func.count()).select_from(base_q.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        # 分页 + 排序
        offset = (filters.page - 1) * filters.page_size
        data_q = base_q.order_by(bal.c.account_code).offset(offset).limit(filters.page_size)
        result = await self.db.execute(data_q)
        rows = [
            BalanceRow(
                account_code=r.account_code,
                account_name=r.account_name,
                opening_balance=r.opening_balance,
                debit_amount=r.debit_amount,
                credit_amount=r.credit_amount,
                closing_balance=r.closing_balance,
                has_aux=r.has_aux or False,
            )
            for r in result.fetchall()
        ]

        return PageResult(
            items=rows,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    async def drill_to_ledger(
        self, project_id: UUID, year: int, account_code: str, filters: LedgerFilter
    ) -> PageResult:
        """穿透到序时账：按科目+日期范围+金额范围+凭证号+摘要关键词筛选。

        包含累计余额（running_balance）：期初余额 + 累计借方 - 累计贷方。
        使用 SQL 窗口函数在数据库层面计算，支持百万行数据。
        """
        tbl = TbLedger.__table__
        bal = TbBalance.__table__

        # 获取该科目的期初余额（用于计算 running balance）
        opening_q = (
            sa.select(
                sa.func.coalesce(sa.func.sum(bal.c.opening_balance), 0).label("opening")
            )
            .where(
                bal.c.project_id == project_id,
                bal.c.year == year,
                bal.c.account_code == account_code,
                bal.c.is_deleted == sa.false(),
            )
        )
        opening_result = await self.db.execute(opening_q)
        opening_balance = opening_result.scalar() or Decimal("0")

        # 基础筛选条件
        where_clauses = [
            tbl.c.project_id == project_id,
            tbl.c.year == year,
            tbl.c.account_code == account_code,
            tbl.c.is_deleted == sa.false(),
        ]
        if filters.date_from is not None:
            where_clauses.append(tbl.c.voucher_date >= filters.date_from)
        if filters.date_to is not None:
            where_clauses.append(tbl.c.voucher_date <= filters.date_to)
        if filters.amount_min is not None:
            where_clauses.append(sa.or_(
                tbl.c.debit_amount >= filters.amount_min,
                tbl.c.credit_amount >= filters.amount_min,
            ))
        if filters.amount_max is not None:
            where_clauses.append(sa.or_(
                sa.and_(tbl.c.debit_amount <= filters.amount_max, tbl.c.debit_amount > 0),
                sa.and_(tbl.c.credit_amount <= filters.amount_max, tbl.c.credit_amount > 0),
            ))
        if filters.voucher_no:
            where_clauses.append(tbl.c.voucher_no == filters.voucher_no)
        if filters.summary_keyword:
            where_clauses.append(tbl.c.summary.ilike(f"%{filters.summary_keyword}%"))
        if filters.counterpart_account:
            where_clauses.append(tbl.c.counterpart_account == filters.counterpart_account)

        base_q = sa.select(
            tbl.c.id,
            tbl.c.voucher_date,
            tbl.c.voucher_no,
            tbl.c.account_code,
            tbl.c.account_name,
            tbl.c.debit_amount,
            tbl.c.credit_amount,
            tbl.c.counterpart_account,
            tbl.c.summary,
            tbl.c.preparer,
        ).where(*where_clauses)

        # 总数
        count_q = sa.select(sa.func.count()).select_from(base_q.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        # 使用窗口函数计算累计余额（在数据库层面完成，支持大数据量）
        order_cols = (tbl.c.voucher_date, tbl.c.voucher_no, tbl.c.id)
        running_balance_expr = (
            sa.literal(opening_balance)
            + sa.func.coalesce(
                sa.func.sum(sa.func.coalesce(tbl.c.debit_amount, 0)).over(order_by=order_cols),
                0,
            )
            - sa.func.coalesce(
                sa.func.sum(sa.func.coalesce(tbl.c.credit_amount, 0)).over(order_by=order_cols),
                0,
            )
        ).label("running_balance")

        data_q = (
            sa.select(
                tbl.c.id,
                tbl.c.voucher_date,
                tbl.c.voucher_no,
                tbl.c.account_code,
                tbl.c.account_name,
                tbl.c.debit_amount,
                tbl.c.credit_amount,
                tbl.c.counterpart_account,
                tbl.c.summary,
                tbl.c.preparer,
                running_balance_expr,
            )
            .where(*where_clauses)
            .order_by(*order_cols)
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        result = await self.db.execute(data_q)
        rows = [
            LedgerRow(
                id=r.id,
                voucher_date=r.voucher_date,
                voucher_no=r.voucher_no,
                account_code=r.account_code,
                account_name=r.account_name,
                debit_amount=r.debit_amount,
                credit_amount=r.credit_amount,
                counterpart_account=r.counterpart_account,
                summary=r.summary,
                preparer=r.preparer,
                running_balance=r.running_balance,
            )
            for r in result.fetchall()
        ]

        return PageResult(
            items=rows,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    async def drill_to_aux_balance(
        self, project_id: UUID, year: int, account_code: str
    ) -> list[AuxBalanceRow]:
        """穿透到辅助余额表：按辅助维度分组"""
        tbl = TbAuxBalance.__table__

        q = (
            sa.select(
                tbl.c.aux_type,
                tbl.c.aux_code,
                tbl.c.aux_name,
                tbl.c.opening_balance,
                tbl.c.debit_amount,
                tbl.c.credit_amount,
                tbl.c.closing_balance,
            )
            .where(
                tbl.c.project_id == project_id,
                tbl.c.year == year,
                tbl.c.account_code == account_code,
                tbl.c.is_deleted == sa.false(),
            )
            .order_by(tbl.c.aux_type, tbl.c.aux_code)
        )
        result = await self.db.execute(q)
        return [
            AuxBalanceRow(
                aux_type=r.aux_type,
                aux_code=r.aux_code,
                aux_name=r.aux_name,
                opening_balance=r.opening_balance,
                debit_amount=r.debit_amount,
                credit_amount=r.credit_amount,
                closing_balance=r.closing_balance,
            )
            for r in result.fetchall()
        ]

    async def drill_to_aux_ledger(
        self,
        project_id: UUID,
        year: int,
        account_code: str,
        aux_type: str | None = None,
        aux_code: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PageResult:
        """穿透到辅助明细账"""
        tbl = TbAuxLedger.__table__

        base_q = (
            sa.select(
                tbl.c.id,
                tbl.c.voucher_date,
                tbl.c.voucher_no,
                tbl.c.account_code,
                tbl.c.aux_type,
                tbl.c.aux_code,
                tbl.c.aux_name,
                tbl.c.debit_amount,
                tbl.c.credit_amount,
                tbl.c.summary,
                tbl.c.preparer,
            )
            .where(
                tbl.c.project_id == project_id,
                tbl.c.year == year,
                tbl.c.account_code == account_code,
                tbl.c.is_deleted == sa.false(),
            )
        )

        if aux_type:
            base_q = base_q.where(tbl.c.aux_type == aux_type)
        if aux_code:
            base_q = base_q.where(tbl.c.aux_code == aux_code)

        # 总数
        count_q = sa.select(sa.func.count()).select_from(base_q.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        # 分页
        offset = (page - 1) * page_size
        data_q = (
            base_q
            .order_by(tbl.c.voucher_date, tbl.c.voucher_no, tbl.c.id)
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(data_q)
        rows = [
            AuxLedgerRow(
                id=r.id,
                voucher_date=r.voucher_date,
                voucher_no=r.voucher_no,
                account_code=r.account_code,
                aux_type=r.aux_type,
                aux_code=r.aux_code,
                aux_name=r.aux_name,
                debit_amount=r.debit_amount,
                credit_amount=r.credit_amount,
                summary=r.summary,
                preparer=r.preparer,
            )
            for r in result.fetchall()
        ]

        return PageResult(
            items=rows,
            total=total,
            page=page,
            page_size=page_size,
        )

    # ------------------------------------------------------------------
    # CTE 优化四表联查（Phase 8 Task 2.3）
    # ------------------------------------------------------------------

    async def get_balance_with_ledger_summary(
        self, project_id: UUID, year: int,
        account_codes: list[str] | None = None,
    ) -> list[dict]:
        """CTE 优化四表联查 — 一次查询获取余额+序时账汇总+辅助维度计数。

        使用 CTE 替代多次独立查询，减少 DB 往返（N+1 → 1）。
        """
        bal = TbBalance.__table__
        led = TbLedger.__table__
        aux = TbAuxBalance.__table__

        # CTE 1: 序时账按科目汇总
        ledger_cte = (
            sa.select(
                led.c.account_code,
                sa.func.coalesce(sa.func.sum(led.c.debit_amount), 0).label("ledger_debit"),
                sa.func.coalesce(sa.func.sum(led.c.credit_amount), 0).label("ledger_credit"),
                sa.func.count().label("voucher_count"),
            )
            .where(
                led.c.project_id == project_id,
                led.c.year == year,
                led.c.is_deleted == sa.false(),
            )
            .group_by(led.c.account_code)
        ).cte("ledger_summary")

        # CTE 2: 辅助维度计数
        aux_cte = (
            sa.select(
                aux.c.account_code,
                sa.func.count(sa.distinct(aux.c.aux_type)).label("aux_type_count"),
                sa.func.count().label("aux_row_count"),
            )
            .where(
                aux.c.project_id == project_id,
                aux.c.year == year,
                aux.c.is_deleted == sa.false(),
            )
            .group_by(aux.c.account_code)
        ).cte("aux_summary")

        # 主查询: 余额表 LEFT JOIN 两个 CTE
        stmt = (
            sa.select(
                bal.c.account_code,
                bal.c.account_name,
                bal.c.level,
                bal.c.opening_balance,
                bal.c.debit_amount,
                bal.c.credit_amount,
                bal.c.closing_balance,
                ledger_cte.c.ledger_debit,
                ledger_cte.c.ledger_credit,
                ledger_cte.c.voucher_count,
                aux_cte.c.aux_type_count,
                aux_cte.c.aux_row_count,
            )
            .select_from(
                bal
                .outerjoin(ledger_cte, bal.c.account_code == ledger_cte.c.account_code)
                .outerjoin(aux_cte, bal.c.account_code == aux_cte.c.account_code)
            )
            .where(
                bal.c.project_id == project_id,
                bal.c.year == year,
                bal.c.is_deleted == sa.false(),
            )
            .order_by(bal.c.account_code)
        )

        if account_codes:
            stmt = stmt.where(bal.c.account_code.in_(account_codes))

        result = await self.db.execute(stmt)
        return [
            {
                "account_code": r.account_code,
                "account_name": r.account_name,
                "level": r.level,
                "opening_balance": r.opening_balance,
                "debit_amount": r.debit_amount,
                "credit_amount": r.credit_amount,
                "closing_balance": r.closing_balance,
                "ledger_debit": r.ledger_debit,
                "ledger_credit": r.ledger_credit,
                "voucher_count": r.voucher_count or 0,
                "has_aux": (r.aux_row_count or 0) > 0,
                "aux_type_count": r.aux_type_count or 0,
            }
            for r in result.fetchall()
        ]

    async def batch_get_ledger_summaries(
        self, project_id: UUID, year: int,
        account_codes: list[str],
    ) -> dict[str, dict]:
        """批量获取多个科目的序时账汇总（减少 N+1 查询）。

        返回 {account_code: {debit, credit, count}} 字典。
        """
        if not account_codes:
            return {}

        tbl = TbLedger.__table__
        stmt = (
            sa.select(
                tbl.c.account_code,
                sa.func.coalesce(sa.func.sum(tbl.c.debit_amount), 0).label("total_debit"),
                sa.func.coalesce(sa.func.sum(tbl.c.credit_amount), 0).label("total_credit"),
                sa.func.count().label("entry_count"),
            )
            .where(
                tbl.c.project_id == project_id,
                tbl.c.year == year,
                tbl.c.account_code.in_(account_codes),
                tbl.c.is_deleted == sa.false(),
            )
            .group_by(tbl.c.account_code)
        )
        result = await self.db.execute(stmt)
        return {
            r.account_code: {
                "total_debit": r.total_debit,
                "total_credit": r.total_credit,
                "entry_count": r.entry_count,
            }
            for r in result.fetchall()
        }

    # ------------------------------------------------------------------
    # 凭证分录查询（按凭证号穿透，显示完整借贷分录）
    # ------------------------------------------------------------------

    async def get_voucher_detail(
        self, project_id: UUID, year: int, voucher_no: str
    ) -> dict:
        """按凭证号查询完整分录，包含借贷合计和平衡状态。

        返回该凭证的所有分录行 + 借方合计 + 贷方合计 + 是否平衡。
        """
        tbl = TbLedger.__table__

        stmt = (
            sa.select(
                tbl.c.id,
                tbl.c.voucher_date,
                tbl.c.voucher_no,
                tbl.c.account_code,
                tbl.c.account_name,
                tbl.c.debit_amount,
                tbl.c.credit_amount,
                tbl.c.counterpart_account,
                tbl.c.summary,
                tbl.c.preparer,
            )
            .where(
                tbl.c.project_id == project_id,
                tbl.c.year == year,
                tbl.c.voucher_no == voucher_no,
                tbl.c.is_deleted == sa.false(),
            )
            .order_by(tbl.c.account_code)
        )
        result = await self.db.execute(stmt)
        rows = result.fetchall()

        entries = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        voucher_date = None

        for r in rows:
            d = r.debit_amount or Decimal("0")
            c = r.credit_amount or Decimal("0")
            total_debit += d
            total_credit += c
            if voucher_date is None:
                voucher_date = r.voucher_date
            entries.append({
                "id": r.id,
                "account_code": r.account_code,
                "account_name": r.account_name,
                "debit_amount": d,
                "credit_amount": c,
                "summary": r.summary,
            })

        return {
            "voucher_no": voucher_no,
            "voucher_date": voucher_date,
            "preparer": rows[0].preparer if rows else None,
            "entries": entries,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "is_balanced": total_debit == total_credit,
            "difference": total_debit - total_credit,
        }

    # ------------------------------------------------------------------
    # 凭证列表（按日期范围分页，支持大数据量）
    # ------------------------------------------------------------------

    async def list_vouchers(
        self, project_id: UUID, year: int,
        date_from=None, date_to=None,
        keyword: str | None = None,
        page: int = 1, page_size: int = 50,
    ) -> PageResult:
        """凭证列表：按凭证号分组，显示日期、摘要、借贷合计。

        使用 GROUP BY 在数据库层面聚合，支持百万行序时账。
        """
        tbl = TbLedger.__table__

        # 按凭证号分组聚合
        group_q = (
            sa.select(
                tbl.c.voucher_no,
                sa.func.min(tbl.c.voucher_date).label("voucher_date"),
                sa.func.min(tbl.c.preparer).label("preparer"),
                sa.func.string_agg(
                    sa.func.distinct(tbl.c.summary),
                    sa.literal_column("'; '"),
                ).label("summaries"),
                sa.func.coalesce(sa.func.sum(tbl.c.debit_amount), 0).label("total_debit"),
                sa.func.coalesce(sa.func.sum(tbl.c.credit_amount), 0).label("total_credit"),
                sa.func.count().label("entry_count"),
            )
            .where(
                tbl.c.project_id == project_id,
                tbl.c.year == year,
                tbl.c.is_deleted == sa.false(),
            )
            .group_by(tbl.c.voucher_no)
        )

        if date_from:
            group_q = group_q.having(sa.func.min(tbl.c.voucher_date) >= date_from)
        if date_to:
            group_q = group_q.having(sa.func.min(tbl.c.voucher_date) <= date_to)
        if keyword:
            # 筛选包含关键词的凭证（摘要或凭证号）
            group_q = group_q.having(
                sa.or_(
                    tbl.c.voucher_no.ilike(f"%{keyword}%"),
                    sa.func.string_agg(tbl.c.summary, sa.literal_column("' '")).ilike(f"%{keyword}%"),
                )
            )

        # 总数
        count_sub = group_q.subquery()
        total = (await self.db.execute(
            sa.select(sa.func.count()).select_from(count_sub)
        )).scalar() or 0

        # 分页
        data_q = (
            group_q
            .order_by(sa.text("voucher_date"), sa.text("voucher_no"))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(data_q)
        items = [
            {
                "voucher_no": r.voucher_no,
                "voucher_date": r.voucher_date,
                "preparer": r.preparer,
                "summaries": r.summaries,
                "total_debit": r.total_debit,
                "total_credit": r.total_credit,
                "entry_count": r.entry_count,
                "is_balanced": r.total_debit == r.total_credit,
            }
            for r in result.fetchall()
        ]

        return PageResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    # ------------------------------------------------------------------
    # 余额表↔序时账联动校验
    # ------------------------------------------------------------------

    async def verify_balance_ledger_consistency(
        self, project_id: UUID, year: int
    ) -> list[dict]:
        """校验余额表与序时账的一致性。

        对每个科目检查：
        - 余额表的 debit_amount 是否等于序时账借方合计
        - 余额表的 credit_amount 是否等于序时账贷方合计
        - 余额表的 closing_balance 是否等于 opening_balance + debit - credit

        使用 SQL 聚合在数据库层面完成，支持大数据量。
        """
        bal = TbBalance.__table__
        led = TbLedger.__table__

        # 序时账按科目汇总
        ledger_agg = (
            sa.select(
                led.c.account_code,
                sa.func.coalesce(sa.func.sum(led.c.debit_amount), 0).label("ledger_debit"),
                sa.func.coalesce(sa.func.sum(led.c.credit_amount), 0).label("ledger_credit"),
                sa.func.count().label("voucher_count"),
            )
            .where(
                led.c.project_id == project_id,
                led.c.year == year,
                led.c.is_deleted == sa.false(),
            )
            .group_by(led.c.account_code)
        ).subquery("ledger_agg")

        # LEFT JOIN 余额表
        stmt = (
            sa.select(
                bal.c.account_code,
                bal.c.account_name,
                bal.c.opening_balance,
                bal.c.debit_amount.label("bal_debit"),
                bal.c.credit_amount.label("bal_credit"),
                bal.c.closing_balance,
                ledger_agg.c.ledger_debit,
                ledger_agg.c.ledger_credit,
                ledger_agg.c.voucher_count,
            )
            .select_from(
                bal.outerjoin(
                    ledger_agg,
                    bal.c.account_code == ledger_agg.c.account_code,
                )
            )
            .where(
                bal.c.project_id == project_id,
                bal.c.year == year,
                bal.c.is_deleted == sa.false(),
            )
            .order_by(bal.c.account_code)
        )

        result = await self.db.execute(stmt)
        issues = []

        for r in result.fetchall():
            opening = r.opening_balance or Decimal("0")
            bal_debit = r.bal_debit or Decimal("0")
            bal_credit = r.bal_credit or Decimal("0")
            closing = r.closing_balance or Decimal("0")
            led_debit = r.ledger_debit or Decimal("0")
            led_credit = r.ledger_credit or Decimal("0")

            # 检查1：余额表发生额 vs 序时账合计
            if bal_debit != led_debit:
                issues.append({
                    "account_code": r.account_code,
                    "account_name": r.account_name,
                    "type": "debit_mismatch",
                    "message": f"借方发生额不一致：余额表={bal_debit}，序时账合计={led_debit}",
                    "balance_value": str(bal_debit),
                    "ledger_value": str(led_debit),
                    "difference": str(bal_debit - led_debit),
                })

            if bal_credit != led_credit:
                issues.append({
                    "account_code": r.account_code,
                    "account_name": r.account_name,
                    "type": "credit_mismatch",
                    "message": f"贷方发生额不一致：余额表={bal_credit}，序时账合计={led_credit}",
                    "balance_value": str(bal_credit),
                    "ledger_value": str(led_credit),
                    "difference": str(bal_credit - led_credit),
                })

            # 检查2：期初+借方-贷方=期末
            expected_closing = opening + bal_debit - bal_credit
            if closing != expected_closing:
                issues.append({
                    "account_code": r.account_code,
                    "account_name": r.account_name,
                    "type": "closing_formula",
                    "message": f"期末余额公式不平：期初({opening})+借方({bal_debit})-贷方({bal_credit})={expected_closing}，实际={closing}",
                    "expected": str(expected_closing),
                    "actual": str(closing),
                    "difference": str(closing - expected_closing),
                })

        return issues
