"""调整分录科目下拉（spec adjustment-hall-entry-review-closure 需求 1.1）。

原先只取「已确认报表行映射」的标准科目：真库和平物流 / 四川物流 / 和平药房 2024 已确认映射为 0
⇒ 下拉为空、大厅录不了分录。现在不传行次时列出本项目全部标准科目，已确认映射的附报表项目；
传年度时附试算表审定数作参考余额。传 ``report_line_code`` 时仍只返回该行次下已确认映射的科目。
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    AccountSource,
    ReportLineMapping,
    TrialBalance,
)
from app.models.audit_platform_schemas import AccountOption


async def list_account_options(
    db: AsyncSession,
    project_id: UUID,
    *,
    report_line_code: str | None = None,
    year: int | None = None,
) -> list[AccountOption]:
    rlm = ReportLineMapping.__table__
    ac = AccountChart.__table__
    standard = sa.and_(
        ac.c.project_id == project_id,
        ac.c.source == AccountSource.standard.value,
        ac.c.is_deleted == sa.false(),
    )

    if report_line_code is not None:
        q = (
            sa.select(rlm.c.standard_account_code, rlm.c.report_line_name, ac.c.account_name, ac.c.level)
            .select_from(rlm.join(ac, sa.and_(standard, ac.c.account_code == rlm.c.standard_account_code)))
            .where(
                rlm.c.project_id == project_id,
                rlm.c.report_line_code == report_line_code,
                rlm.c.is_deleted == sa.false(),
                rlm.c.is_confirmed == sa.true(),
            )
            .order_by(rlm.c.standard_account_code)
        )
        rows = (await db.execute(q)).fetchall()
        return [
            AccountOption(
                code=r.standard_account_code,
                name=r.account_name or "",
                level=r.level or 1,
                report_line=r.report_line_name,
            )
            for r in rows
        ]

    accounts = (await db.execute(
        sa.select(ac.c.account_code, ac.c.account_name, ac.c.level).where(standard).order_by(ac.c.account_code)
    )).fetchall()
    report_lines: dict[str, str] = {}
    for code, line_name in (await db.execute(
        sa.select(rlm.c.standard_account_code, rlm.c.report_line_name).where(
            rlm.c.project_id == project_id,
            rlm.c.is_deleted == sa.false(),
            rlm.c.is_confirmed == sa.true(),
        )
    )).fetchall():
        if code and line_name and code not in report_lines:
            report_lines[code] = line_name

    balances: dict[str, Decimal] = {}
    if year is not None:
        tb = TrialBalance.__table__
        for code, amount in (await db.execute(
            sa.select(tb.c.standard_account_code, sa.func.sum(tb.c.audited_amount))
            .where(tb.c.project_id == project_id, tb.c.year == year, tb.c.is_deleted == sa.false())
            .group_by(tb.c.standard_account_code)
        )).fetchall():
            if code is not None and amount is not None:
                balances[code] = Decimal(str(amount))

    options: list[AccountOption] = []
    seen: set[str] = set()
    for code, name, level in accounts:
        if not code or code in seen:
            continue
        seen.add(code)
        options.append(AccountOption(
            code=code,
            name=name or "",
            level=level or 1,
            report_line=report_lines.get(code),
            balance=balances.get(code),
        ))
    return options
