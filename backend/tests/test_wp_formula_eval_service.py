"""acnr-foundation-defect-closure T13：底稿公式三参 WP 的 A1 第三参按目录 sheet 精确取值（design §2.5）。

真实目录 + SQLite 真 ORM（与 ``tests/acnr/test_wp_cell_target.py`` 同一夹具形态）：
- ``evaluate_wp_formula_expression`` 三参 A1：两张 sheet 同一 A1 各取各值，结果与 ``read_formula_cell`` 逐值相等；
  取不到 / 多义时 errors 非空、带中文原因（4 个调用方据此丢弃该值，0 只是占位）；
- ``WPExecutor.execute`` 三参 A1 返回真实值，取不到返回 None（原来把表名当列名、恒 0）；
- 两参与 D2-3 分支不走新分支（spy ``read_sheet_cell`` 0 次）。

SQLite 上原生 SQL 按 ``str(uuid)`` 绑定匹配不到（存 32 位十六进制），项目年度查询在下一层
``wp_cell_reader.fetch_project_audit_year`` 换成固定 2025；真库三者相等用例随 T14 的 pg_only。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType  # noqa: E402
from app.services import wp_cell_reader  # noqa: E402
from app.services.acnr.catalog import get_catalog  # noqa: E402
from app.services.acnr.wp_cell_target import read_formula_cell  # noqa: E402
from app.services.formula_engine import WPExecutor  # noqa: E402
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression  # noqa: E402

_TABLES = [User.__table__, Project.__table__, WpIndex.__table__, WorkingPaper.__table__]
_E1 = {"html_data": {
    "货币资金审定表E1-1": {"cells": {"C10": "100.50"}},
    "货币资金分析表E1-14": {"cells": {"C10": "0.125"}},
}, "audited_amount": "777"}
_AUDITED = "WP('E1','货币资金审定表E1-1','C10')"
_ANALYSIS = "WP('E1','货币资金分析表E1-14','C10')"


@pytest.fixture
async def world(monkeypatch):
    async def _year(_db, _pid):
        return 2025

    monkeypatch.setattr(wp_cell_reader, "fetch_project_audit_year", _year)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        pid = uuid.uuid4()
        db.add(Project(id=pid, name="【测试】三参 WP 取值", client_name="【测试】三参 WP 取值",
                       status=ProjectStatus.execution, template_type="listed", report_scope="standalone",
                       audit_year=2025, scenario="normal"))
        await db.flush()
        idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code="E1", wp_name="【测试】E1")
        db.add(idx)
        await db.flush()
        db.add(WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path="E1.xlsx",
                            source_type=WpSourceType.template, parsed_data=_E1))
        await db.commit()
        yield db, pid
    await engine.dispose()


async def _eval(db, pid, expr: str, year: int = 2025):
    return await evaluate_wp_formula_expression(db, project_id=pid, year=year, expression=expr)


async def test_two_sheets_same_a1_each_reads_its_own(world):
    db, pid = world
    audited, errs1 = await _eval(db, pid, _AUDITED)
    analysis, errs2 = await _eval(db, pid, _ANALYSIS)
    assert (audited, errs1) == (Decimal("100.50"), [])
    assert (analysis, errs2) == (Decimal("0.125"), [])
    total, errs = await _eval(db, pid, f"{_AUDITED}+{_ANALYSIS}")
    assert (total, errs) == (Decimal("100.625"), [])


async def test_value_equals_shared_reader(world):
    """底稿公式三参求值 == read_formula_cell 直读（同一读取函数，不是另一份实现）。"""
    db, pid = world
    direct = await read_formula_cell(db, project_id=pid, year=2025, wp_code="E1", sheet_text="货币资金分析表E1-14",
                                     cell="C10", index=get_catalog())
    value, _ = await _eval(db, pid, _ANALYSIS)
    assert direct.read.state == "ok" and direct.read.value == value


@pytest.mark.parametrize("expr, needle", [
    ("WP('E1','货币资金分析表E1-14','Z99')", "WP('E1','货币资金分析表E1-14','Z99')："),
    ("WP('F2','底稿目录','B20')", "WP('F2','底稿目录','B20')："),
], ids=["cell_empty", "ambiguous"])
async def test_non_ok_reports_reason_not_silent_zero(world, expr, needle):
    db, pid = world
    _value, errs = await _eval(db, pid, expr)
    assert errs and errs[0].startswith(needle) and len(errs[0]) > len(needle), errs


async def test_year_mismatch_is_an_error(world):
    db, pid = world
    _value, errs = await _eval(db, pid, _ANALYSIS, year=2024)
    assert errs and "年度" in errs[0], errs


async def test_executor_three_arg_a1_reads_real_value(world):
    db, pid = world
    assert await WPExecutor.execute(db, pid, "E1", "货币资金分析表E1-14", field="C10") == Decimal("0.125")
    assert await WPExecutor.execute(db, pid, "E1", "货币资金审定表E1-1", field="C10") == Decimal("100.50")
    assert await WPExecutor.execute(db, pid, "E1", "货币资金分析表E1-14", field="Z99") is None


async def test_two_arg_and_d23_do_not_take_new_branch(world, monkeypatch):
    db, pid = world
    calls: list[tuple] = []
    original = WPExecutor.read_sheet_cell

    async def _spy(*args, **kwargs):
        calls.append(args)
        return await original(*args, **kwargs)

    monkeypatch.setattr(WPExecutor, "read_sheet_cell", staticmethod(_spy))
    assert await WPExecutor.execute(db, pid, "E1", "审定数") == Decimal("777")
    value, errs = await _eval(db, pid, "WP('E1','审定数')")
    assert (value, errs) == (Decimal("777"), [])
    d23 = []

    async def _fake_d23(_db, _pid, wp_code, sheet, field):
        d23.append((wp_code, sheet, field))
        return Decimal("5")

    monkeypatch.setattr(WPExecutor, "_resolve_d23", staticmethod(_fake_d23))
    value, errs = await _eval(db, pid, "WP('D2','坏账准备明细表D2-3','B5')")
    assert (value, errs, d23) == (Decimal("5"), [], [("D2", "坏账准备明细表D2-3", "B5")])
    assert calls == []
