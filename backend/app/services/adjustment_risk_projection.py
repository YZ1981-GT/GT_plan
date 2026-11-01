"""调整分录组的重要性比例、性质风险与复核层级投影。"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import Adjustment
from app.services.materiality_service import MaterialityService

_HIGH_RISK_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("revenue_recognition", "收入确认", ("收入", "销售", "确认收入")),
    ("management_override", "管理层凌驾", ("管理层凌驾", "管理层调整", "越权调整")),
    ("related_party", "关联方", ("关联方", "关联交易")),
    ("significant_estimate", "重大会计估计", ("重大会计估计", "重大估计", "复杂估计")),
    ("abnormal_voucher", "异常凭证", ("异常凭证", "无凭证", "补录凭证")),
)
_PERIOD_END_TERMS = ("期末", "年末", "结账后", "资产负债表日后")
_REVENUE_CODES = ("6001", "6051")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _ratio(amount: Decimal, threshold: Decimal | None) -> Decimal | None:
    if threshold is None or threshold <= 0:
        return None
    return (amount / threshold * Decimal("100")).quantize(Decimal("0.01"))


def _flag(code: str, label: str, reason: str) -> dict[str, str]:
    return {"code": code, "label": label, "reason": reason}


async def project_adjustment_risk(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    rows: list[Adjustment],
    materiality: Any = ...,
) -> dict[str, Any]:
    """按一笔完整分录组计算可解释风险；不写库。"""
    if not rows:
        raise ValueError("分录不存在或已删除")
    debit = sum((_decimal(row.debit_amount) for row in rows), Decimal("0"))
    credit = sum((_decimal(row.credit_amount) for row in rows), Decimal("0"))
    amount = max(debit, credit)
    text = " ".join(
        str(value or "")
        for row in rows
        for value in (row.description, row.account_name)
    )
    codes = {str(row.account_code or "") for row in rows}
    flags: list[dict[str, str]] = []
    for code, label, terms in _HIGH_RISK_RULES:
        if any(term in text for term in terms):
            flags.append(_flag(code, label, f"摘要或科目含{label}相关表述"))
    if any(account.startswith(_REVENUE_CODES) for account in codes) and not any(
        item["code"] == "revenue_recognition" for item in flags
    ):
        flags.append(_flag("revenue_recognition", "收入确认", "涉及营业收入类标准科目"))
    first = rows[0]
    if (first.origin or "manual") == "manual" and any(term in text for term in _PERIOD_END_TERMS):
        flags.append(_flag("period_end_manual", "期末手工分录", "手工分录摘要含期末或年末表述"))

    if materiality is ...:
        materiality = await MaterialityService(db).get_current(project_id, year)
    overall = _decimal(materiality.overall_materiality) if materiality else None
    performance = _decimal(materiality.performance_materiality) if materiality else None
    trivial = _decimal(materiality.trivial_threshold) if materiality else None
    reaches_performance = bool(performance and performance > 0 and amount >= performance)
    reaches_overall = bool(overall and overall > 0 and amount >= overall)
    high_risk = bool(flags)
    required_level = "partner" if reaches_performance or high_risk else "manager"
    evidence_required = required_level == "partner"
    return {
        "entry_group_id": str(first.entry_group_id),
        "amount": amount,
        "total_debit": debit,
        "total_credit": credit,
        "materiality_configured": materiality is not None,
        "overall_materiality": overall,
        "performance_materiality": performance,
        "trivial_threshold": trivial,
        "overall_ratio": _ratio(amount, overall),
        "performance_ratio": _ratio(amount, performance),
        "trivial_ratio": _ratio(amount, trivial),
        "reaches_overall": reaches_overall,
        "reaches_performance": reaches_performance,
        "above_trivial": bool(trivial and trivial > 0 and amount >= trivial),
        "risk_flags": flags,
        "high_risk": high_risk,
        "required_level": required_level,
        "evidence_required": evidence_required,
    }


async def project_adjustment_risks(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    group_ids: list[UUID],
) -> dict[str, dict[str, Any]]:
    """批量投影列表页分录风险；整页只读取一次重要性。"""
    if not group_ids:
        return {}
    import sqlalchemy as sa

    rows = list((await db.execute(sa.select(Adjustment).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.entry_group_id.in_(group_ids),
        Adjustment.is_deleted == sa.false(),
    ))).scalars().all())
    grouped: dict[UUID, list[Adjustment]] = {}
    for row in rows:
        grouped.setdefault(row.entry_group_id, []).append(row)
    materiality = await MaterialityService(db).get_current(project_id, year)
    out: dict[str, dict[str, Any]] = {}
    for group_id, group_rows in grouped.items():
        out[str(group_id)] = await project_adjustment_risk(
            db, project_id=project_id, year=year, rows=group_rows,
            materiality=materiality,
        )
    return out
