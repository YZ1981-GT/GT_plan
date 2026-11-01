"""调整分录“客户已入账”唯一判定、标记、撤销与重算。

一组 AJE 只有在最新动作是 book、标记数据集不晚于当前 active 数据集，且所选
VoucherKey 全部仍存在于当前 active 序时账时才生效。所有计算读取方复用本模块。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adjustment_review_models import AdjustmentClientBooking
from app.models.audit_platform_models import Adjustment, AdjustmentType, ReviewStatus, TbLedger
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.dataset_models import LedgerDataset
from app.services.dataset_service import DatasetService
from app.services.voucher_identity import VoucherKey, parse_voucher_keys, voucher_keys_in
from app.services.workpaper_sync.outbox import DurableEventOutboxService


class AdjustmentClientBookingError(ValueError):
    def __init__(self, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class BookingProjection:
    status: str
    effective: bool
    voucher_keys: tuple[str, ...]
    booked_dataset_id: UUID | None
    created_by: UUID | None
    created_at: Any = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "effective": self.effective,
            "voucher_keys": list(self.voucher_keys),
            "booked_dataset_id": str(self.booked_dataset_id) if self.booked_dataset_id else None,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "note": self.note,
        }


async def _latest_records(
    db: AsyncSession, project_id: UUID, year: int, group_ids: Iterable[UUID] | None = None,
) -> dict[UUID, AdjustmentClientBooking]:
    stmt = sa.select(AdjustmentClientBooking).where(
        AdjustmentClientBooking.project_id == project_id,
        AdjustmentClientBooking.year == year,
    )
    ids = list(group_ids or [])
    if ids:
        stmt = stmt.where(AdjustmentClientBooking.entry_group_id.in_(ids))
    stmt = stmt.order_by(
        AdjustmentClientBooking.entry_group_id,
        AdjustmentClientBooking.sequence.desc(),
        AdjustmentClientBooking.created_at.desc(),
        AdjustmentClientBooking.id.desc(),
    )
    latest: dict[UUID, AdjustmentClientBooking] = {}
    for row in (await db.execute(stmt)).scalars().all():
        latest.setdefault(row.entry_group_id, row)
    return latest


async def _active_dataset(
    db: AsyncSession, project_id: UUID, year: int,
) -> LedgerDataset | None:
    active_id = await DatasetService.get_active_dataset_id(db, project_id, year)
    if active_id is None:
        return None
    return (await db.execute(sa.select(LedgerDataset).where(
        LedgerDataset.id == active_id,
        LedgerDataset.project_id == project_id,
        LedgerDataset.year == year,
    ))).scalar_one_or_none()


async def _voucher_keys_present(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    dataset_id: UUID,
    keys: list[VoucherKey],
) -> set[VoucherKey]:
    if not keys:
        return set()
    tbl = TbLedger.__table__
    rows = (await db.execute(sa.select(
        tbl.c.year, tbl.c.company_code, tbl.c.voucher_date, tbl.c.voucher_type, tbl.c.voucher_no,
    ).where(
        tbl.c.project_id == project_id,
        tbl.c.year == year,
        tbl.c.dataset_id == dataset_id,
        tbl.c.is_deleted == sa.false(),
        voucher_keys_in(tbl, keys),
    ).distinct())).mappings().all()
    return {VoucherKey.from_row(row) for row in rows}


async def effective_booked_group_ids(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    group_ids: Iterable[UUID] | None = None,
) -> set[UUID]:
    """当前 active 账套下真正生效的客户已入账分录组。"""
    latest = await _latest_records(db, project_id, year, group_ids)
    # 没有任何标记时无需触碰账套大表。这既缩短绝大多数调整重算路径，也让
    # 尚未启用“客户已入账”的项目不依赖账套生命周期表。
    if not latest:
        return set()
    active = await _active_dataset(db, project_id, year)
    if active is None:
        return set()
    candidates: dict[UUID, tuple[AdjustmentClientBooking, list[VoucherKey]]] = {}
    all_keys: dict[VoucherKey, None] = {}
    for group_id, row in latest.items():
        if row.action != "book" or row.booked_dataset_id is None:
            continue
        booked_dataset = (await db.execute(sa.select(LedgerDataset).where(
            LedgerDataset.id == row.booked_dataset_id,
            LedgerDataset.project_id == project_id,
            LedgerDataset.year == year,
        ))).scalar_one_or_none()
        if booked_dataset is None or booked_dataset.created_at > active.created_at:
            continue
        keys = parse_voucher_keys(row.voucher_keys or [])
        if not keys or len(keys) != len(set(row.voucher_keys or [])):
            continue
        candidates[group_id] = (row, keys)
        for key in keys:
            all_keys[key] = None
    present = await _voucher_keys_present(
        db, project_id=project_id, year=year, dataset_id=active.id, keys=list(all_keys),
    )
    return {
        group_id for group_id, (_row, keys) in candidates.items()
        if set(keys) <= present
    }


async def effective_booked_groups_clause(
    db: AsyncSession,
    adjustment_table: Any,
    *,
    project_id: UUID,
    year: int,
) -> sa.ColumnElement:
    """计算读取方共用的“排除已入账组”SQL 条件。"""
    c = adjustment_table.c if hasattr(adjustment_table, "c") else adjustment_table.__table__.c
    group_ids = await effective_booked_group_ids(db, project_id=project_id, year=year)
    return c.entry_group_id.notin_(sorted(group_ids, key=str)) if group_ids else sa.true()


async def booking_projection(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    group_ids: Iterable[UUID],
) -> dict[str, BookingProjection]:
    ids = list(group_ids)
    latest = await _latest_records(db, project_id, year, ids)
    effective = await effective_booked_group_ids(
        db, project_id=project_id, year=year, group_ids=ids,
    )
    out: dict[str, BookingProjection] = {}
    for group_id, row in latest.items():
        out[str(group_id)] = BookingProjection(
            status="booked" if row.action == "book" else "revoked",
            effective=group_id in effective,
            voucher_keys=tuple(str(value) for value in row.voucher_keys or []),
            booked_dataset_id=row.booked_dataset_id,
            created_by=row.created_by,
            created_at=row.created_at,
            note=row.note,
        )
    return out


async def _next_sequence(db: AsyncSession, project_id: UUID, entry_group_id: UUID) -> int:
    value = (await db.execute(sa.select(sa.func.max(AdjustmentClientBooking.sequence)).where(
        AdjustmentClientBooking.project_id == project_id,
        AdjustmentClientBooking.entry_group_id == entry_group_id,
    ))).scalar_one_or_none()
    return int(value or 0) + 1


async def mark_booked(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    entry_group_id: UUID,
    voucher_key_values: list[str],
    actor_id: UUID,
    note: str | None = None,
) -> AdjustmentClientBooking:
    rows = list((await db.execute(sa.select(Adjustment).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.entry_group_id == entry_group_id,
        Adjustment.is_deleted == sa.false(),
    ).with_for_update())).scalars().all())
    if not rows:
        raise AdjustmentClientBookingError("GROUP_NOT_FOUND", "调整分录不存在或已删除")
    if {row.adjustment_type for row in rows} != {AdjustmentType.aje}:
        raise AdjustmentClientBookingError("AJE_REQUIRED", "只有审计调整 AJE 可以标记客户已入账")
    if {row.review_status for row in rows} != {ReviewStatus.approved}:
        raise AdjustmentClientBookingError("APPROVED_REQUIRED", "只有已批准的 AJE 可以标记客户已入账")
    keys = parse_voucher_keys(voucher_key_values)
    if not keys or len(keys) != len(set(voucher_key_values)):
        raise AdjustmentClientBookingError("VOUCHER_KEY_REQUIRED", "请至少选择一张有效且不重复的客户入账凭证")
    if any(key.year != str(year) for key in keys):
        raise AdjustmentClientBookingError("VOUCHER_YEAR_MISMATCH", "入账凭证年度与调整分录年度不一致")
    active = await _active_dataset(db, project_id, year)
    if active is None:
        raise AdjustmentClientBookingError("ACTIVE_DATASET_REQUIRED", "当前项目年度没有已激活账套，无法标记客户已入账")
    present = await _voucher_keys_present(
        db, project_id=project_id, year=year, dataset_id=active.id, keys=keys,
    )
    missing = [key.to_str() for key in keys if key not in present]
    if missing:
        raise AdjustmentClientBookingError(
            "VOUCHERS_NOT_IN_ACTIVE_DATASET",
            "所选凭证不在当前已激活账套中",
            {"missing_voucher_keys": missing},
        )
    canonical = [key.to_str() for key in keys]
    latest = (await _latest_records(db, project_id, year, [entry_group_id])).get(entry_group_id)
    if latest and latest.action == "book" and latest.booked_dataset_id == active.id and latest.voucher_keys == canonical:
        return latest
    record = AdjustmentClientBooking(
        project_id=project_id,
        year=year,
        entry_group_id=entry_group_id,
        action="book",
        sequence=await _next_sequence(db, project_id, entry_group_id),
        voucher_keys=canonical,
        booked_dataset_id=active.id,
        note=(note or "").strip() or None,
        created_by=actor_id,
    )
    db.add(record)
    await db.flush()
    return record


async def revoke_booking(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    entry_group_id: UUID,
    actor_id: UUID,
    reason: str,
) -> AdjustmentClientBooking:
    reason = (reason or "").strip()
    if not reason:
        raise AdjustmentClientBookingError("REVOKE_REASON_REQUIRED", "撤销客户已入账标记必须填写原因")
    lock_stmt = sa.select(Adjustment.id).where(
        Adjustment.project_id == project_id,
        Adjustment.entry_group_id == entry_group_id,
        Adjustment.is_deleted == sa.false(),
    )
    if db.get_bind() is not None and db.get_bind().dialect.name == "postgresql":
        lock_stmt = lock_stmt.with_for_update()
    if not (await db.execute(lock_stmt)).first():
        raise AdjustmentClientBookingError("GROUP_NOT_FOUND", "调整分录不存在或已删除")
    latest = (await _latest_records(db, project_id, year, [entry_group_id])).get(entry_group_id)
    if latest is None or latest.action != "book":
        raise AdjustmentClientBookingError("BOOKING_NOT_ACTIVE", "该调整分录当前没有可撤销的客户已入账标记")
    record = AdjustmentClientBooking(
        project_id=project_id,
        year=year,
        entry_group_id=entry_group_id,
        action="revoke",
        sequence=await _next_sequence(db, project_id, entry_group_id),
        voucher_keys=list(latest.voucher_keys or []),
        booked_dataset_id=latest.booked_dataset_id,
        note=reason,
        created_by=actor_id,
    )
    db.add(record)
    await db.flush()
    return record


async def apply_booking_change(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    entry_group_id: UUID,
    actor_id: UUID,
    action: str,
) -> dict[str, Any]:
    """标记/撤销后同事务重算 TB，并登记耐久下游事件。"""
    rows = list((await db.execute(sa.select(Adjustment).where(
        Adjustment.project_id == project_id,
        Adjustment.entry_group_id == entry_group_id,
        Adjustment.is_deleted == sa.false(),
    ))).scalars().all())
    if not rows:
        raise AdjustmentClientBookingError("GROUP_NOT_FOUND", "调整分录不存在或已删除")
    account_codes = sorted({row.account_code for row in rows if row.account_code})
    company_codes = {row.company_code for row in rows if row.company_code}
    if len(company_codes) != 1:
        raise AdjustmentClientBookingError("COMPANY_AMBIGUOUS", "分录组所属主体不一致，无法重算试算表")
    from app.services.adjustment_review_coordinator import AdjustmentReviewCoordinator
    from app.services.trial_balance_service import TrialBalanceService

    company_code = next(iter(company_codes))
    await AdjustmentReviewCoordinator(db).ensure_tb_rows(
        project_id=project_id, year=year, company_code=company_code,
        account_codes=account_codes,
    )
    svc = TrialBalanceService(db)
    await svc.recalc_adjustments(project_id, year, company_code=company_code, account_codes=account_codes)
    await svc.recalc_audited(project_id, year, company_code=company_code, account_codes=account_codes)
    extra = {
        "trigger": "adjustment_client_booking_changed",
        "action": action,
        "operator_id": str(actor_id),
        "tb_recalc_committed": True,
    }
    await DurableEventOutboxService.enqueue_event(db, EventPayload(
        event_type=EventType.ADJUSTMENT_CLIENT_BOOKING_CHANGED,
        project_id=project_id,
        year=year,
        account_codes=account_codes,
        entry_group_id=entry_group_id,
        extra=extra,
    ))
    await DurableEventOutboxService.enqueue_event(db, EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=project_id,
        year=year,
        account_codes=account_codes,
        entry_group_id=entry_group_id,
        extra=extra,
    ))
    return {"account_codes": account_codes, "company_code": company_code}


async def booking_history(
    db: AsyncSession, *, project_id: UUID, year: int, entry_group_id: UUID,
) -> list[dict[str, Any]]:
    rows = list((await db.execute(sa.select(AdjustmentClientBooking).where(
        AdjustmentClientBooking.project_id == project_id,
        AdjustmentClientBooking.year == year,
        AdjustmentClientBooking.entry_group_id == entry_group_id,
    ).order_by(AdjustmentClientBooking.created_at.desc(), AdjustmentClientBooking.id.desc()))).scalars().all())
    return [{
        "id": str(row.id), "action": row.action,
        "voucher_keys": list(row.voucher_keys or []),
        "booked_dataset_id": str(row.booked_dataset_id) if row.booked_dataset_id else None,
        "note": row.note, "created_by": str(row.created_by),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    } for row in rows]


def _match_voucher_lines(
    adjustment_lines: list[dict[str, Any]],
    ledger_lines: list[dict[str, Any]],
    mapping: dict[str, set[str]],
) -> list[tuple[dict[str, Any], dict[str, Any]]] | None:
    """小规模二分图精确匹配；每条序时账分录最多匹配一次。"""
    from app.services.voucher_identity import amount_str, side_of, signed_amount

    candidates: list[list[int]] = []
    for adjustment in adjustment_lines:
        acceptable_codes = mapping.get(adjustment["standard_account_code"], {adjustment["standard_account_code"]})
        side = side_of(adjustment["debit_amount"], adjustment["credit_amount"])
        amount = amount_str(signed_amount(adjustment["debit_amount"], adjustment["credit_amount"], side))
        candidates.append([
            index for index, ledger in enumerate(ledger_lines)
            if ledger["account_code"] in acceptable_codes
            and side_of(ledger["debit_amount"], ledger["credit_amount"]) == side
            and amount_str(signed_amount(ledger["debit_amount"], ledger["credit_amount"], side)) == amount
        ])
    order = sorted(range(len(adjustment_lines)), key=lambda index: len(candidates[index]))
    used: set[int] = set()
    matched: dict[int, int] = {}

    def visit(position: int) -> bool:
        if position == len(order):
            return True
        adjustment_index = order[position]
        for ledger_index in candidates[adjustment_index]:
            if ledger_index in used:
                continue
            used.add(ledger_index)
            matched[adjustment_index] = ledger_index
            if visit(position + 1):
                return True
            used.remove(ledger_index)
            matched.pop(adjustment_index, None)
        return False

    if not visit(0):
        return None
    return [(adjustment_lines[index], ledger_lines[matched[index]]) for index in range(len(adjustment_lines))]


async def suggest_bookings(
    db: AsyncSession, *, project_id: UUID, year: int,
) -> list[dict[str, Any]]:
    """按科目、借贷栏和金额精确匹配当前 active 账套中的客户入账凭证。"""
    from app.models.audit_platform_models import AccountMapping, AdjustmentEntry
    from app.services.voucher_identity import VoucherKey, group_by_voucher_key, voucher_label

    active = await _active_dataset(db, project_id, year)
    if active is None:
        return []
    already = await _latest_records(db, project_id, year)
    excluded = {group_id for group_id, row in already.items() if row.action == "book"}
    headers = list((await db.execute(sa.select(Adjustment).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.adjustment_type == AdjustmentType.aje,
        Adjustment.review_status == ReviewStatus.approved,
        Adjustment.is_deleted == sa.false(),
    ).order_by(Adjustment.created_at, Adjustment.entry_group_id))).scalars().all())
    groups: dict[UUID, list[Adjustment]] = {}
    for row in headers:
        if row.entry_group_id not in excluded:
            groups.setdefault(row.entry_group_id, []).append(row)
    if not groups:
        return []
    entry_rows = list((await db.execute(sa.select(AdjustmentEntry).where(
        AdjustmentEntry.entry_group_id.in_(list(groups)),
        AdjustmentEntry.is_deleted == sa.false(),
    ).order_by(AdjustmentEntry.entry_group_id, AdjustmentEntry.line_no))).scalars().all())
    entries: dict[UUID, list[dict[str, Any]]] = {}
    for row in entry_rows:
        entries.setdefault(row.entry_group_id, []).append({
            "line_no": row.line_no, "standard_account_code": row.standard_account_code,
            "account_name": row.account_name, "debit_amount": row.debit_amount,
            "credit_amount": row.credit_amount,
        })
    mappings = (await db.execute(sa.select(
        AccountMapping.standard_account_code, AccountMapping.original_account_code,
    ).where(
        AccountMapping.project_id == project_id,
        AccountMapping.is_deleted == sa.false(),
    ))).all()
    code_map: dict[str, set[str]] = {}
    for standard, original in mappings:
        code_map.setdefault(standard, set()).add(original)
    for group_lines in entries.values():
        for line in group_lines:
            code_map.setdefault(line["standard_account_code"], set()).add(line["standard_account_code"])
    account_codes = sorted({code for values in code_map.values() for code in values})
    if not account_codes:
        return []
    ledger = list((await db.execute(sa.select(TbLedger).where(
        TbLedger.project_id == project_id,
        TbLedger.year == year,
        TbLedger.dataset_id == active.id,
        TbLedger.account_code.in_(account_codes),
        TbLedger.is_deleted == sa.false(),
    ))).scalars().all())
    vouchers = group_by_voucher_key(ledger)
    results: list[dict[str, Any]] = []
    for group_id, rows in groups.items():
        adjustment_lines = entries.get(group_id, [])
        if not adjustment_lines:
            continue
        candidates = []
        for key, voucher_lines in vouchers.items():
            serialized = [{
                "id": str(row.id), "account_code": row.account_code,
                "account_name": row.account_name, "debit_amount": row.debit_amount,
                "credit_amount": row.credit_amount, "summary": row.summary,
            } for row in voucher_lines]
            matched = _match_voucher_lines(adjustment_lines, serialized, code_map)
            if matched is None:
                continue
            candidates.append({
                "voucher_key": key.to_str(), "label": voucher_label(key),
                "voucher_date": key.voucher_date, "voucher_type": key.voucher_type,
                "voucher_no": key.voucher_no, "company_code": key.company_code,
                "summary": next((line["summary"] for line in serialized if line.get("summary")), ""),
                "matches": [{
                    "adjustment_line_no": adjustment["line_no"],
                    "ledger_line_id": ledger_line["id"],
                    "account_code": ledger_line["account_code"],
                    "debit_amount": str(ledger_line["debit_amount"] or 0),
                    "credit_amount": str(ledger_line["credit_amount"] or 0),
                } for adjustment, ledger_line in matched],
                "distance_days": abs((key.date_value - rows[0].created_at.date()).days) if rows[0].created_at else 0,
            })
        if candidates:
            candidates.sort(key=lambda item: (item["distance_days"], item["voucher_date"], item["voucher_no"]))
            results.append({
                "entry_group_id": str(group_id), "adjustment_no": rows[0].adjustment_no,
                "description": rows[0].description, "audit_phase": rows[0].audit_phase,
                "candidates": candidates,
            })
    return results


async def effective_booking_impacts_for_accounts(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    account_codes: Iterable[str],
) -> list[dict[str, Any]]:
    """发布门：返回所涉科目中当前生效的客户已入账 AJE 组。"""
    effective = await effective_booked_group_ids(db, project_id=project_id, year=year)
    if not effective:
        return []
    rows = (await db.execute(sa.select(
        Adjustment.entry_group_id,
        Adjustment.adjustment_no,
        Adjustment.description,
        Adjustment.account_code,
    ).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.entry_group_id.in_(list(effective)),
        Adjustment.account_code.in_(sorted({code for code in account_codes if code})),
        Adjustment.is_deleted == sa.false(),
    ))).all()
    grouped: dict[UUID, dict[str, Any]] = {}
    for group_id, number, description, code in rows:
        item = grouped.setdefault(group_id, {
            "entry_group_id": str(group_id), "adjustment_no": number,
            "description": description, "account_codes": [],
        })
        if code not in item["account_codes"]:
            item["account_codes"].append(code)
    return list(grouped.values())
