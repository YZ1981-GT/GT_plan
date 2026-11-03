"""按凭证键比较两个账套版本；PG 聚合不把百万行明细拉到 Python。"""
from __future__ import annotations

import time
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger
from app.models.dataset_models import LedgerDataset
from app.services.voucher_identity import VoucherKey, side_of, signed_amount

_KINDS = ("added", "deleted", "modified")
_MONEY = Decimal("0.01")


def _money(value: Any) -> str:
    return str(Decimal(str(value or 0)).quantize(_MONEY, rounding=ROUND_HALF_EVEN))


def _empty_report(base_id: UUID, new_id: UUID) -> dict[str, Any]:
    return {
        "status": "ok",
        "base_dataset_id": str(base_id),
        "new_dataset_id": str(new_id),
        "summary": {kind: {"count": 0, "amount": "0.00", "net_amount_change": "0.00"} for kind in _KINDS},
        "by_month": {},
        "samples": {kind: [] for kind in _KINDS},
    }


_PG_DIFF_SQL = r"""
WITH base AS MATERIALIZED (
  SELECT year, company_code, voucher_date, COALESCE(voucher_type, '') AS voucher_type, voucher_no,
         md5(string_agg(
           account_code || '|' ||
           CASE WHEN COALESCE(debit_amount,0)<>0 AND COALESCE(credit_amount,0)=0 THEN 'D'
                WHEN COALESCE(credit_amount,0)<>0 AND COALESCE(debit_amount,0)=0 THEN 'C' ELSE 'X' END || '|' ||
           ROUND(CASE WHEN COALESCE(debit_amount,0)<>0 THEN debit_amount ELSE COALESCE(credit_amount,0) END,2)::text,
           E'\n' ORDER BY account_code,
           CASE WHEN COALESCE(debit_amount,0)<>0 AND COALESCE(credit_amount,0)=0 THEN 'D'
                WHEN COALESCE(credit_amount,0)<>0 AND COALESCE(debit_amount,0)=0 THEN 'C' ELSE 'X' END,
           ROUND(CASE WHEN COALESCE(debit_amount,0)<>0 THEN debit_amount ELSE COALESCE(credit_amount,0) END,2)::text
         )) AS signature,
         GREATEST(ABS(SUM(COALESCE(debit_amount,0))), ABS(SUM(COALESCE(credit_amount,0)))) AS amount
  FROM tb_ledger WHERE dataset_id=:base_id AND is_deleted=false
  GROUP BY year, company_code, voucher_date, COALESCE(voucher_type, ''), voucher_no
),
"""
_PG_DIFF_SQL += r"""
newer AS MATERIALIZED (
  SELECT year, company_code, voucher_date, COALESCE(voucher_type, '') AS voucher_type, voucher_no,
         md5(string_agg(
           account_code || '|' ||
           CASE WHEN COALESCE(debit_amount,0)<>0 AND COALESCE(credit_amount,0)=0 THEN 'D'
                WHEN COALESCE(credit_amount,0)<>0 AND COALESCE(debit_amount,0)=0 THEN 'C' ELSE 'X' END || '|' ||
           ROUND(CASE WHEN COALESCE(debit_amount,0)<>0 THEN debit_amount ELSE COALESCE(credit_amount,0) END,2)::text,
           E'\n' ORDER BY account_code,
           CASE WHEN COALESCE(debit_amount,0)<>0 AND COALESCE(credit_amount,0)=0 THEN 'D'
                WHEN COALESCE(credit_amount,0)<>0 AND COALESCE(debit_amount,0)=0 THEN 'C' ELSE 'X' END,
           ROUND(CASE WHEN COALESCE(debit_amount,0)<>0 THEN debit_amount ELSE COALESCE(credit_amount,0) END,2)::text
         )) AS signature,
         GREATEST(ABS(SUM(COALESCE(debit_amount,0))), ABS(SUM(COALESCE(credit_amount,0)))) AS amount
  FROM tb_ledger WHERE dataset_id=:new_id AND is_deleted=false
  GROUP BY year, company_code, voucher_date, COALESCE(voucher_type, ''), voucher_no
),
diff AS MATERIALIZED (
  SELECT COALESCE(n.year,b.year) AS year, COALESCE(n.company_code,b.company_code) AS company_code,
         COALESCE(n.voucher_date,b.voucher_date) AS voucher_date,
         COALESCE(n.voucher_type,b.voucher_type) AS voucher_type,
         COALESCE(n.voucher_no,b.voucher_no) AS voucher_no,
         CASE WHEN b.signature IS NULL THEN 'added' WHEN n.signature IS NULL THEN 'deleted' ELSE 'modified' END AS kind,
         b.amount AS old_amount, n.amount AS new_amount,
         CASE WHEN b.signature IS NULL THEN n.amount WHEN n.signature IS NULL THEN b.amount
              ELSE GREATEST(ABS(b.amount),ABS(n.amount)) END AS amount,
         COALESCE(n.amount,0)-COALESCE(b.amount,0) AS amount_delta
  FROM base b FULL JOIN newer n USING (year,company_code,voucher_date,voucher_type,voucher_no)
  WHERE b.signature IS NULL OR n.signature IS NULL OR b.signature<>n.signature
), ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY kind ORDER BY voucher_date,company_code,voucher_type,voucher_no) AS rn
  FROM diff
)
"""
_PG_DIFF_SQL += r"""
SELECT 'aggregate' AS row_type, kind, EXTRACT(MONTH FROM voucher_date)::int AS month,
       COUNT(*)::bigint AS item_count, SUM(amount) AS amount, SUM(amount_delta) AS amount_delta,
       NULL::int AS year, NULL::text AS company_code, NULL::date AS voucher_date,
       NULL::text AS voucher_type, NULL::text AS voucher_no,
       NULL::numeric AS old_amount, NULL::numeric AS new_amount
FROM diff GROUP BY kind, EXTRACT(MONTH FROM voucher_date)::int
UNION ALL
SELECT 'sample', kind, EXTRACT(MONTH FROM voucher_date)::int, 1::bigint, amount, amount_delta,
       year, company_code, voucher_date, voucher_type, voucher_no, old_amount, new_amount
FROM ranked WHERE rn<=20
ORDER BY row_type, kind, month, voucher_date NULLS FIRST, company_code, voucher_type, voucher_no
"""


