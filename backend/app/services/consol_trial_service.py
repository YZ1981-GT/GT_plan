"""合并试算表服务 — 异步 ORM"""

from decimal import Decimal
from uuid import UUID
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import (
    ConsolTrial,
    EliminationEntry,
    ReviewStatusEnum,
)
from app.models.consolidation_schemas import ConsolTrialRow, ConsolTrialResponse


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
        await db.commit()
        await db.refresh(existing)
        return existing

    trial = ConsolTrial(
        project_id=project_id,
        year=year,
        standard_account_code=standard_account_code,
        account_name=account_name,
        account_category=account_category,
    )
    db.add(trial)
    await db.commit()
    await db.refresh(trial)
    return trial


async def recalculate_trial(db: AsyncSession, project_id: UUID, year: int) -> list[ConsolTrial]:
    """重新计算合并试算表"""
    trials = await get_trial_balance(db, project_id, year)

    # 获取所有已审批的抵消分录
    result = await db.execute(
        sa.select(EliminationEntry).where(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.review_status == ReviewStatusEnum.APPROVED,
            EliminationEntry.is_deleted.is_(False),
        )
    )
    elim_entries = list(result.scalars().all())

    # 按科目代码汇总抵消金额
    elim_debits: dict[str, Decimal] = {}
    elim_credits: dict[str, Decimal] = {}
    for entry in elim_entries:
        for line in (entry.lines or []):
            code = line.get("account_code", "")
            debit = Decimal(str(line.get("debit_amount") or 0))
            credit = Decimal(str(line.get("credit_amount") or 0))
            if code:
                elim_debits[code] = elim_debits.get(code, Decimal("0")) + debit
                elim_credits[code] = elim_credits.get(code, Decimal("0")) + credit

    # 更新试算表
    for trial in trials:
        code = trial.standard_account_code
        trial.consol_adjustment = Decimal("0")
        trial.consol_elimination = (elim_debits.get(code, Decimal("0")) - elim_credits.get(code, Decimal("0")))
        trial.consol_amount = trial.individual_sum + trial.consol_adjustment + trial.consol_elimination

    await db.commit()
    for trial in trials:
        await db.refresh(trial)
    return trials


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
