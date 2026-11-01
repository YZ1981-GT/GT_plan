"""试算表陈旧口径提示（spec income-statement-lower-section-formulas，ADR-ISL-05）。

补齐利润链公式后，金额与符号是否可信完全取决于试算表本身的口径。真实项目里存在旧代码算出、
之后没再重算的陈旧结果（余额表 ``sign_convention_version`` 为 v1，报表营业收入为负）。本模块
**只提示、不改数据、不改公式**：报表生成时检查两项，任一成立就在利润表结果上追加一条中文 warning。

- 口径残留：``sign_convention_guard.check_sign_convention_readiness`` 报余额表含 v1 行；
- 符号异常：试算表里**贷方性质的损益科目**（SQL 先以 ``account_category in {revenue, expense}``
  缩小范围，再由 ``resolve_account_direction(code, name)`` 判方向；这样历史上误标为 expense 的 6001 仍能检出）
  审定数为负。

数据修复是运维动作（``migrate_account_category_correction.py`` / ``migrate_sign_convention_v2.py``），
按 S9 design §4 D3 由用户决定，本模块不执行。
"""
from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: 损益类别先用于缩小 SQL 扫描面；最终贷方方向仍由 ``resolve_account_direction`` 判定。
#: 同时纳入 expense，才能抓到历史上把 6001 营业收入误标为 expense 的行（design §1 第 12 行）。
PL_CATEGORIES = ("revenue", "expense")
STALE_WARNING = (
    "试算表是按旧口径算出的，利润表各行的金额和符号可能不对，请先全量重算试算表再生成报表"
)
#: 提示里最多点名几个科目（避免一条 warning 过长）
_MAX_SAMPLES = 5


async def negative_credit_pl_accounts(
    db: AsyncSession, project_id: UUID, year: int, *, limit: int = _MAX_SAMPLES,
) -> list[str]:
    """贷方性质损益科目里审定数为负的科目码（正数口径下不该出现）。"""
    from app.models.audit_platform_models import TrialBalance
    from app.services.ledger_import.direction_resolver import resolve_account_direction

    rows = (await db.execute(
        sa.select(
            TrialBalance.standard_account_code,
            TrialBalance.account_name,
        )
        .where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
            TrialBalance.account_category.in_(PL_CATEGORIES),
            TrialBalance.audited_amount < Decimal("0"),
        )
        .order_by(TrialBalance.standard_account_code)
    )).all()
    out: list[str] = []
    seen: set[str] = set()
    for code, name in rows:
        direction, _source = resolve_account_direction(code or "", name or "")
        if code and direction == "credit" and code not in seen:
            out.append(code)
            seen.add(code)
            if len(out) >= limit:
                break
    return out


async def stale_trial_balance_warning(
    db: AsyncSession, project_id: UUID, year: int,
) -> str | None:
    """两项检查任一成立 ⇒ 返回中文提示；都不成立 ⇒ ``None``。检查自身出错只记日志、不拦报表生成。"""
    from app.services.ledger_import.sign_convention_guard import check_sign_convention_readiness

    reasons: list[str] = []
    try:
        # 提示性查询也必须用保存点：PG 上任一 SQL 报错会把外层报表生成事务置 aborted；
        # 只 catch 异常而不回滚到保存点并不是真正的 fail-open。
        async with db.begin_nested():
            readiness = await check_sign_convention_readiness(db, project_id, year)
        if readiness.has_legacy:
            reasons.append("余额表仍有旧符号约定（v1）的行")
    except Exception:  # noqa: BLE001 —— 提示性检查，失败不影响报表生成
        logger.warning("试算表口径检查失败（符号约定）", exc_info=True)
    try:
        async with db.begin_nested():
            negatives = await negative_credit_pl_accounts(db, project_id, year)
        if negatives:
            reasons.append(f"贷方性质的损益科目审定数为负（{'、'.join(negatives)}）")
    except Exception:  # noqa: BLE001 —— 同上
        logger.warning("试算表口径检查失败（损益科目符号）", exc_info=True)
    if not reasons:
        return None
    return f"{STALE_WARNING}；检出：{'；'.join(reasons)}"
