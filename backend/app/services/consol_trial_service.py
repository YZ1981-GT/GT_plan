"""合并试算表服务 — 异步 ORM"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolTrial

if TYPE_CHECKING:
    from app.services.consol_calc_basis import CalcBasis


async def get_trial_balance(db: AsyncSession, project_id: UUID, year: int) -> list[ConsolTrial]:
    result = await db.execute(
        sa.select(ConsolTrial).where(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.is_deleted.is_(False),
        ).order_by(ConsolTrial.standard_account_code)
    )
    return list(result.scalars().all())


async def get_trial_row(db: AsyncSession, trial_id: UUID, project_id: UUID) -> ConsolTrial | None:
    result = await db.execute(
        sa.select(ConsolTrial).where(
            ConsolTrial.id == trial_id,
            ConsolTrial.project_id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_trial_row(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    standard_account_code: str,
    account_name: str | None = None,
    account_category: str | None = None,
) -> ConsolTrial:
    result = await db.execute(
        sa.select(ConsolTrial).where(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.standard_account_code == standard_account_code,
            ConsolTrial.is_deleted.is_(False),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if account_name:
            existing.account_name = account_name
        if account_category:
            existing.account_category = account_category
        await db.flush()
        return existing

    trial = ConsolTrial(
        project_id=project_id,
        year=year,
        standard_account_code=standard_account_code,
        account_name=account_name,
        account_category=account_category,
    )
    db.add(trial)
    await db.flush()
    return trial


async def sync_trial_rows(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    basis: "CalcBasis",
    fill: Callable[[ConsolTrial, str | None], None],
) -> list[ConsolTrial]:
    """按本树科目集合同步合并试算行（需求 5.6）。

    - 集合内的科目：没有行就建（名称、类别取口径 —— 试算表优先，只在分录里出现的取分录行名称），
      再 ``fill(row, 科目)``；
    - 已有行但科目不在集合内（数据叶子与分录都不再有该科目）：``fill(row, None)`` 由调用方清零；
    - 同科目重复的有效行（历史脏数据）只保留一行，其余软删，防止报表取数重复计。
    只 flush 不 commit。
    """
    existing = (await db.execute(
        sa.select(ConsolTrial).where(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.is_deleted.is_(False),
        )
    )).scalars().all()
    by_code: dict[str, ConsolTrial] = {}
    for row in sorted(existing, key=lambda r: str(r.id)):
        if row.standard_account_code in by_code:
            row.soft_delete()
        else:
            by_code[row.standard_account_code] = row

    for code in basis.accounts:
        row = by_code.get(code)
        name = basis.names.get(code)
        category = basis.categories.get(code)
        if row is None:
            zero = Decimal("0")
            # 金额列与陈旧标记显式给值：只靠库默认值时 flush 后属性过期，异步会话里再读会触发隐式 IO
            row = ConsolTrial(
                project_id=project_id, year=year, standard_account_code=code,
                account_name=name, account_category=category,
                individual_sum=zero, consol_adjustment=zero, consol_elimination=zero,
                consol_amount=zero, is_stale=False,
            )
            db.add(row)
            by_code[code] = row
        else:
            if name:
                row.account_name = name
            if row.account_category is None and category is not None:
                row.account_category = category
        fill(row, code)
    wanted = set(basis.accounts)
    for code, row in by_code.items():
        if code not in wanted:
            fill(row, None)
    await db.flush()
    return list(by_code.values())


async def recalculate_trial(db: AsyncSession, project_id: UUID, year: int) -> list[ConsolTrial]:
    """重新计算合并试算表（spec consol-tree-three-code-autobuild 任务 7.4）。

    ``consol_amount = individual_sum + consol_adjustment + consol_elimination``：
    - 个别数汇总 = 企业树全部数据叶子的审定数（含母公司本体、各级本部与分公司）；
    - 调整 / 抵销 = 已归属分录明细行按科目自然方向归一（``sign(a)·(借−贷)``），
      「其他调整」进调整列，其余进抵销列；孤儿分录不计入；
    - 取数、归属、符号与差额表引擎同一函数（``consol_calc_basis``），根节点合并数逐科目相等（P8）。

    口径变更（有意）：删除按 ``projects.consolidation_type == "branch"`` 整体跳过抵销的分支 ——
    合并方式由下级关系推导（ADR-CTREE-004），母分差额分录与合并差额分录各自计入（需求 4.2 / 4.3）。
    只 flush 不 commit。
    """
    from app.services.consol_calc_basis import load_calc_basis, trial_amounts

    basis = await load_calc_basis(db, project_id, year)
    if basis is None:
        raise ValueError(f"企业树构建失败：找不到合并母项目 {project_id}")
    amounts = trial_amounts(basis)
    computed_at = datetime.now(timezone.utc).isoformat()
    zero = Decimal("0")

    def fill(trial: ConsolTrial, account: str | None) -> None:
        a = amounts.get(account) if account is not None else None
        trial.individual_sum = a.individual_sum if a is not None else zero
        trial.consol_adjustment = a.consol_adjustment if a is not None else zero
        trial.consol_elimination = a.consol_elimination if a is not None else zero
        trial.consol_amount = a.consol_amount if a is not None else zero
        trial.consolidation_breakdown = {
            "by_company": a.by_company if a is not None else [],
            "individual_sum": str(trial.individual_sum),
            "computed_at": computed_at,
        }
        trial.is_stale = False  # 重算后清除陈旧标记（P1）

    await sync_trial_rows(db, project_id, year, basis, fill)
    return await get_trial_balance(db, project_id, year)


async def check_trial_consistency(db: AsyncSession, project_id: UUID, year: int) -> dict[str, Any]:
    """一致性校验：借贷平衡检查"""
    trials = await get_trial_balance(db, project_id, year)

    total_debit = sum(t.consol_amount for t in trials if t.consol_amount >= 0)
    total_credit = sum(abs(t.consol_amount) for t in trials if t.consol_amount < 0)

    return {
        "is_balanced": abs(total_debit - total_credit) < Decimal("0.01"),
        "total_debit": total_debit,
        "total_credit": total_credit,
        "difference": total_debit - total_credit,
        "row_count": len(trials),
    }


async def delete_trial(db: AsyncSession, trial_id: UUID, project_id: UUID) -> bool:
    trial = await get_trial_row(db, trial_id, project_id)
    if not trial:
        return False
    trial.soft_delete()
    await db.commit()
    return True
