"""预审样本存续核对（spec voucher-identity-writeback-and-audit-phase 任务 17，需求 8，ADR-VK-11）。

逐条判定严格按 design §7 的顺序：

1. 分录指纹在当前 active 账套命中 → unchanged；
2. 原凭证键仍在、但分录指纹不在 → modified（分录已改）；
3. 原凭证键已不在，但同日期、科目、借贷栏、金额存在于其他凭证 → renumbered（疑似重编号）；
4. 否则 → deleted（凭证已删除）。

第三步不能放到第四步后，也不能只按凭证号找；账套重导会换行 id，所以第一步复用 ``resolve_line_fps``。
逐行结果写回宿主行元数据 ``_gt.sv``；本服务只 upsert ``interim_survival_checks`` 汇总，供项目抽样概览查询。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_phase_models import InterimSurvivalCheck
from app.models.audit_platform_models import TbLedger
from app.services.dataset_query import get_active_filter
from app.services.dataset_service import DatasetService
from app.services.voucher_identity import (
    LineFingerprint,
    VoucherKey,
    amount_str,
    describe_line,
    resolve_line_fps,
    voucher_key_sql,
    voucher_keys_in,
)

STATUSES = ("unchanged", "modified", "renumbered", "deleted")
MAX_ROWS = 2000
CANDIDATE_LIMIT = 5
CURRENT_LINE_LIMIT = 20
_CANDIDATE_CHUNK = 250


def _problem(code: str, message: str, status: int = 422) -> HTTPException:
    return HTTPException(status_code=status, detail={"error_code": code, "message": message})


def _parse_row(raw: dict[str, Any], year: int) -> dict[str, Any]:
    """校验客户端行元数据；科目 / 借贷栏 / 金额须与 lfp 内嵌值一致，避免同一状态两种口径。"""
    key = str(raw.get("row_key") or raw.get("lfp") or "")
    lfp_text, vk_text = str(raw.get("lfp") or ""), str(raw.get("vk") or "")
    try:
        fp, vk = LineFingerprint.parse(lfp_text), VoucherKey.from_str(vk_text)
        fp.vk.date_value
        vk.date_value
    except ValueError as exc:
        raise _problem("INVALID_SURVIVAL_ROW", f"预审样本元数据损坏，无法核对：{key[:80]}") from exc
    if fp.vk != vk:
        raise _problem("SURVIVAL_IDENTITY_MISMATCH", "分录指纹与凭证键不是同一张凭证，已拒绝核对")
    if fp.vk.year != str(year):
        raise _problem("SURVIVAL_YEAR_MISMATCH", f"预审样本年度 {fp.vk.year} 与请求年度 {year} 不一致")
    try:
        supplied = (str(raw.get("account_code") or ""), str(raw.get("side") or ""), amount_str(raw.get("amount")))
    except ValueError as exc:
        raise _problem("INVALID_SURVIVAL_ROW", "预审样本金额无法解析，已拒绝核对") from exc
    embedded = (fp.account_code, fp.side, fp.amount)
    if supplied != embedded:
        raise _problem("SURVIVAL_LINE_MISMATCH", "科目、借贷栏或金额与分录指纹不一致，已拒绝核对")
    return {
        "row_key": key,
        "lfp": lfp_text,
        "fp": fp,
        "previous_dataset_id": str(raw.get("previous_dataset_id") or ""),
        "previous_status": str(raw.get("previous_status") or ""),
        "acknowledged": bool(raw.get("acknowledged")),
    }


def _line_view(row: Any) -> dict[str, Any]:
    vk, account, side, amount = describe_line(row)
    return {
        "voucher_key": vk.to_str(),
        "voucher_date": vk.voucher_date,
        "voucher_type": vk.voucher_type,
        "voucher_no": vk.voucher_no,
        "company_code": vk.company_code,
        "account_code": account,
        "side": side,
        "amount": amount,
        "summary": str(row.summary or ""),
    }


async def _current_rows(
    db: AsyncSession, *, project_id: UUID, year: int, dataset_id: UUID, keys: Iterable[VoucherKey]
) -> list[Any]:
    keys = list(keys)
    if not keys:
        return []
    tbl = TbLedger.__table__
    active = await get_active_filter(db, tbl, project_id, year, force_dataset_id=dataset_id, strict=True)
    return list((await db.execute(
        sa.select(
            tbl.c.id, tbl.c.year, tbl.c.company_code, tbl.c.voucher_date, tbl.c.voucher_type,
            tbl.c.voucher_no, tbl.c.account_code, tbl.c.debit_amount, tbl.c.credit_amount, tbl.c.summary,
        ).where(active, voucher_keys_in(tbl, keys))
    )).all())


async def _renumber_candidates(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    dataset_id: UUID,
    missing: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str], list[VoucherKey]]:
    """第三步：同日期 + 科目 + 借贷栏 + 金额找其他凭证键；每个条件最多返回 5 个稳定排序候选。"""
    tbl = TbLedger.__table__
    active = await get_active_filter(db, tbl, project_id, year, force_dataset_id=dataset_id, strict=True)
    probes = sorted({(r["fp"].vk.date_value, r["fp"].account_code) for r in missing})
    found: dict[tuple[str, str, str, str], set[VoucherKey]] = defaultdict(set)
    for start in range(0, len(probes), _CANDIDATE_CHUNK):
        chunk = probes[start : start + _CANDIDATE_CHUNK]
        rows = (await db.execute(sa.select(
            tbl.c.year, tbl.c.company_code, tbl.c.voucher_date, tbl.c.voucher_type, tbl.c.voucher_no,
            tbl.c.account_code, tbl.c.debit_amount, tbl.c.credit_amount, tbl.c.summary,
        ).where(active, sa.tuple_(tbl.c.voucher_date, tbl.c.account_code).in_(chunk)))).all()
        for row in rows:
            vk, account, side, amount = describe_line(row)
            found[(vk.voucher_date, account, side, amount)].add(vk)
    return {k: sorted(v, key=VoucherKey.parts)[:CANDIDATE_LIMIT] for k, v in found.items()}


async def _upsert_summary(db: AsyncSession, values: dict[str, Any]) -> UUID:
    dialect = db.bind.dialect.name if db.bind is not None else ""
    table = InterimSurvivalCheck.__table__
    update = {k: values[k] for k in (
        "project_id", "total", "unchanged", "changed", "deleted", "renumbered", "unacked", "checked_by", "checked_at"
    )}
    if dialect == "postgresql":
        stmt = pg_insert(table).values(**values).on_conflict_do_update(
            index_elements=[table.c.working_paper_id, table.c.dataset_id], set_=update,
        ).returning(table.c.id)
        return (await db.execute(stmt)).scalar_one()
    if dialect == "sqlite":
        stmt = sqlite_insert(table).values(**values).on_conflict_do_update(
            index_elements=[table.c.working_paper_id, table.c.dataset_id], set_=update,
        ).returning(table.c.id)
        return (await db.execute(stmt)).scalar_one()
    existing = (await db.execute(sa.select(InterimSurvivalCheck).where(
        InterimSurvivalCheck.working_paper_id == values["working_paper_id"],
        InterimSurvivalCheck.dataset_id == values["dataset_id"],
    ))).scalar_one_or_none()
    if existing is None:
        existing = InterimSurvivalCheck(**values)
        db.add(existing)
    else:
        for key, value in update.items():
            setattr(existing, key, value)
    await db.flush()
    return existing.id


async def check_interim_survival(
    db: AsyncSession,
    *,
    project_id: UUID,
    workpaper_id: UUID,
    year: int,
    rows: list[dict[str, Any]],
    checked_by: UUID,
) -> dict[str, Any]:
    if not rows:
        raise _problem("SURVIVAL_ROWS_REQUIRED", "没有可核对的预审分录")
    if len(rows) > MAX_ROWS:
        raise _problem("TOO_MANY_SURVIVAL_ROWS", f"一次最多核对 {MAX_ROWS} 条预审分录")
    parsed = [_parse_row(r, year) for r in rows]
    # 同一源分录按 lfp 核对一次：一对多展开的几行共用一个 lfp，不能重复计数。
    unique: dict[str, dict[str, Any]] = {}
    for row in parsed:
        unique.setdefault(row["lfp"], row)
    parsed = list(unique.values())

    dataset_id = await DatasetService.get_active_dataset_id(db, project_id, year)
    if dataset_id is None:
        raise _problem("ACTIVE_LEDGER_DATASET_REQUIRED", "本项目该年度没有已激活账套，无法核对预审样本", 409)
    resolved = await resolve_line_fps(
        db, project_id=project_id, year=year, fps=[r["lfp"] for r in parsed], force_dataset_id=dataset_id,
    )
    unresolved = [r for r in parsed if r["lfp"] not in resolved]
    current = await _current_rows(
        db, project_id=project_id, year=year, dataset_id=dataset_id,
        keys={r["fp"].vk for r in unresolved},
    )
    by_key: dict[VoucherKey, list[Any]] = defaultdict(list)
    for row in current:
        by_key[VoucherKey.from_row(row)].append(row)
    no_voucher = [r for r in unresolved if r["fp"].vk not in by_key]
    candidates = await _renumber_candidates(
        db, project_id=project_id, year=year, dataset_id=dataset_id, missing=no_voucher,
    )

    results: list[dict[str, Any]] = []
    counts = {s: 0 for s in STATUSES}
    unacked = 0
    for item in parsed:
        fp: LineFingerprint = item["fp"]
        if item["lfp"] in resolved:
            status, detail = "unchanged", {"current_line_id": str(resolved[item["lfp"]])}
        elif fp.vk in by_key:
            lines = by_key[fp.vk]
            status, detail = "modified", {
                "current_voucher": {
                    "voucher_key": fp.vk.to_str(),
                    "line_count": len(lines),
                    "lines": [_line_view(r) for r in lines[:CURRENT_LINE_LIMIT]],
                    "truncated": len(lines) > CURRENT_LINE_LIMIT,
                }
            }
        else:
            probe = (fp.vk.voucher_date, fp.account_code, fp.side, fp.amount)
            cands = [vk for vk in candidates.get(probe, []) if vk != fp.vk]
            if cands:
                status, detail = "renumbered", {"candidates": [{
                    "voucher_key": vk.to_str(), "voucher_date": vk.voucher_date,
                    "voucher_type": vk.voucher_type, "voucher_no": vk.voucher_no, "company_code": vk.company_code,
                } for vk in cands]}
            else:
                status, detail = "deleted", {}
        counts[status] += 1
        preserved_ack = (
            status != "unchanged" and item["acknowledged"]
            and item["previous_dataset_id"] == str(dataset_id) and item["previous_status"] == status
        )
        if status != "unchanged" and not preserved_ack:
            unacked += 1
        results.append({
            "row_key": item["row_key"], "lfp": item["lfp"], "status": status,
            "acknowledged": preserved_ack, **detail,
        })

    checked_at = datetime.now(timezone.utc)
    check_id = await _upsert_summary(db, {
        "project_id": project_id,
        "working_paper_id": workpaper_id,
        "dataset_id": dataset_id,
        "total": len(parsed),
        "unchanged": counts["unchanged"],
        "changed": counts["modified"],
        "deleted": counts["deleted"],
        "renumbered": counts["renumbered"],
        "unacked": unacked,
        "checked_by": checked_by,
        "checked_at": checked_at,
    })
    await db.flush()
    return {
        "check_id": str(check_id), "dataset_id": str(dataset_id), "year": year,
        "total": len(parsed), **counts, "unacked": unacked,
        "checked_by": str(checked_by), "checked_at": checked_at.isoformat(), "results": results,
    }


async def survival_status(
    db: AsyncSession, *, project_id: UUID, workpaper_id: UUID, year: int,
) -> dict[str, Any]:
    dataset_id = await DatasetService.get_active_dataset_id(db, project_id, year)
    if dataset_id is None:
        return {"year": year, "active_dataset_id": None, "check": None}
    row = (await db.execute(sa.select(InterimSurvivalCheck).where(
        InterimSurvivalCheck.project_id == project_id,
        InterimSurvivalCheck.working_paper_id == workpaper_id,
        InterimSurvivalCheck.dataset_id == dataset_id,
    ))).scalar_one_or_none()
    check = None if row is None else {
        "check_id": str(row.id), "dataset_id": str(row.dataset_id), "total": row.total,
        "unchanged": row.unchanged, "modified": row.changed, "deleted": row.deleted,
        "renumbered": row.renumbered, "unacked": row.unacked,
        "checked_by": str(row.checked_by) if row.checked_by else None,
        "checked_at": row.checked_at.isoformat() if row.checked_at else None,
    }
    return {"year": year, "active_dataset_id": str(dataset_id), "check": check}


async def set_unacked(
    db: AsyncSession,
    *,
    project_id: UUID,
    workpaper_id: UUID,
    dataset_id: UUID,
    check_id: UUID,
    unacked: int,
    actor_id: UUID,
) -> dict[str, Any]:
    # 先取汇总，再校它的数据集仍是 active（避免把旧版本确认写到当前概览）。
    row = (await db.execute(sa.select(InterimSurvivalCheck).where(
        InterimSurvivalCheck.id == check_id,
        InterimSurvivalCheck.project_id == project_id,
        InterimSurvivalCheck.working_paper_id == workpaper_id,
        InterimSurvivalCheck.dataset_id == dataset_id,
    ))).scalar_one_or_none()
    if row is None:
        raise _problem("SURVIVAL_CHECK_NOT_FOUND", "存续核对记录不存在或不属于该底稿", 404)
    from app.models.dataset_models import DatasetStatus, LedgerDataset
    is_active = (await db.execute(sa.select(sa.func.count()).select_from(LedgerDataset).where(
        LedgerDataset.id == dataset_id, LedgerDataset.project_id == project_id, LedgerDataset.status == DatasetStatus.active,
    ))).scalar_one()
    if not is_active:
        raise _problem("SURVIVAL_DATASET_STALE", "账套版本已变化，请重新核对预审样本", 409)
    affected = row.changed + row.deleted + row.renumbered
    if unacked < 0 or unacked > affected:
        raise _problem("INVALID_UNACKED_COUNT", f"未确认数须在 0 至 {affected} 之间")
    row.unacked = unacked
    await db.flush()
    now = datetime.now(timezone.utc)
    return {"check_id": str(row.id), "dataset_id": str(row.dataset_id), "unacked": row.unacked,
            "ack_by": str(actor_id), "ack_at": now.isoformat()}
