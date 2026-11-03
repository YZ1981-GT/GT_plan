"""余额表 → 标准科目汇总的共用构件（spec post-push-residual-defect-closure R1）。

未审数重算（``TrialBalanceService.recalc_unadjusted``）与试算表端点的本期发生额（``include_movement``）
共用同一套口径，不各写一份：

* 只汇总**叶子节点**：客户科目表是多级树（1122 / 1122.01），父级余额 = 子级之和，父子全加会双计；
* 标准科目按**最长前缀映射**解析：叶子自身没映射就继承最近的已映射祖先（1651.02 → 1651 → 1641），
  无任何已映射祖先的叶子返回 NULL（不计入）。

🔴 损益类（5xxx / 6xxx）含年末结转分录时借贷两侧**恒相等**（见 ``four_table/pl_occurrence``），
本期发生额的借 / 贷是原始事实，不能拿「贷 − 借」当本期净发生额；损益金额以试算表单边口径为准。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import AccountMapping, TbBalance


def leaf_condition(bal):
    """``bal`` 行是叶子：同项目、同年度、同数据集下没有以它为前缀的子科目。"""
    child = bal.alias("tb_child")
    return ~sa.exists(
        sa.select(sa.literal(1))
        .select_from(child)
        .where(
            child.c.project_id == bal.c.project_id,
            child.c.year == bal.c.year,
            child.c.is_deleted == sa.false(),
            child.c.account_code != bal.c.account_code,
            child.c.account_code.like(bal.c.account_code.concat(".%")),
            # 子级须与父级同数据集才算其子科目（active dataset 已由 balance_filter 锁定 bal）
            sa.or_(
                child.c.dataset_id == bal.c.dataset_id,
                sa.and_(child.c.dataset_id.is_(None), bal.c.dataset_id.is_(None)),
            ),
        )
    )


def resolved_standard_code(bal):
    """``bal`` 行的标准科目码：自身有映射用自身，否则取最近的已映射祖先（按原科目码长度取最长前缀）。"""
    mp_anc = AccountMapping.__table__.alias("mp_anc")
    return (
        sa.select(mp_anc.c.standard_account_code)
        .where(
            mp_anc.c.project_id == bal.c.project_id,
            mp_anc.c.is_deleted == sa.false(),
            sa.or_(
                bal.c.account_code == mp_anc.c.original_account_code,
                bal.c.account_code.like(mp_anc.c.original_account_code.concat(".%")),
            ),
        )
        .order_by(sa.func.length(mp_anc.c.original_account_code).desc())
        .limit(1)
        .correlate(bal)
        .scalar_subquery()
    )


def period_movement_query(bal, balance_filter, account_codes: list[str] | None = None):
    """按标准科目汇总叶子的本期借 / 贷方发生额：列 ``standard_account_code`` / ``total_debit`` / ``total_credit``。"""
    period_sub = (
        sa.select(
            resolved_standard_code(bal).label("std"),
            bal.c.debit_amount.label("dr"),
            bal.c.credit_amount.label("cr"),
        )
        .select_from(bal)
        .where(balance_filter)
        .where(leaf_condition(bal))
    ).subquery("period_sub")
    query = (
        sa.select(
            period_sub.c.std.label("standard_account_code"),
            sa.func.coalesce(sa.func.sum(period_sub.c.dr), 0).label("total_debit"),
            sa.func.coalesce(sa.func.sum(period_sub.c.cr), 0).label("total_credit"),
        )
        .where(period_sub.c.std.isnot(None))
        .group_by(period_sub.c.std)
    )
    if account_codes:
        query = query.where(period_sub.c.std.in_(account_codes))
    return query


async def aggregate_period_movement(
    db: AsyncSession, project_id: UUID, year: int, account_codes: list[str] | None = None,
) -> dict[str, tuple[Decimal, Decimal]]:
    """``{标准科目码: (本期借方发生额, 本期贷方发生额)}``（当前生效数据集，叶子 + 最长前缀映射）。"""
    from app.services.dataset_query import get_active_filter

    bal = TbBalance.__table__
    balance_filter = await get_active_filter(db, bal, project_id, year)
    rows = (await db.execute(period_movement_query(bal, balance_filter, account_codes))).fetchall()
    return {
        r.standard_account_code: (Decimal(str(r.total_debit)), Decimal(str(r.total_credit)))
        for r in rows
    }