async def _pg_report(db: AsyncSession, base_id: UUID, new_id: UUID) -> dict[str, Any]:
    report = _empty_report(base_id, new_id)
    rows = (
        await db.execute(sa.text(_PG_DIFF_SQL), {"base_id": base_id, "new_id": new_id})
    ).mappings().all()
    for row in rows:
        kind = str(row["kind"])
        if row["row_type"] == "aggregate":
            month = str(int(row["month"]))
            cell = {
                "count": int(row["item_count"]),
                "amount": _money(row["amount"]),
                "net_amount_change": _money(row["amount_delta"]),
            }
            report["by_month"].setdefault(month, {})[kind] = cell
            total = report["summary"][kind]
            total["count"] += cell["count"]
            total["amount"] = _money(Decimal(total["amount"]) + Decimal(cell["amount"]))
            total["net_amount_change"] = _money(
                Decimal(total["net_amount_change"]) + Decimal(cell["net_amount_change"])
            )
            continue
        key = VoucherKey.of(
            year=row["year"],
            company_code=row["company_code"],
            voucher_date=row["voucher_date"],
            voucher_type=row["voucher_type"],
            voucher_no=row["voucher_no"],
        )
        report["samples"][kind].append({
            "voucher_key": key.to_str(),
            "month": int(row["month"]),
            "old_amount": _money(row["old_amount"]),
            "new_amount": _money(row["new_amount"]),
            "amount_change": _money(row["amount_delta"]),
        })
    return report


async def _python_vouchers(db: AsyncSession, dataset_id: UUID) -> dict[str, dict[str, Any]]:
    table = TbLedger.__table__
    rows = (
        await db.execute(
            sa.select(
                table.c.year, table.c.company_code, table.c.voucher_date, table.c.voucher_type,
                table.c.voucher_no, table.c.account_code, table.c.debit_amount, table.c.credit_amount,
            ).where(table.c.dataset_id == dataset_id, table.c.is_deleted == sa.false())
        )
    ).mappings().all()
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = VoucherKey.of(
            year=row["year"],
            company_code=row["company_code"],
            voucher_date=row["voucher_date"],
            voucher_type=row["voucher_type"],
            voucher_no=row["voucher_no"],
        )
        token = key.to_str()
        item = groups.setdefault(token, {"key": key, "lines": [], "debit": Decimal(0), "credit": Decimal(0)})
        side = side_of(row["debit_amount"], row["credit_amount"])
        amount = signed_amount(row["debit_amount"], row["credit_amount"], side)
        item["lines"].append((str(row["account_code"]), side, _money(amount)))
        item["debit"] += Decimal(str(row["debit_amount"] or 0))
        item["credit"] += Decimal(str(row["credit_amount"] or 0))
    for item in groups.values():
        item["signature"] = tuple(sorted(item.pop("lines")))
        item["amount"] = max(abs(item.pop("debit")), abs(item.pop("credit")))
    return groups


