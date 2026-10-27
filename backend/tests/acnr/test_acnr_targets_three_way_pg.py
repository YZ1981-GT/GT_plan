"""三者相等（acnr-foundation-defect-closure 需求 1.2，T13 移交、随 T14 交付；pg_only）。

真 PG 回滚事务内建【测试】项目与 E1 底稿（``parsed_data.html_data`` 写 E1-14!C10=0.125、E1-15!C8=222，两张表另在同一
A1 写不同值），同一夹具上逐值比较：

1. 底稿公式三参求值 ``evaluate_wp_formula_expression("WP('E1','<表名>','<A1>')")``；
2. acnr_targets 取值 ``read_acnr_target_values(resolve_acnr_targets(...))``；
3. 库内值（SQL 直读 ``parsed_data -> 'html_data' -> 表名 -> 'cells' -> A1``）。

项目年度走真实的 ``fetch_project_audit_year``（SQLite 上原生 SQL 匹配不到，故放 PG）。事务最后回滚，不留数据。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.base import ProjectStatus
from app.models.core import Project
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
from app.services.acnr.catalog import get_catalog
from app.services.custom_query.acnr_target_values import read_acnr_target_values, resolve_acnr_targets
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

pytestmark = pytest.mark.pg_only

_E1_14 = "货币资金分析表E1-14"
_E1_15 = get_catalog().sheets_by_addr_id["E1/E1-15"]["sheet_name"]
_CELLS = {_E1_14: {"C10": "0.125", "C15": "-3.5"}, _E1_15: {"C8": "222", "C10": "999"}}
#: (addr_id, 表名, A1)：同一 A1（C10）两张表各取各的；C15 / C8 是目录里登记的另两格
_CASES = [("E1/E1-14/C10", _E1_14, "C10"), ("E1/E1-14/C15", _E1_14, "C15"), ("E1/E1-15/C8", _E1_15, "C8")]


async def _with_world(fn):
    from app.core.config import settings
    eng = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with async_sessionmaker(eng, expire_on_commit=False)() as s:
            try:
                pid = uuid.uuid4()
                s.add(Project(id=pid, name="【测试】acnr_targets 三者相等", client_name="【测试】acnr_targets 三者相等",
                              status=ProjectStatus.execution, template_type="listed", report_scope="standalone",
                              audit_year=2025, scenario="normal"))
                await s.flush()
                idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code="E1", wp_name="【测试】E1")
                s.add(idx)
                await s.flush()
                wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path="E1.xlsx",
                                  source_type=WpSourceType.template,
                                  parsed_data={"html_data": {k: {"cells": v} for k, v in _CELLS.items()}})
                s.add(wp)
                await s.flush()
                return await fn(s, pid, wp.id)
            finally:
                await s.rollback()
    finally:
        await eng.dispose()


async def test_formula_targets_and_stored_values_are_equal():
    async def run(s, pid, wp_id):
        resolved = await resolve_acnr_targets([a for a, _, _ in _CASES], project_id=str(pid), db=s)
        block = await read_acnr_target_values(resolved, project_id=str(pid), year=2025, db=s)
        assert block["year"] == 2025
        rows = []
        for (addr, sheet, a1), item in zip(_CASES, block["items"], strict=True):
            formula, errors = await evaluate_wp_formula_expression(
                s, project_id=pid, year=2025, expression=f"WP('E1','{sheet}','{a1}')")
            stored = (await s.execute(
                text("SELECT parsed_data -> 'html_data' -> :sheet -> 'cells' ->> :a1 FROM working_paper WHERE id = :id"),
                {"sheet": sheet, "a1": a1, "id": wp_id})).scalar_one()
            assert errors == [], (addr, errors)
            assert (item["addr_id"], item["state"]) == (addr, "ok")
            assert formula == Decimal(item["value"]) == Decimal(stored), (addr, formula, item["value"], stored)
            rows.append(formula)
        return rows

    assert await _with_world(run) == [Decimal("0.125"), Decimal("-3.5"), Decimal("222")]


async def test_missing_cell_is_error_in_formula_and_missing_in_targets():
    """取不到：底稿公式 errors 非空（调用方丢弃该值），acnr_targets 为 missing、value 为 None，都不是 0。"""
    async def run(s, pid, _wp_id):
        cat = get_catalog()
        addr = next(a for a in cat.cells_by_addr_id if a.startswith("E1/E1-15/") and a != "E1/E1-15/C8")
        a1 = cat.cells_by_addr_id[addr]["cell_address"]
        _value, errors = await evaluate_wp_formula_expression(
            s, project_id=pid, year=2025, expression=f"WP('E1','{_E1_15}','{a1}')")
        block = await read_acnr_target_values(
            await resolve_acnr_targets([addr], project_id=str(pid), db=s), project_id=str(pid), year=2025, db=s)
        (item,) = block["items"]
        return errors, item

    errors, item = await _with_world(run)
    assert errors and "单元格" in errors[0]
    assert (item["state"], item["value"], item["reason_code"]) == ("missing", None, "cell_empty")
