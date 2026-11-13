#!/usr/bin/env python
"""修复 sampled_vouchers 旧身份债：补全缺失的 voucher_date / company_code / voucher_type。

spec: voucher-runtime-integrity-and-visibility-closure  任务 10（R6）

用法：
  # 干跑（默认）——只输出报告不改库
  python backend/scripts/fix/fix_sampled_voucher_legacy_identity.py

  # 只看指定项目
  python backend/scripts/fix/fix_sampled_voucher_legacy_identity.py --project-id <uuid>

  # 真正写库（会要求 y/n 确认）
  python backend/scripts/fix/fix_sampled_voucher_legacy_identity.py --apply

输出 JSON 报告到 stdout（--output <path> 写文件）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from uuid import UUID

# ── 让 backend 包可 import ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]          # backend/
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa                             # noqa: E402
from sqlalchemy.ext.asyncio import (                # noqa: E402
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker             # noqa: E402

from app.core.config import settings                # noqa: E402
from app.models.audit_platform_models import TbLedger, WorkpaperExtractionLog  # noqa: E402
from app.models.workpaper_models import SampledVoucher  # noqa: E402
from app.services.dataset_query import get_active_filter  # noqa: E402

logger = logging.getLogger(__name__)


# ── 查询 ───────────────────────────────────────────────────────────────

async def _find_legacy_rows(db: AsyncSession, project_id: UUID | None) -> list:
    """找 voucher_date / company_code / voucher_type 任一为 NULL 且未软删的行。"""
    conds = [
        SampledVoucher.is_deleted == sa.false(),
        sa.or_(
            SampledVoucher.voucher_date.is_(None),
            SampledVoucher.company_code.is_(None),
            SampledVoucher.voucher_type.is_(None),
        ),
    ]
    if project_id is not None:
        conds.append(SampledVoucher.project_id == project_id)
    return (await db.execute(
        sa.select(SampledVoucher).where(*conds).order_by(SampledVoucher.project_id, SampledVoucher.year)
    )).scalars().all()


def _candidate(r) -> dict:
    out = {
        "voucher_date": r.voucher_date.isoformat() if r.voucher_date else None,
        "company_code": r.company_code,
        "voucher_type": r.voucher_type,
    }
    accounts = getattr(r, "accounts", None)
    if accounts is not None:
        out["accounts"] = sorted(set(accounts))
    return out


async def _resolve_engine_row(db: AsyncSession, row: SampledVoucher) -> list[dict] | None:
    """抽凭引擎登记：按批次回填日志的 ``filled_unit_ids``（被抽中的分录 id）回查分录，定出确切的凭证与分录科目。

    引擎旧登记的 ``account_code`` 是筛选条件的第一个科目，不是分录科目（共享库 30 行登记 1001、分录实为 1002），
    不能拿来当条件。日志没有分录 id 或一条都查不到时返回 None，由调用方退回按账套查。
    """
    log = (await db.execute(
        sa.select(WorkpaperExtractionLog.extraction_criteria)
        .where(WorkpaperExtractionLog.batch_id == row.batch_id, WorkpaperExtractionLog.project_id == row.project_id)
        .order_by(WorkpaperExtractionLog.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    criteria = log if isinstance(log, dict) else {}
    ids = []
    for value in criteria.get("filled_unit_ids") or []:
        try:
            ids.append(UUID(str(value)))
        except (ValueError, TypeError):
            continue
    if not ids:
        return None
    tbl = TbLedger.__table__
    rows = (await db.execute(
        sa.select(
            tbl.c.voucher_date, tbl.c.company_code, tbl.c.voucher_type,
            sa.func.array_agg(sa.distinct(tbl.c.account_code)).label("accounts"),
        )
        .where(tbl.c.id.in_(ids), tbl.c.project_id == row.project_id, tbl.c.voucher_no == row.voucher_no)
        .group_by(tbl.c.voucher_date, tbl.c.company_code, tbl.c.voucher_type)
    )).all()
    return [_candidate(r) for r in rows] or None


async def _resolve_from_ledger(db: AsyncSession, row: SampledVoucher) -> list[dict]:
    """在 active 账套中查这条登记可能指的凭证（按日期 + 主体 + 凭证字去重）。

    行上已记的凭证键列（日期 / 主体 / 凭证字）都作为条件；手工挂凭的登记科目是挂凭意图科目（用户所在行的科目），
    这张凭证一定有该科目的分录，也作为条件。引擎登记的科目不可靠（见 ``_resolve_engine_row``），不用。
    只按凭证号查会把同号的几十张凭证都算成候选（单号最多对应 83 个日期）。
    查询失败抛出，由调用方记 ``resolve_error``，不当成「账套里没有」。
    """
    tbl = TbLedger.__table__
    active_filter = await get_active_filter(db, tbl, row.project_id, row.year)
    conds = [active_filter, tbl.c.voucher_no == row.voucher_no]
    if row.voucher_date is not None:
        conds.append(tbl.c.voucher_date == row.voucher_date)
    if row.company_code is not None:
        conds.append(tbl.c.company_code == row.company_code)
    if row.voucher_type is not None:
        conds.append(tbl.c.voucher_type == row.voucher_type)
    if row.batch_id is None and row.account_code:
        conds.append(tbl.c.account_code.like(f"{row.account_code}%"))
    rows = (await db.execute(
        sa.select(
            tbl.c.voucher_date, tbl.c.company_code, tbl.c.voucher_type,
        )
        .where(*conds)
        .group_by(tbl.c.voucher_date, tbl.c.company_code, tbl.c.voucher_type)
    )).all()
    return [_candidate(r) for r in rows]


# ── 主逻辑 ─────────────────────────────────────────────────────────────

async def run(*, apply: bool, project_id: UUID | None) -> dict:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    results: list[dict] = []
    counts = {"auto_resolve": 0, "ambiguous": 0, "no_match": 0, "legacy_orphan": 0, "resolve_error": 0, "total": 0}

    async with async_session() as db:
        rows = await _find_legacy_rows(db, project_id)
        counts["total"] = len(rows)

        for row in rows:
            entry: dict = {
                "id": str(row.id),
                "project_id": str(row.project_id),
                "year": row.year,
                "voucher_no": row.voucher_no,
                "source": "sampling_engine" if row.batch_id else "manual",
                "account_code": row.account_code,
                "before": {
                    "voucher_date": row.voucher_date.isoformat() if row.voucher_date else None,
                    "company_code": row.company_code,
                    "voucher_type": row.voucher_type,
                    "working_paper_id": str(row.working_paper_id) if row.working_paper_id else None,
                },
            }

            # 孤儿检测
            if row.working_paper_id is None:
                entry["status"] = "legacy_orphan"
                entry["action"] = "标记 note"
                counts["legacy_orphan"] += 1
                if apply:
                    existing_note = row.note or ""
                    if "legacy_orphan" not in existing_note:
                        row.note = (existing_note + " [legacy_orphan]").strip()
                results.append(entry)
                continue

            # 引擎登记先按回填分录 id 定位；其余（及日志里没有分录 id 的）在账套中查候选。
            # 查询失败如实记下，不当成「账套里没有」
            try:
                async with db.begin_nested():
                    candidates = await _resolve_engine_row(db, row) if row.batch_id is not None else None
                    entry["basis"] = "filled_unit_ids" if candidates is not None else "active_ledger"
                    if candidates is None:
                        candidates = await _resolve_from_ledger(db, row)
            except Exception as exc:  # noqa: BLE001 —— 保存点已回滚，继续下一行
                entry["status"] = "resolve_error"
                entry["action"] = f"查询账套失败：{type(exc).__name__}：{str(exc)[:200]}"
                counts["resolve_error"] += 1
                results.append(entry)
                continue

            if len(candidates) == 1:
                c = candidates[0]
                entry["status"] = "auto_resolve"
                entry["after"] = c
                accounts = c.get("accounts") or []
                # 引擎登记的科目改成被抽中分录的科目（只有一个时）；手工挂凭的科目是用户选的，不动
                fixed_account = accounts[0] if row.batch_id is not None and len(accounts) == 1 else None
                if fixed_account is not None and fixed_account != row.account_code:
                    entry["account_fix"] = {"before": row.account_code, "after": fixed_account}
                counts["auto_resolve"] += 1
                if apply:
                    if c["voucher_date"] and row.voucher_date is None:
                        from datetime import date as _date
                        row.voucher_date = _date.fromisoformat(c["voucher_date"])
                    if c["company_code"] is not None and row.company_code is None:
                        row.company_code = c["company_code"]
                    if c["voucher_type"] is not None and row.voucher_type is None:
                        row.voucher_type = c["voucher_type"]
                    if fixed_account is not None:
                        row.account_code = fixed_account
            elif len(candidates) == 0:
                entry["status"] = "no_match"
                entry["action"] = "账套无此凭证号（可能已重导）"
                counts["no_match"] += 1
            else:
                entry["status"] = "ambiguous"
                entry["candidates"] = candidates
                entry["action"] = f"命中 {len(candidates)} 张凭证，需人工确认"
                counts["ambiguous"] += 1

            results.append(entry)

        if apply:
            await db.commit()

    await engine.dispose()
    return {"counts": counts, "results": results, "applied": apply}


# ── CLI ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="修复 sampled_vouchers 旧身份债")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run）")
    parser.add_argument("--project-id", type=str, default=None, help="只治理指定项目")
    parser.add_argument("--output", type=str, default=None, help="报告输出文件（默认 stdout）")
    args = parser.parse_args()

    pid = UUID(args.project_id) if args.project_id else None

    if args.apply:
        confirm = input("⚠️  即将修改 sampled_vouchers 表，确认？(y/n): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

    report = asyncio.run(run(apply=args.apply, project_id=pid))

    out = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"报告已写入 {args.output}")
    else:
        print(out)

    c = report["counts"]
    print(
        f"\n{'[已执行]' if args.apply else '[干跑]'} "
        f"共 {c['total']} 行：自动补全 {c['auto_resolve']} / "
        f"歧义 {c['ambiguous']} / 无匹配 {c['no_match']} / 孤儿 {c['legacy_orphan']} / 查询失败 {c['resolve_error']}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
