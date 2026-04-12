"""合并试算表路由

提供合并试算表的查询、汇总、重算、一致性校验等 API 端点。

端点：
- GET    /                            获取合并试算表列表
- POST   /                            创建试算表行
- GET    /{trial_id}                  获取单个试算表行
- PUT    /{trial_id}                  更新试算表行
- DELETE /{trial_id}                  删除试算表行
- POST   /aggregate                   触发汇总（各公司审定数）
- POST   /recalc-elimination          重算抵消列
- POST   /recalc-consol-amount       重算合并数列
- POST   /full-recalc                 完整全量重算（包含汇总+抵消+合并数）
- GET    /consistency-check           一致性校验
- GET    /summary                     试算表汇总（借贷合计）

Validates: Requirements 3.1-3.4
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import get_db as db, get_current_user
from app.models.consolidation_schemas import (
    ConsolTrialResponse,
    ConsolTrialUpdate,
    ConsistencyCheckResult,
)
from app.services.consol_trial_service import (
    aggregate_individual,
    check_consistency,
    delete_trial,
    full_recalc,
    get_trial_balance,
    get_trial_row,
    recalc_consol_amount,
    recalc_elimination,
    upsert_trial_row,
)

router = APIRouter(prefix="/consolidation/trial", tags=["合并试算表"])


# ────────────────────────────────────────────────────────────────
# 7.5 试算表汇总响应
# ────────────────────────────────────────────────────────────────


class ConsolTrialSummary(BaseModel):
    """合并试算表汇总"""
    row_count: int = 0
    total_individual_sum: Decimal = Field(default=Decimal("0"))
    total_consol_adjustment: Decimal = Field(default=Decimal("0"))
    total_consol_elimination: Decimal = Field(default=Decimal("0"))
    total_consol_amount: Decimal = Field(default=Decimal("0"))
    debit_total: Decimal = Field(default=Decimal("0"))
    credit_total: Decimal = Field(default=Decimal("0"))
    is_balanced: bool = True
    difference: Decimal = Field(default=Decimal("0"))


# ────────────────────────────────────────────────────────────────
# CRUD 端点
# ────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ConsolTrialResponse])
def list_trial_balance(
    project_id: UUID,
    year: int,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    return get_trial_balance(db, project_id, year)


@router.post("/", response_model=ConsolTrialResponse, status_code=201)
def create_trial_row(
    project_id: UUID,
    year: int,
    standard_account_code: str,
    account_name: str | None = None,
    account_category: str | None = None,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    """
    创建合并试算表行。

    如果相同 project_id + year + standard_account_code 的记录已存在，
    则更新该记录；否则创建新记录。
    """
    trial = upsert_trial_row(
        db,
        project_id=project_id,
        year=year,
        standard_account_code=standard_account_code,
        account_name=account_name,
        account_category=account_category,
    )
    return trial


@router.get("/summary", response_model=ConsolTrialSummary)
def get_trial_summary(
    project_id: UUID,
    year: int,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    """
    获取合并试算表汇总信息。

    返回各列合计、借方合计、贷方合计、借贷平衡状态。
    """
    trials = get_trial_balance(db, project_id, year)

    summary = ConsolTrialSummary(row_count=len(trials))

    debit_total = Decimal("0")
    credit_total = Decimal("0")

    for trial in trials:
        summary.total_individual_sum += trial.individual_sum or Decimal("0")
        summary.total_consol_adjustment += trial.consol_adjustment or Decimal("0")
        summary.total_consol_elimination += trial.consol_elimination or Decimal("0")
        summary.total_consol_amount += trial.consol_amount or Decimal("0")

        # 借贷平衡判断：资产类科目（1开头）借加贷减，负债/权益类（2/3/4）贷加借减
        account_code = trial.standard_account_code or ""
        if account_code.startswith("1"):
            debit_total += trial.consol_amount or Decimal("0")
        else:
            credit_total += trial.consol_amount or Decimal("0")

    summary.debit_total = debit_total
    summary.credit_total = credit_total
    summary.difference = abs(debit_total - credit_total)
    summary.is_balanced = summary.difference == Decimal("0")

    return summary


@router.get("/{trial_id}", response_model=ConsolTrialResponse)
def get_trial_by_id(
    trial_id: UUID,
    project_id: UUID,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    trial = get_trial_row(db, trial_id, project_id)
    if not trial:
        raise HTTPException(status_code=404, detail="试算表行不存在")
    return trial


@router.put("/{trial_id}", response_model=ConsolTrialResponse)
def update_trial_row(
    trial_id: UUID,
    project_id: UUID,
    year: int,
    data: ConsolTrialUpdate,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    """
    更新合并试算表行。

    支持更新的字段：account_name、account_category、各金额列。
    """
    existing = get_trial_row(db, trial_id, project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="试算表行不存在")

    # 更新字段
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(existing, field, value)

    db.commit()
    db.refresh(existing)
    return existing


@router.delete("/{trial_id}", status_code=204)
def delete_trial_row(
    trial_id: UUID,
    project_id: UUID,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    if not delete_trial(db, trial_id, project_id):
        raise HTTPException(status_code=404, detail="试算表行不存在")


# ────────────────────────────────────────────────────────────────
# 7.1 汇总各公司审定数
# ────────────────────────────────────────────────────────────────

@router.post("/aggregate", response_model=list[ConsolTrialResponse])
def trigger_aggregate(
    project_id: UUID,
    year: int,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    """
    触发汇总：汇总纳入合并范围各公司的审定数到标准科目。

    对于外币子公司，使用 forex_translation 中的折算后金额。
    对于本币公司，直接汇总 trial_balance.audited_amount。
    根据合并方法（full/equity/proportional）处理汇总比例。

    Validates: Requirements 3.1, 3.2
    """
    trials = aggregate_individual(db, project_id, year)
    db.commit()
    for trial in trials:
        db.refresh(trial)
    return trials


# ────────────────────────────────────────────────────────────────
# 7.2 抵消分录重算 & 合并数重算
# ────────────────────────────────────────────────────────────────

@router.post("/recalc-elimination", response_model=list[ConsolTrialResponse])
def trigger_recalc_elimination(
    project_id: UUID,
    year: int,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    """
    重新汇总已审批抵消分录的金额，按标准科目代码汇总。

    只汇总 status='approved' 的抵消分录。
    抵消方向（debit/credit）决定是加还是减。

    Validates: Requirements 3.4
    """
    trials = recalc_elimination(db, project_id, year)
    db.commit()
    for trial in trials:
        db.refresh(trial)
    return trials


@router.post("/recalc-consol-amount", response_model=list[ConsolTrialResponse])
def trigger_recalc_consol_amount(
    project_id: UUID,
    year: int,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    """
    重新计算合并数：consol_amount = individual_sum + consol_adjustment + consol_elimination。

    前提条件：aggregate_individual 和 recalc_elimination 已执行。
    本端点更新 consol_elimination（调用 recalc_elimination）并重新计算 consol_amount。

    Validates: Requirements 3.4
    """
    trials = recalc_consol_amount(db, project_id, year)
    db.commit()
    for trial in trials:
        db.refresh(trial)
    return trials


# ────────────────────────────────────────────────────────────────
# 7.3 完整全量重算
# ────────────────────────────────────────────────────────────────

@router.post("/full-recalc", response_model=list[ConsolTrialResponse])
def trigger_full_recalc(
    project_id: UUID,
    year: int,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    """
    完整全量重算合并试算表。

    执行步骤：
    1. aggregate_individual — 汇总各公司审定数
    2. recalc_elimination — 汇总已审批抵消分录
    3. recalc_consol_amount — 计算合并数 = individual_sum + consol_adjustment + consol_elimination

    这是最可靠的兜底重算方法，所有合并数都会重新计算。

    Validates: Requirements 3.4
    """
    trials = full_recalc(db, project_id, year)
    db.commit()
    for trial in trials:
        db.refresh(trial)
    return trials


# ────────────────────────────────────────────────────────────────
# 7.3 一致性校验
# ────────────────────────────────────────────────────────────────

@router.get("/consistency-check", response_model=ConsistencyCheckResult)
def check_consistency_endpoint(
    project_id: UUID,
    year: int,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    """
    合并试算表一致性校验。

    校验内容：
    1. 借贷平衡：所有合并金额的借方合计 = 贷方合计
    2. 抵消列校验：consol_elimination = 已审批抵消分录汇总
    3. 合并数公式：consol_amount = individual_sum + consol_adjustment + consol_elimination

    Validates: Requirements 3.4
    """
    result = check_consistency(db, project_id, year)
    return result
