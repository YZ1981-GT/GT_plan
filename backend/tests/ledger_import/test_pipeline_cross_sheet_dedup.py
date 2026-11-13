"""管线级回归：同一份文件里「科目余额表 + 辅助余额表 + 序时账 + 辅助明细账」四个 sheet 同时存在时，
tb_balance / tb_ledger 不得因为辅助 sheet 再各写一份而出现重复行。

真跑 ``execute_pipeline``（SQLite 内存库），不 mock 管线本身。
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

import openpyxl
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_models import TbAuxBalance, TbAuxLedger, TbBalance, TbLedger


def _build_workbook(path: Path, *, with_ledger_sheet: bool = True) -> Path:
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "科目余额表"
    ws.append(["科目编码", "科目名称", "期初借方", "期初贷方", "本期借方", "本期贷方", "期末借方", "期末贷方"])
    ws.append(["1002", "银行存款", 100, 0, 50, 20, 130, 0])
    ws.append(["1122", "应收账款", 40, 0, 10, 0, 50, 0])
    ws.append(["2202", "应付账款", 0, 30, 0, 0, 0, 30])

    ws = wb.create_sheet("辅助余额表")
    ws.append(["科目编码", "科目名称", "辅助类型", "辅助编码", "辅助名称",
               "期初借方", "期初贷方", "本期借方", "本期贷方", "期末借方", "期末贷方"])
    ws.append(["1002", "银行存款", "银行账户", "B1", "工行", 60, 0, 30, 10, 80, 0])
    ws.append(["1002", "银行存款", "银行账户", "B2", "建行", 40, 0, 20, 10, 50, 0])
    ws.append(["1122", "应收账款", "客户", "C1", "甲公司", 40, 0, 10, 0, 50, 0])
    # 只有辅助明细、没有汇总行的科目：应保留聚合出来的虚拟汇总行
    ws.append(["1221", "其他应收款", "客户", "C2", "乙公司", 7, 0, 0, 0, 7, 0])

    if with_ledger_sheet:
        ws = wb.create_sheet("序时账")
        ws.append(["记账日期", "凭证号", "摘要", "科目编码", "科目名称", "借方", "贷方"])
        ws.append([date(2025, 1, 15), "记-001", "收款", "1002", "银行存款", 50, None])
        ws.append([date(2025, 1, 15), "记-001", "收款", "1122", "应收账款", None, 50])
        ws.append([date(2025, 2, 10), "记-002", "付款", "2202", "应付账款", 20, None])
        ws.append([date(2025, 2, 10), "记-002", "付款", "1002", "银行存款", None, 20])

    ws = wb.create_sheet("辅助明细账")
    ws.append(["记账日期", "凭证号", "摘要", "科目编码", "科目名称", "借方", "贷方",
               "辅助类型", "辅助编码", "辅助名称"])
    ws.append([date(2025, 1, 15), "记-001", "收款", "1002", "银行存款", 50, None, "银行账户", "B1", "工行"])
    ws.append([date(2025, 1, 15), "记-001", "收款", "1122", "应收账款", None, 50, "客户", "C1", "甲公司"])
    ws.append([date(2025, 2, 10), "记-002", "付款", "1002", "银行存款", None, 20, "银行账户", "B2", "建行"])

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _run(session_factory, path: Path, project_id: uuid.UUID):
    from app.services.ledger_import.pipeline import execute_pipeline

    async def _noop_rebuild(*_a, **_kw) -> int:
        return 0

    with patch("app.core.database.async_session", session_factory), \
         patch("app.services.ledger_import.pipeline._detect_memory_pressure", return_value=True), \
         patch("app.services.smart_import_engine.rebuild_aux_balance_summary", _noop_rebuild):
        return await execute_pipeline(
            job_id=uuid.uuid4(), project_id=project_id, year=2025, custom_mapping=None,
            created_by=None, file_sources=[(path.name, path)], force_activate=True,
        )


async def _rows(session_factory, model, project_id):
    async with session_factory() as db:
        return list((await db.execute(sa.select(model).where(model.project_id == project_id))).scalars().all())


@pytest.mark.asyncio
async def test_balance_main_table_has_one_row_per_account(session_factory, tmp_path):
    pid = uuid.uuid4()
    result = await _run(session_factory, _build_workbook(tmp_path / "four.xlsx"), pid)
    assert result.success

    bal = await _rows(session_factory, TbBalance, pid)
    codes = sorted(r.account_code for r in bal)
    assert codes == ["1002", "1122", "1221", "2202"], f"主表每个科目只应一行：{codes}"

    by_code = {r.account_code: r for r in bal}
    # 有汇总行的科目：用真实汇总行（金额取汇总表，不是辅助表聚合值），且不带聚合标记
    for code in ("1002", "1122", "2202"):
        assert not (by_code[code].raw_extra or {}).get("_aggregated_from_aux"), code
    assert by_code["1002"].closing_balance == 130
    # 只有辅助明细的科目：保留聚合出来的虚拟汇总行
    assert (by_code["1221"].raw_extra or {}).get("_aggregated_from_aux") is True

    assert len(await _rows(session_factory, TbAuxBalance, pid)) == 4


@pytest.mark.asyncio
async def test_ledger_main_table_not_duplicated_by_aux_ledger_sheet(session_factory, tmp_path):
    pid = uuid.uuid4()
    result = await _run(session_factory, _build_workbook(tmp_path / "four.xlsx"), pid)
    assert result.success

    ledger = await _rows(session_factory, TbLedger, pid)
    assert len(ledger) == 4, f"主序时账只应有序时账 sheet 的 4 行，实际 {len(ledger)}（辅助明细 sheet 不得再写一份）"
    assert result.ledger_rows == 4
    assert len(await _rows(session_factory, TbAuxLedger, pid)) == 3


@pytest.mark.asyncio
async def test_without_ledger_sheet_aux_ledger_still_feeds_main_table(session_factory, tmp_path):
    """没有序时账 sheet 时，辅助明细 sheet 仍要提供主表行，不能把主序时账写成空。"""
    pid = uuid.uuid4()
    result = await _run(session_factory, _build_workbook(tmp_path / "no_ledger.xlsx", with_ledger_sheet=False), pid)
    assert result.success
    assert len(await _rows(session_factory, TbLedger, pid)) == 3
    assert len(await _rows(session_factory, TbAuxLedger, pid)) == 3
