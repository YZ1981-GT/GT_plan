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
        """穿透到序时账：按科目+日期范围+金额范围+凭证号+摘要关键词筛选"""
        tbl = TbLedger.__table__

        base_q = (
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
                tbl.c.account_code == account_code,
                tbl.c.is_deleted == sa.false(),
            )
        )

        # 筛选条件
        if filters.date_from is not None:
            base_q = base_q.where(tbl.c.voucher_date >= filters.date_from)
        if filters.date_to is not None:
            base_q = base_q.where(tbl.c.voucher_date <= filters.date_to)
        if filters.amount_min is not None:
            base_q = base_q.where(
                sa.or_(
                    tbl.c.debit_amount >= filters.amount_min,
                    tbl.c.credit_amount >= filters.amount_min,
                )
            )
        if filters.amount_max is not None:
            base_q = base_q.where(
                sa.or_(
                    sa.and_(tbl.c.debit_amount <= filters.amount_max, tbl.c.debit_amount > 0),
                    sa.and_(tbl.c.credit_amount <= filters.amount_max, tbl.c.credit_amount > 0),
                )
            )
        if filters.voucher_no:
            base_q = base_q.where(tbl.c.voucher_no == filters.voucher_no)
        if filters.summary_keyword:
            base_q = base_q.where(tbl.c.summary.ilike(f"%{filters.summary_keyword}%"))
        if filters.counterpart_account:
            base_q = base_q.where(tbl.c.counterpart_account == filters.counterpart_account)

        # 总数
        count_q = sa.select(sa.func.count()).select_from(base_q.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        # 分页 + 排序（按凭证日期+凭证号）
        offset = (filters.page - 1) * filters.page_size
        data_q = (
            base_q
            .order_by(tbl.c.voucher_date, tbl.c.voucher_no, tbl.c.id)
            .offset(offset)
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
