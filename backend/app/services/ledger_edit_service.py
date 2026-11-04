"""科目余额表 / 序时账人工修改（spec citar-table-manual-edit R3~R5）。

- 直接改当前数据集的 ``tb_balance`` / ``tb_ledger`` 行：试算表、底稿取数、报表等读取方不用改就读到新值；
  每次修改写 ``ledger_manual_edits``（改前 / 改后的字段值），用于标出改过的行、显示原值、恢复导入原值。
- 余额表只改末级（数据集里没有下级）；数据集里真实存在的上级行按「借正贷负」差额同步（记 cascade）。
  余额按行原有存法写回：有方向列的存正数 + 方向，没有方向列的存借正贷负。
- 恢复 = 取该行第一次修改的 ``before`` 原样写回（上级随之回调）。
- 序时账可改日期、凭证号、摘要、科目、借贷金额；不回写余额表（试算表取余额表）。
- service 只 flush，路由 commit。
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbBalance, TbLedger
from app.models.ledger_edit_models import (
    ACTION_CASCADE,
    ACTION_EDIT,
    ACTION_RESTORE,
    TABLE_BALANCE,
    TABLE_LEDGER,
    LedgerManualEdit,
)
from app.services.dataset_query import get_active_dataset_id_or_none, get_active_filter

_ZERO = Decimal(0)
_MAX_AMOUNT = Decimal("1e17")
MAX_TEXT = 500

#: 余额表存储字段（含方向）：日志的 before / after 只记这些
BALANCE_FIELDS = ("opening_balance", "opening_direction", "debit_amount", "credit_amount", "closing_balance", "closing_direction")
LEDGER_FIELDS = ("voucher_date", "voucher_no", "summary", "account_code", "account_name", "debit_amount", "credit_amount",
                 "accounting_period")


# ── 值处理 ──
def _amount(raw: Any, label: str) -> Decimal | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise HTTPException(status_code=422, detail=f"{label}只能填数字")
    try:
        v = Decimal(str(raw).replace(",", "").strip())
    except InvalidOperation:
        raise HTTPException(status_code=422, detail=f"{label}只能填数字") from None
    if not v.is_finite() or abs(v) >= _MAX_AMOUNT:
        raise HTTPException(status_code=422, detail=f"{label}超出范围")
    return v.quantize(Decimal("0.01"))


def _signed(amount: Decimal | None, direction: str | None) -> Decimal:
    """借正贷负（与 tb_mapping_sql.signed_balance 同口径：方向列优先，缺方向原值）。"""
    a = amount or _ZERO
    if direction == "credit":
        return -abs(a)
    if direction == "debit":
        return abs(a)
    return a


def _stored(signed: Decimal, direction: str | None) -> tuple[Decimal, str | None]:
    """借正贷负 → 按行原有存法：有方向列存正数 + 方向（0 保留原方向），没有方向列存借正贷负。"""
    if direction in ("debit", "credit"):
        if signed > 0:
            return signed, "debit"
        if signed < 0:
            return -signed, "credit"
        return _ZERO, direction
    return signed, direction


def _json(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def _snapshot(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: _json(getattr(row, f)) for f in fields}


def _norm(code: str | None) -> str:
    c = (code or "").strip()
    return c[:-2] if c.endswith(".0") else c


def _descends(child: str, parent: str) -> bool:
    """与 tb_mapping_sql.is_descendant 同口径：编码以上级编码开头且更长。"""
    c, p = _norm(child), _norm(parent)
    return c != p and c.startswith(p)


# ── 余额表 ──
async def _balance_rows(db: AsyncSession, project_id: UUID, year: int) -> list[TbBalance]:
    tbl = TbBalance.__table__
    flt = await get_active_filter(db, tbl, project_id, year)
    return list((await db.execute(sa.select(TbBalance).where(flt))).scalars().all())


_last_stamp = dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _stamp() -> dt.datetime:
    """修改时间由应用写、本进程内严格递增：库默认 now() 是事务开始时间、SQLite 只到秒，同一秒的修改 / 恢复分不出先后。"""
    global _last_stamp
    now = dt.datetime.now(dt.timezone.utc)
    if now <= _last_stamp:
        now = _last_stamp + dt.timedelta(microseconds=1)
    _last_stamp = now
    return now


def _log(db: AsyncSession, project_id: UUID, year: int, dataset_id: UUID | None, table: str, row_id: UUID,
         action: str, before: dict, after: dict, user_id: UUID, reason: str | None) -> None:
    db.add(LedgerManualEdit(project_id=project_id, year=year, dataset_id=dataset_id, table_name=table, row_id=row_id,
                            action=action, before=before, after=after, edited_by=user_id, reason=reason,
                            edited_at=_stamp()))


async def _apply_balance(
    db: AsyncSession, project_id: UUID, year: int, row_id: UUID, target: dict[str, Any], action: str,
    user_id: UUID, reason: str | None, rows: list[TbBalance] | None = None,
) -> TbBalance:
    """把末级行写成 ``target``（存储字段原值），上级按借正贷负差额同步。"""
    if rows is None:
        rows = await _balance_rows(db, project_id, year)
    row = next((r for r in rows if r.id == row_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="科目余额行不存在（可能已重新导入）")
    if any(_descends(r.account_code, row.account_code) for r in rows if r.dataset_id == row.dataset_id):
        raise HTTPException(status_code=422, detail=f"{row.account_code} 有下级科目，请修改末级科目（上级随之汇总）")
    before = _snapshot(row, BALANCE_FIELDS)
    old = {
        "opening": _signed(row.opening_balance, row.opening_direction),
        "closing": _signed(row.closing_balance, row.closing_direction),
        "debit": row.debit_amount or _ZERO,
        "credit": row.credit_amount or _ZERO,
    }
    for f in BALANCE_FIELDS:
        if f in target:
            v = target[f]
            setattr(row, f, Decimal(v) if v is not None and not f.endswith("direction") else v)
    new = {
        "opening": _signed(row.opening_balance, row.opening_direction),
        "closing": _signed(row.closing_balance, row.closing_direction),
        "debit": row.debit_amount or _ZERO,
        "credit": row.credit_amount or _ZERO,
    }
    after = _snapshot(row, BALANCE_FIELDS)
    if after == before:
        return row
    dataset_id = row.dataset_id
    _log(db, project_id, year, dataset_id, TABLE_BALANCE, row.id, action, before, after, user_id, reason)

    delta = {k: new[k] - old[k] for k in new}
    for parent in rows:
        if parent.dataset_id != dataset_id or not _descends(row.account_code, parent.account_code):
            continue
        p_before = _snapshot(parent, BALANCE_FIELDS)
        for kind in ("opening", "closing"):
            if delta[kind]:
                amt_f, dir_f = f"{kind}_balance", f"{kind}_direction"
                signed = _signed(getattr(parent, amt_f), getattr(parent, dir_f)) + delta[kind]
                amount, direction = _stored(signed, getattr(parent, dir_f))
                setattr(parent, amt_f, amount)
                setattr(parent, dir_f, direction)
        for kind in ("debit", "credit"):
            if delta[kind]:
                setattr(parent, f"{kind}_amount", (getattr(parent, f"{kind}_amount") or _ZERO) + delta[kind])
        p_after = _snapshot(parent, BALANCE_FIELDS)
        if p_after != p_before:
            _log(db, project_id, year, dataset_id, TABLE_BALANCE, parent.id, ACTION_CASCADE, p_before, p_after, user_id,
                 f"下级 {row.account_code} 修改带动")
    await db.flush()
    return row


async def edit_balance(
    db: AsyncSession, project_id: UUID, year: int, row_id: UUID, values: dict[str, Any], user_id: UUID,
    reason: str | None = None,
) -> TbBalance:
    """``values``：opening / closing 为借正贷负金额，debit / credit 为发生额；不传的不改。"""
    rows = await _balance_rows(db, project_id, year)
    row = next((r for r in rows if r.id == row_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="科目余额行不存在（可能已重新导入）")
    target: dict[str, Any] = {}
    labels = {"opening": "期初余额", "closing": "期末余额", "debit": "本期借方", "credit": "本期贷方"}
    for key in ("opening", "closing"):
        if key in values:
            signed = _amount(values[key], labels[key]) or _ZERO
            amount, direction = _stored(signed, getattr(row, f"{key}_direction"))
            target[f"{key}_balance"] = amount
            target[f"{key}_direction"] = direction
    for key in ("debit", "credit"):
        if key in values:
            target[f"{key}_amount"] = _amount(values[key], labels[key])
    unknown = set(values) - set(labels)
    if unknown:
        raise HTTPException(status_code=422, detail=f"不能修改的字段：{', '.join(sorted(unknown))}")
    return await _apply_balance(db, project_id, year, row_id, target, ACTION_EDIT, user_id, _reason(reason), rows)


# ── 序时账 ──
async def _ledger_row(db: AsyncSession, project_id: UUID, year: int, row_id: UUID) -> TbLedger:
    tbl = TbLedger.__table__
    flt = await get_active_filter(db, tbl, project_id, year)
    row = (await db.execute(sa.select(TbLedger).where(flt, TbLedger.id == row_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="序时账分录不存在（可能已重新导入）")
    return row


def _ledger_target(values: dict[str, Any]) -> dict[str, Any]:
    allowed = {"voucher_date", "voucher_no", "summary", "account_code", "account_name", "debit_amount", "credit_amount"}
    unknown = set(values) - allowed
    if unknown:
        raise HTTPException(status_code=422, detail=f"不能修改的字段：{', '.join(sorted(unknown))}")
    target: dict[str, Any] = {}
    if "voucher_date" in values:
        try:
            d = dt.date.fromisoformat(str(values["voucher_date"]))
        except ValueError:
            raise HTTPException(status_code=422, detail="凭证日期格式应为 YYYY-MM-DD") from None
        target["voucher_date"] = d
        target["accounting_period"] = d.month
    for f, label in (("voucher_no", "凭证号"), ("account_code", "科目编码")):
        if f in values:
            v = str(values[f] or "").strip()
            if not v:
                raise HTTPException(status_code=422, detail=f"{label}不能为空")
            if len(v) > 100:
                raise HTTPException(status_code=422, detail=f"{label}过长")
            target[f] = v
    for f in ("summary", "account_name"):
        if f in values:
            v = values[f]
            if v is not None and (not isinstance(v, str) or len(v) > MAX_TEXT):
                raise HTTPException(status_code=422, detail="文字过长或格式不对")
            target[f] = v.strip() if isinstance(v, str) else None
    for f, label in (("debit_amount", "借方金额"), ("credit_amount", "贷方金额")):
        if f in values:
            target[f] = _amount(values[f], label)
    return target


async def _apply_ledger(db: AsyncSession, project_id: UUID, year: int, row: TbLedger, target: dict[str, Any],
                        action: str, user_id: UUID, reason: str | None) -> TbLedger:
    before = _snapshot(row, LEDGER_FIELDS)
    for f, v in target.items():
        setattr(row, f, v)
    after = _snapshot(row, LEDGER_FIELDS)
    if after != before:
        _log(db, project_id, year, row.dataset_id, TABLE_LEDGER, row.id, action, before, after, user_id, reason)
        await db.flush()
    return row


async def edit_ledger(db: AsyncSession, project_id: UUID, year: int, row_id: UUID, values: dict[str, Any],
                      user_id: UUID, reason: str | None = None) -> TbLedger:
    row = await _ledger_row(db, project_id, year, row_id)
    return await _apply_ledger(db, project_id, year, row, _ledger_target(values), ACTION_EDIT, user_id, _reason(reason))


# ── 恢复 / 列表 ──
def _reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    r = reason.strip()
    if len(r) > MAX_TEXT:
        raise HTTPException(status_code=422, detail="修改原因过长")
    return r or None


async def _row_log(db: AsyncSession, table: str, row_id: UUID) -> list[LedgerManualEdit]:
    return list((await db.execute(
        sa.select(LedgerManualEdit)
        .where(LedgerManualEdit.table_name == table, LedgerManualEdit.row_id == row_id)
        .order_by(LedgerManualEdit.edited_at, LedgerManualEdit.id)
    )).scalars().all())


def _first_edit(log: list[LedgerManualEdit]) -> LedgerManualEdit | None:
    return next((e for e in log if e.action == ACTION_EDIT), None)


async def restore(db: AsyncSession, project_id: UUID, year: int, table: str, row_id: UUID, user_id: UUID) -> None:
    """恢复导入原值：取该行第一次人工修改前的值写回。没改过返回 404。"""
    log = await _row_log(db, table, row_id)
    first = _first_edit(log)
    if first is None or first.project_id != project_id:
        raise HTTPException(status_code=404, detail="该行没有人工修改")
    original = first.before or {}
    if table == TABLE_BALANCE:
        await _apply_balance(db, project_id, year, row_id, original, ACTION_RESTORE, user_id, "恢复导入原值")
        return
    row = await _ledger_row(db, project_id, year, row_id)
    target = {f: original.get(f) for f in LEDGER_FIELDS if f in original}
    if target.get("voucher_date"):
        target["voucher_date"] = dt.date.fromisoformat(str(target["voucher_date"])[:10])
    for f in ("debit_amount", "credit_amount"):
        if target.get(f) is not None:
            target[f] = Decimal(str(target[f]))
    await _apply_ledger(db, project_id, year, row, target, ACTION_RESTORE, user_id, "恢复导入原值")


async def list_edits(db: AsyncSession, project_id: UUID, year: int, table: str) -> list[dict]:
    """当前数据集里人工改过（最后一次是修改、不是恢复）的行：修改人、时间、导入原值。上级同步的行不列。"""
    dataset_id = await get_active_dataset_id_or_none(db, project_id, year)
    q = sa.select(LedgerManualEdit).where(
        LedgerManualEdit.project_id == project_id,
        LedgerManualEdit.year == year,
        LedgerManualEdit.table_name == table,
        LedgerManualEdit.action != ACTION_CASCADE,
    ).order_by(LedgerManualEdit.edited_at, LedgerManualEdit.id)
    if dataset_id is not None:
        q = q.where(LedgerManualEdit.dataset_id == dataset_id)
    by_row: dict[UUID, dict] = {}
    for e in (await db.execute(q)).scalars().all():
        item = by_row.setdefault(e.row_id, {"row_id": str(e.row_id), "original": e.before, "count": 0})
        item.update(last_action=e.action, edited_by=str(e.edited_by) if e.edited_by else None,
                    edited_at=e.edited_at.isoformat() if e.edited_at else None, reason=e.reason)
        if e.action == ACTION_EDIT:
            item["count"] += 1
    return [{k: v for k, v in item.items() if k != "last_action"} for item in by_row.values() if item["last_action"] == ACTION_EDIT]


async def summary(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """当前数据集里改过的行数（数据导入页提示：重新导入后这些修改不会保留）。"""
    return {t: len(await list_edits(db, project_id, year, t)) for t in (TABLE_BALANCE, TABLE_LEDGER)}
