"""账套单位只读巡检（AC-18 只读纪律）。连当前 ``DATABASE_URL`` 的 PostgreSQL，只读事务、从不写库。

原版只断言报告有哪几个键：字段清单写错（不存在的 ``balance`` 列、不属于四表的 ``trial_balance``、漏了
``tb_aux_ledger``）、查询失败被吞进 ``error`` 字段、``project_id`` 参数被忽略，它都照样绿。
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.pg_only


def _pg_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgres"):
        pytest.skip("Requires PostgreSQL DATABASE_URL")
    return url


@pytest.mark.asyncio
async def test_inspector_reports_every_four_table_amount_field(tmp_path: Path):
    from app.services.ledger_unit_inspector import AMOUNT_FIELDS, inspect_datasets

    missing_project = str(uuid.uuid4())  # 只统计一个不存在的项目：结构完整、计数为 0，不扫全库
    report = await inspect_datasets(_pg_url(), tmp_path, project_id=missing_project)

    assert set(AMOUNT_FIELDS) == {"tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger"}
    assert report["project_id"] == missing_project
    assert report["dataset_count"] == 0
    assert report["classification"] == {"normalized_v1": 0, "legacy_declared": 0, "legacy_unknown": 0}
    assert set(report["tables"]) == set(AMOUNT_FIELDS)
    for table, fields in AMOUNT_FIELDS.items():
        stats = report["tables"][table]
        assert stats["row_count"] == 0, table
        assert set(stats["fields"]) == set(fields), table
        for field, item in stats["fields"].items():
            assert item == {"non_null_count": 0, "sum": None, "max_absolute": None, "overflow_risk": False}, (table, field)
    loaded = json.loads((tmp_path / "inspector_report.json").read_text(encoding="utf-8"))
    assert loaded["tables"] == report["tables"]


@pytest.mark.asyncio
async def test_inspector_refuses_report_on_schema_drift(tmp_path: Path, monkeypatch):
    from app.services import ledger_unit_inspector as inspector

    monkeypatch.setitem(inspector.AMOUNT_FIELDS, "tb_ledger", ("debit_amount", "balance"))
    with pytest.raises(inspector.InspectorSchemaError, match="tb_ledger.balance"):
        await inspector.inspect_datasets(_pg_url(), tmp_path, project_id=str(uuid.uuid4()))
    assert not (tmp_path / "inspector_report.json").exists()


@pytest.mark.asyncio
async def test_read_only_connection_rejects_update():
    """``SET TRANSACTION READ ONLY`` 之后的 UPDATE 必须被 PG 以 SQLSTATE 25006 拒绝（谓词恒假，即使失效也不改行）。"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(_pg_url(), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            with pytest.raises(Exception) as exc_info:
                await conn.execute(text("UPDATE ledger_datasets SET source_summary = source_summary WHERE false"))
            error_str = str(exc_info.value)
            assert "25006" in error_str or "read-only" in error_str.lower(), error_str
            await conn.rollback()
    finally:
        await engine.dispose()
