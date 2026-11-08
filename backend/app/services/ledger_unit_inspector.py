"""共享库只读的账套单位巡检（platform-global-display-settings-closure R8 / AC-18 的只读纪律）。

单连接；第一条业务语句是 ``SET TRANSACTION READ ONLY`` 并核验生效；结束时显式 rollback，从不写库，
报告只写到调用方给的目录。巡检对象是四表（余额表 / 序时账 / 辅助余额 / 辅助明细）的本位币金额列。

任一语句失败即整体失败抛出：只读事务里一条语句出错后整个事务进入 aborted，后续统计全是连带错误，
把它们记成「某字段 error」写进报告只会得到一份看似完整、实则失真的结果。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.services.dataset_unit_contract import classify_dataset_unit

logger = logging.getLogger(__name__)

_BALANCE_FIELDS = (
    "opening_balance", "opening_debit", "opening_credit",
    "debit_amount", "credit_amount",
    "closing_balance", "closing_debit", "closing_credit",
)
_LEDGER_FIELDS = ("debit_amount", "credit_amount")

#: 四表 → 本位币金额列（与 ``app.models.audit_platform_models`` 的 TbBalance / TbLedger / TbAuxBalance / TbAuxLedger 一致）
AMOUNT_FIELDS: dict[str, tuple[str, ...]] = {
    "tb_balance": _BALANCE_FIELDS,
    "tb_ledger": _LEDGER_FIELDS,
    "tb_aux_balance": _BALANCE_FIELDS,
    "tb_aux_ledger": _LEDGER_FIELDS,
}

_OVERFLOW_LIMIT = Decimal("999999999999999999.99")


class ReadOnlyViolation(Exception):
    """``SET TRANSACTION READ ONLY`` 没有生效。"""


class InspectorSchemaError(Exception):
    """巡检要读的表或列在库里不存在（schema 漂移）⇒ 拒绝产出报告。"""


async def _assert_columns_exist(conn) -> None:
    rows = (await conn.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = ANY(:tables)"
    ), {"tables": list(AMOUNT_FIELDS)})).fetchall()
    present: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        present.setdefault(str(table_name), set()).add(str(column_name))
    missing = [
        f"{table}.{column}"
        for table, fields in AMOUNT_FIELDS.items()
        for column in ("project_id", *fields)
        if column not in present.get(table, set())
    ]
    if missing:
        raise InspectorSchemaError(f"巡检对象在当前 schema 里不存在：{', '.join(missing)}")


async def inspect_datasets(
    db_url: str,
    output_dir: Path,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """只读巡检并写出 ``inspector_report.json``；给 ``project_id`` 时只统计该项目。"""
    engine = create_async_engine(db_url, poolclass=NullPool)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
    }
    scope_sql = " AND project_id = CAST(:pid AS uuid)" if project_id else ""
    params = {"pid": project_id} if project_id else {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            read_only = (await conn.execute(text("SHOW transaction_read_only"))).scalar_one()
            if read_only != "on":
                raise ReadOnlyViolation(f"transaction_read_only={read_only}，期望 on")
            await _assert_columns_exist(conn)

            datasets = (await conn.execute(text(
                "SELECT id, source_summary FROM ledger_datasets WHERE status = 'active'" + scope_sql
            ), params)).fetchall()
            classification = {"normalized_v1": 0, "legacy_declared": 0, "legacy_unknown": 0}
            for _id, summary in datasets:
                unit_class = classify_dataset_unit(summary if isinstance(summary, dict) else {})
                classification[unit_class] = classification.get(unit_class, 0) + 1
            report["dataset_count"] = len(datasets)
            report["classification"] = classification

            tables: dict[str, Any] = {}
            for table_name, fields in AMOUNT_FIELDS.items():
                row_count = (await conn.execute(text(
                    f"SELECT count(*) FROM {table_name} WHERE true" + scope_sql
                ), params)).scalar_one()
                field_stats: dict[str, Any] = {}
                for field in fields:
                    non_null, total, max_abs = (await conn.execute(text(
                        f"SELECT count({field}), sum({field}), max(abs({field})) "
                        f"FROM {table_name} WHERE {field} IS NOT NULL" + scope_sql
                    ), params)).one()
                    field_stats[field] = {
                        "non_null_count": int(non_null or 0),
                        "sum": None if total is None else str(total),
                        "max_absolute": None if max_abs is None else str(max_abs),
                        "overflow_risk": max_abs is not None and Decimal(str(max_abs)) > _OVERFLOW_LIMIT,
                    }
                tables[table_name] = {"row_count": int(row_count), "fields": field_stats}
            report["tables"] = tables
            await conn.rollback()
    finally:
        await engine.dispose()

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "inspector_report.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    logger.info("账套单位巡检报告已写到 %s", output_path)
    return report