def _add_change(report: dict[str, Any], kind: str, key: VoucherKey, old: Decimal, new: Decimal) -> None:
    amount = new if kind == "added" else old if kind == "deleted" else max(abs(old), abs(new))
    delta = new - old
    month_value = int(str(key.voucher_date).split("-")[1])
    month = str(month_value)
    cell = report["by_month"].setdefault(month, {}).setdefault(
        kind, {"count": 0, "amount": Decimal(0), "net_amount_change": Decimal(0)}
    )
    cell["count"] += 1
    cell["amount"] += amount
    cell["net_amount_change"] += delta
    total = report["summary"][kind]
    total["count"] += 1
    total["amount"] = _money(Decimal(total["amount"]) + amount)
    total["net_amount_change"] = _money(Decimal(total["net_amount_change"]) + delta)
    if len(report["samples"][kind]) < 20:
        report["samples"][kind].append({
            "voucher_key": key.to_str(), "month": month_value,
            "old_amount": _money(old), "new_amount": _money(new), "amount_change": _money(delta),
        })


async def _python_report(db: AsyncSession, base_id: UUID, new_id: UUID) -> dict[str, Any]:
    report = _empty_report(base_id, new_id)
    base = await _python_vouchers(db, base_id)
    newer = await _python_vouchers(db, new_id)
    for token in sorted(set(base) | set(newer)):
        old_item, new_item = base.get(token), newer.get(token)
        if old_item is None:
            _add_change(report, "added", new_item["key"], Decimal(0), new_item["amount"])
        elif new_item is None:
            _add_change(report, "deleted", old_item["key"], old_item["amount"], Decimal(0))
        elif old_item["signature"] != new_item["signature"]:
            _add_change(report, "modified", new_item["key"], old_item["amount"], new_item["amount"])
    for kinds in report["by_month"].values():
        for cell in kinds.values():
            cell["amount"] = _money(cell["amount"])
            cell["net_amount_change"] = _money(cell["net_amount_change"])
    return report


async def build_voucher_diff(
    db: AsyncSession,
    *,
    base_dataset_id: UUID,
    new_dataset_id: UUID,
) -> dict[str, Any]:
    started = time.perf_counter()
    dialect = db.get_bind().dialect.name if db.get_bind() is not None else ""
    report = (
        await _pg_report(db, base_dataset_id, new_dataset_id)
        if dialect == "postgresql"
        else await _python_report(db, base_dataset_id, new_dataset_id)
    )
    report["duration_ms"] = int((time.perf_counter() - started) * 1000)
    return report


async def build_and_store_voucher_diff(
    db: AsyncSession,
    *,
    staged_dataset_id: UUID,
    base_dataset_id: UUID | None,
) -> dict[str, Any]:
    """生成失败也写明原因；调用方统一决定何时 commit。"""
    if base_dataset_id is None:
        report: dict[str, Any] = {"status": "not_applicable", "reason": "没有上一 active 版本"}
    else:
        try:
            async with db.begin_nested():
                report = await build_voucher_diff(
                    db,
                    base_dataset_id=base_dataset_id,
                    new_dataset_id=staged_dataset_id,
                )
        except Exception as exc:  # SAVEPOINT 已回滚，主导入事务仍可继续
            report = {"status": "failed", "reason": str(exc)[:500]}
    dataset = await db.get(LedgerDataset, staged_dataset_id)
    if dataset is not None:
        dataset.source_summary = {**(dataset.source_summary or {}), "voucher_diff": report}
        await db.flush()
    return report


__all__ = ["build_and_store_voucher_diff", "build_voucher_diff"]
