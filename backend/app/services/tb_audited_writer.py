"""试算表审定数统一写入器。

底稿发布是唯一允许写入 ``TrialBalance.audited_amount`` 的发布门。
本模块只负责定位目标行、计算底稿调整分量并 flush；事务提交由调用方统一完成。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance


@dataclass(frozen=True)
class PublishRowSkip:
    """一条发布行未写入的可审计原因。"""

    account_code: str
    reason: str
    company_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublishRowResult:
    """一条实际发布行的结果。"""

    account_code: str
    audited_amount: Decimal
    previous_amount: Decimal | None
    published_at: datetime


@dataclass
class PublishRowsResult:
    """审定数发布结果；不代表事务已经提交。"""

    updated_account_codes: list[str] = field(default_factory=list)
    updated_rows: list[PublishRowResult] = field(default_factory=list)
    skipped: list[PublishRowSkip] = field(default_factory=list)

    @property
    def updated_count(self) -> int:
        return len(self.updated_account_codes)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


_ZERO = Decimal("0")


def _decimal(value: Any, *, field_name: str) -> Decimal:
    """将发布载荷转为两位金额；非法值必须失败而不是静默写零。"""
    if value is None:
        raise ValueError(f"{field_name} 不能为空")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 不是有效金额: {value!r}") from exc


def _row_values(row: Any) -> tuple[str, Decimal]:
    """读取 dict 或轻量对象形式的发布行。"""
    if isinstance(row, dict):
        account_code = row.get("account_code") or row.get("standard_account_code")
        audited = row.get("audited_amount")
    else:
        account_code = getattr(row, "account_code", None) or getattr(
            row, "standard_account_code", None
        )
        audited = getattr(row, "audited_amount", None)

    account_code = str(account_code or "").strip()
    if not account_code:
        raise ValueError("发布行缺少 account_code")
    return account_code, _decimal(audited, field_name=f"{account_code}.audited_amount")


async def publish_rows(
    session: AsyncSession,
    project_id: UUID,
    year: int,
    rows: Iterable[dict[str, Any] | Any],
    *,
    source: str,
) -> PublishRowsResult:
    """将审定表行发布到试算表，并记录底稿调整增量。

    每个科目按项目/年度/科目查询未删除行：无行或多公司编码均跳过；唯一目标行
    再以同一条 ``UPDATE`` 写入 ``audited_amount``、``wp_adjustment``、发布基准和时间。
    ``source`` 必须由调用方显式提供，便于审计调用点保留来源；本函数不 commit。
    """
    if not source or not source.strip():
        raise ValueError("source 不能为空")

    result = PublishRowsResult()
    publish_time = datetime.now(timezone.utc)
    seen: set[str] = set()

    for raw_row in rows:
        account_code, audited_amount = _row_values(raw_row)
        if account_code in seen:
            result.skipped.append(
                PublishRowSkip(account_code, "同一发布载荷重复出现，避免重复写入")
            )
            continue
        seen.add(account_code)

        target_id = (
            raw_row.get("trial_balance_id")
            if isinstance(raw_row, dict)
            else getattr(raw_row, "trial_balance_id", None)
        )
        query = (
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted.is_(False),
            )
            .with_for_update()
        )
        if target_id is not None:
            query = query.where(TrialBalance.id == target_id)
        rows_result = await session.execute(query)
        candidates = list(rows_result.scalars().all())

        if not candidates:
            result.skipped.append(PublishRowSkip(account_code, "未找到未删除的试算表行"))
            continue

        company_codes = tuple(sorted({str(row.company_code) for row in candidates}))
        if len(company_codes) != 1 or len(candidates) != 1:
            result.skipped.append(
                PublishRowSkip(
                    account_code,
                    "同一科目命中多个公司编码，未猜测目标公司",
                    company_codes,
                )
            )
            continue

        target = candidates[0]
        previous_amount = target.audited_amount
        unadjusted = target.unadjusted_amount or _ZERO
        rje = target.rje_adjustment or _ZERO
        aje = target.aje_adjustment or _ZERO
        wp_adjustment = audited_amount - (unadjusted + rje + aje)

        update_stmt = (
            sa.update(TrialBalance)
            .where(
                TrialBalance.id == target.id,
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted.is_(False),
            )
            .values(
                audited_amount=audited_amount,
                wp_adjustment=wp_adjustment,
                wp_publish_base=unadjusted,
                wp_published_at=publish_time,
                updated_at=publish_time,
            )
        )
        update_result = await session.execute(update_stmt)
        if update_result.rowcount == 1:
            result.updated_account_codes.append(account_code)
            result.updated_rows.append(
                PublishRowResult(
                    account_code=account_code,
                    audited_amount=audited_amount,
                    previous_amount=previous_amount,
                    published_at=publish_time,
                )
            )
        else:
            result.skipped.append(
                PublishRowSkip(account_code, "目标行在发布期间已删除或不存在")
            )

    await session.flush()
    return result
