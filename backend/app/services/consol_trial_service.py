"""合并试算表服务"""

from decimal import Decimal
from uuid import UUID
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.consolidation_models import (
    ConsolTrial,
    EliminationEntry,
    ReviewStatusEnum,
)
from app.models.consolidation_schemas import ConsolTrialRow, ConsolTrialResponse


def get_trial_balance(db: Session, project_id: UUID, year: int) -> list[ConsolTrial]:
    return (
        db.query(ConsolTrial)
        .filter(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.is_deleted.is_(False),
        )
        .order_by(ConsolTrial.standard_account_code)
        .all()
    )


def get_trial_row(db: Session, trial_id: UUID, project_id: UUID) -> ConsolTrial | None:
    return (
        db.query(ConsolTrial)
        .filter(ConsolTrial.id == trial_id, ConsolTrial.project_id == project_id)
        .first()
    )


def upsert_trial_row(
    db: Session,
    project_id: UUID,
    year: int,
    standard_account_code: str,
    account_name: str | None = None,
    account_category: str | None = None,
) -> ConsolTrial:
    existing = (
        db.query(ConsolTrial)
        .filter(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.standard_account_code == standard_account_code,
            ConsolTrial.is_deleted.is_(False),
        )
        .first()
    )
    if existing:
        if account_name:
            existing.account_name = account_name
        if account_category:
            existing.account_category = account_category
        db.commit()
        db.refresh(existing)
        return existing

    trial = ConsolTrial(
        project_id=project_id,
        year=year,
        standard_account_code=standard_account_code,
        account_name=account_name,
        account_category=account_category,
    )
    db.add(trial)
    db.commit()
    db.refresh(trial)
    return trial


def recalculate_trial(db: Session, project_id: UUID, year: int) -> list[ConsolTrial]:
    """重新计算合并试算表"""
    trials = get_trial_balance(db, project_id, year)

    # 获取所有已审批的抵消分录
    elim_entries = (
        db.query(EliminationEntry)
        .filter(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.review_status == ReviewStatusEnum.APPROVED,
            EliminationEntry.is_deleted.is_(False),
        )
        .all()
    )

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
        trial.consol_adjustment = Decimal("0")  # 调整数归零，重新计算
        trial.consol_elimination = (elim_debits.get(code, Decimal("0")) - elim_credits.get(code, Decimal("0")))
        trial.consol_amount = trial.individual_sum + trial.consol_adjustment + trial.consol_elimination

    db.commit()
    for trial in trials:
        db.refresh(trial)
    return trials


def check_trial_consistency(db: Session, project_id: UUID, year: int) -> dict[str, Any]:
    """一致性校验：借贷平衡检查"""
    trials = get_trial_balance(db, project_id, year)

    total_debit = sum(t.consol_amount for t in trials if t.consol_amount >= 0)
    total_credit = sum(abs(t.consol_amount) for t in trials if t.consol_amount < 0)

    return {
        "is_balanced": abs(total_debit - total_credit) < Decimal("0.01"),
        "total_debit": total_debit,
        "total_credit": total_credit,
        "difference": total_debit - total_credit,
        "row_count": len(trials),
    }


def delete_trial(db: Session, trial_id: UUID, project_id: UUID) -> bool:
    trial = get_trial_row(db, trial_id, project_id)
    if not trial:
        return False
    trial.is_deleted = True
    db.commit()
    return True
