"""Memory-bounded XLSX export for ordinary and auxiliary Ledger windows."""
from __future__ import annotations

import json
import tempfile
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbAuxLedger, TbLedger
from app.schemas.ledger_window import LedgerWindowQuery
from app.services.ledger_penetration_service import _attach_extra_fields
from app.services.ledger_window_service import (
    Kind,
    LedgerWindowService,
    _order,
    _range_conditions,
    _scope_conditions,
)

_UNSET = object()


def _visible(row: dict[str, Any], query: LedgerWindowQuery, *, auxiliary: bool) -> bool:
    if query.keyword:
        needle = query.keyword.lower()
        values = [row.get("summary"), row.get("voucher_no"), row.get("voucher_date")]
        values.append(row.get("aux_code") if auxiliary else row.get("counterpart_account"))
        if auxiliary:
            values.append(row.get("aux_name"))
        if not any(needle in str(value or "").lower() for value in values):
            return False
    debit, credit = Decimal(str(row.get("debit_amount") or 0)), Decimal(str(row.get("credit_amount") or 0))
    if query.amount_dir == "debit" and debit <= 0:
        return False
    if query.amount_dir == "credit" and credit <= 0:
        return False
    return True


def _extra_value(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value


async def _chunks(stream, size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    try:
        while True:
            chunk = stream.read(size)
            if not chunk:
                break
            yield chunk
    finally:
        stream.close()


async def build_ledger_export(
    db: AsyncSession,
    kind: Kind,
    project_id: UUID,
    query: LedgerWindowQuery,
) -> tuple[AsyncIterator[bytes], str, int]:
    """Build a write-only workbook while streaming rows from PostgreSQL.

    The temporary file can spill to disk, so browser export no longer retains
    every ledger row in JavaScript or Python object lists.
    """
    auxiliary = kind == "aux_ledger"
    service = LedgerWindowService(db)
    if auxiliary and not query.aux_type:
        # Reuse the service's stable error contract.
        await service.fetch(kind, project_id, "export", query)
        raise AssertionError("unreachable")
    table = TbAuxLedger.__table__ if auxiliary else TbLedger.__table__
    dataset_id = await service._active_dataset(project_id, query.year)
    annual = await service._opening(project_id, dataset_id, query, auxiliary=auxiliary)
    opening = await service._range_opening(table, project_id, dataset_id, query, annual, auxiliary=auxiliary)
    extra_columns = await service._extra_columns(table, project_id, dataset_id, query, auxiliary=auxiliary)

    columns = [
        table.c.id, table.c.voucher_date, table.c.voucher_no,
        table.c.account_code, table.c.account_name,
        table.c.debit_amount, table.c.credit_amount,
        table.c.summary, table.c.voucher_type, table.c.company_code,
        table.c.accounting_period, table.c.raw_extra,
    ]
    if auxiliary:
        columns.extend([table.c.aux_type, table.c.aux_code, table.c.aux_name])
    else:
        columns.append(table.c.counterpart_account)
    stmt = (sa.select(*columns)
            .where(*_scope_conditions(table, project_id, dataset_id, query, auxiliary=auxiliary),
                   *_range_conditions(table, query))
            .order_by(*_order(table.c)).execution_options(yield_per=1000))

    book = Workbook(write_only=True)
    sheet = book.create_sheet(title=("辅助明细_" if auxiliary else "序时账_") + query.account_code.replace("*", "")[:20])
    fixed_headers = ["日期", "凭证号", "摘要", "借方", "贷方", "余额", "余额方向"]
    if auxiliary:
        fixed_headers.extend(["辅助类型", "辅助编码", "辅助名称"])
    else:
        fixed_headers.append("对方科目")
    sheet.append([*fixed_headers, *extra_columns])
    opening_row = [None, None, "范围期初余额", None, None, abs(opening), "贷" if opening < 0 else "借"]
    opening_row.extend([None, None, None] if auxiliary else [None])
    sheet.append([*opening_row, *([None] * len(extra_columns))])

    running = opening
    current_month: str | None | object = _UNSET
    month_debit, month_credit, month_visible = Decimal(0), Decimal(0), 0
    exported = 0

    def append_subtotal() -> None:
        nonlocal month_debit, month_credit, month_visible
        if month_visible:
            label = f"{current_month} 本月合计" if current_month else "未注明日期合计"
            row = [None, None, label, month_debit, month_credit, abs(running), "贷" if running < 0 else "借"]
            row.extend([None, None, None] if auxiliary else [None])
            sheet.append([*row, *([None] * len(extra_columns))])
        month_debit, month_credit, month_visible = Decimal(0), Decimal(0), 0

    result = await db.stream(stmt)
    try:
        async for record in result.mappings():
            row = dict(record)
            value = row.get("voucher_date")
            month = value.strftime("%Y-%m") if value is not None else None
            # A dedicated sentinel is needed because ``None`` is the valid undated month.
            if current_month is _UNSET:
                current_month = month
            elif month != current_month:
                append_subtotal()
                current_month = month
            debit = Decimal(str(row.get("debit_amount") or 0))
            credit = Decimal(str(row.get("credit_amount") or 0))
            running += debit - credit
            if not _visible(row, query, auxiliary=auxiliary):
                continue
            row = _attach_extra_fields([row])[0]
            month_debit += debit
            month_credit += credit
            month_visible += 1
            exported += 1
            values = [row.get("voucher_date"), row.get("voucher_no"), row.get("summary"),
                      debit or None, credit or None, abs(running), "贷" if running < 0 else "借"]
            if auxiliary:
                values.extend([row.get("aux_type"), row.get("aux_code"), row.get("aux_name")])
            else:
                values.append(row.get("counterpart_account"))
            values.extend(_extra_value(row["extra_fields"].get(key)) for key in extra_columns)
            sheet.append(values)
    finally:
        await result.close()
    append_subtotal()

    stream = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    book.save(stream)
    stream.seek(0)
    label = query.account_code.replace("*", "")
    filename = f"{'辅助明细账' if auxiliary else '序时账'}_{label}_{query.year}.xlsx"
    return _chunks(stream), filename, exported
