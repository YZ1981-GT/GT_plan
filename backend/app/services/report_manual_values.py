"""审定报表手工值（迁移 V260 ``financial_report.manual_amounts``，spec citar-table-manual-edit R6）。

- 存储：``{"current": {"value": "…", "auto": "…"}, "prior": {…}, "by": 用户 id, "at": 时间}``；
  ``current_period_amount`` / ``prior_period_amount`` 始终是生效值（手工优先），导出、单体报表、跨表 ROW() 零改动读到手工值。
- 生成 / 增量重算 / 过期重算写金额一律经 ``apply_auto``：有手工值的列只刷新 ``auto``，生效值不动。
- 生成时手工的本期值进 ROW() 缓存、手工的上期值进上期缓存 ⇒ 合计按手工值算。
  例外：上期取自上年项目已生成报表时，上期合计照搬上年报表（不按本年手工明细重加），需要时手工改合计行。
- ``save_manual``：改 / 恢复一批格（service 只 flush，路由重新生成报表后 commit）。
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReport, FinancialReportType

COLUMNS = {"current": "current_period_amount", "prior": "prior_period_amount"}
MAX_ITEMS = 500


def _dec(v: Any) -> Decimal | None:
    if v is None:
        return None
    return Decimal(str(v))


def _text(v: Decimal | None) -> str | None:
    return None if v is None else str(v)


def manual_value(manual: dict | None, column: str) -> tuple[bool, Decimal | None]:
    """(该列是否手工, 手工值)。手工值可以是 None（手工清空）。"""
    entry = (manual or {}).get(column)
    if not isinstance(entry, dict):
        return False, None
    return True, _dec(entry.get("value"))


def effective(manual: dict | None, column: str, auto: Decimal | None) -> Decimal | None:
    is_manual, value = manual_value(manual, column)
    return value if is_manual else auto


def apply_auto(row: FinancialReport, column: str, auto: Decimal | None) -> None:
    """写自动算出的金额：该列有手工值时只记 auto、生效值保持手工值。"""
    manual = row.manual_amounts or {}
    entry = manual.get(column)
    if isinstance(entry, dict):
        if entry.get("auto") != _text(auto):
            row.manual_amounts = {**manual, column: {**entry, "auto": _text(auto)}}
        setattr(row, COLUMNS[column], _dec(entry.get("value")))
        return
    setattr(row, COLUMNS[column], auto)


async def load_manual(db: AsyncSession, project_id: UUID, year: int, report_type: FinancialReportType) -> dict[str, dict]:
    """本表有手工值的行：row_code → manual_amounts。"""
    rows = (await db.execute(
        sa.select(FinancialReport.row_code, FinancialReport.manual_amounts).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == report_type,
            FinancialReport.is_deleted == sa.false(),
            FinancialReport.manual_amounts.is_not(None),
        )
    )).all()
    # 只认有列的手工值（V260 修复前恢复全部手工值会留 JSON null / 只剩 by、at 的空壳）
    return {r.row_code: r.manual_amounts for r in rows if isinstance(r.manual_amounts, dict) and any(c in r.manual_amounts for c in COLUMNS)}


def _parse_amount(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise HTTPException(status_code=422, detail="金额只能填数字")
    try:
        v = Decimal(str(raw).replace(",", "").strip())
    except InvalidOperation:
        raise HTTPException(status_code=422, detail=f"金额只能填数字：{raw}") from None
    if not v.is_finite() or abs(v) >= Decimal("1e18"):
        raise HTTPException(status_code=422, detail=f"金额超出范围：{raw}")
    return v.quantize(Decimal("0.01"))


async def save_manual(db: AsyncSession, project_id: UUID, year: int, items: list[dict], user_id: UUID) -> int:
    """``items`` = [{report_type, row_code, column: current|prior, value?, restore?}]；返回改动的格数。"""
    if not items:
        return 0
    if len(items) > MAX_ITEMS:
        raise HTTPException(status_code=422, detail="一次修改的格子过多")
    changed = 0
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for item in items:
        try:
            report_type = FinancialReportType(item.get("report_type"))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"报表类型无效：{item.get('report_type')}") from None
        column = item.get("column")
        if column not in COLUMNS:
            raise HTTPException(status_code=422, detail=f"列无效：{column}")
        row = (await db.execute(
            sa.select(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == report_type,
                FinancialReport.row_code == item.get("row_code"),
                FinancialReport.is_deleted == sa.false(),
            )
        )).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=409, detail="报表尚未生成或行次不存在，请先生成报表")
        manual = dict(row.manual_amounts or {})
        entry = manual.get(column) if isinstance(manual.get(column), dict) else None
        if item.get("restore"):
            if entry is None:
                continue
            manual.pop(column)
            setattr(row, COLUMNS[column], _dec(entry.get("auto")))
        else:
            value = _parse_amount(item.get("value"))
            auto = entry.get("auto") if entry else _text(getattr(row, COLUMNS[column]))
            manual[column] = {"value": _text(value), "auto": auto}
            setattr(row, COLUMNS[column], value)
        has_columns = any(k in manual for k in COLUMNS)
        row.manual_amounts = {**manual, "by": str(user_id), "at": now} if has_columns else None
        changed += 1
    await db.flush()
    return changed
