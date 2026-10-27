"""``wp_cell_reader.resolve_wp_cell`` 共享契约（formula-hub design §8.2 表逐行钉住；ACNR T11 先落地提交）。

§8.2 约定：先落地方实现并提交本文件，后落地方只接线、不改这里的断言。本文件钉的是读取函数自身的行：
位置与签名 / 返回 / 年度 / 底稿绑定 / 工作表 / 单元格 / 异常。表里「WPExecutor」「三参预载挂点」「底稿公式代入」
三行是调用方的接线，由各自任务的用例钉（两参分支归 formula-hub 任务 23，三参 A1 分支归 ACNR T13）；
「formula_wp_semantics」行本文件只钉读取函数这一条登记。

SQLite 真 ORM（项目年度查询是 PG 专用 SQL，年度闸门用例替换 ``fetch_project_audit_year``）；末尾一例 pg_only
在真库只读事务里走真实年度查询。
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType  # noqa: E402
from app.services import wp_cell_reader  # noqa: E402
from app.services.wp_cell_reader import CatalogSheetKeys, WpCellRead, resolve_wp_cell  # noqa: E402

_TABLES = [User.__table__, Project.__table__, WpIndex.__table__, WorkingPaper.__table__]
BACKEND = Path(__file__).resolve().parents[1]

#: 同一底稿两张表同 A1、一张表名带排序前缀与多余空白（归一后相等）、一个文本格、一个空格
_PARSED = {
    "html_data": {
        "货币资金审定表E1-1": {"cells": {"C10": {"v": "100.50"}, "D5": "结论：无异常", "E3": "", "F2": 7}},
        "货币资金分析表E1-14": {"cells": {"C10": "0.125"}},
        "1. 银行存款明细表  E1-2": {"cells": {"B3": 42}},
    },
}


@pytest.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
        # 真库 working_paper 有 (project_id, wp_index_id) 非部分唯一索引（2026-10-28 现查），「多份底稿」与
        # 「已删 + 在用」两种形态真库造不出来；这里拆掉索引只为钉住读取函数的防御分支。
        await conn.execute(text("DROP INDEX uq_working_paper_project_index"))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        pid = uuid.uuid4()
        db.add(Project(id=pid, name="【测试】共享读取契约", client_name="【测试】共享读取契约",
                       status=ProjectStatus.execution, template_type="listed", report_scope="standalone",
                       audit_year=2025, scenario="normal"))
        await db.flush()
        papers = {}
        for code, parsed, copies in (("E1", _PARSED, 1), ("E9", {}, 1), ("D2", {"html_data": {}}, 2)):
            idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=code, wp_name=f"【测试】{code}")
            db.add(idx)
            await db.flush()
            for _ in range(copies):
                wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path=f"{code}.xlsx",
                                  source_type=WpSourceType.template, parsed_data=parsed)
                db.add(wp)
                papers[code] = wp.id
        # 已删除的那一份不参与绑定
        idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code="F1", wp_name="【测试】F1")
        db.add(idx)
        await db.flush()
        db.add(WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path="F1.xlsx",
                            source_type=WpSourceType.template, parsed_data=_PARSED, is_deleted=True))
        live_f1 = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path="F1b.xlsx",
                               source_type=WpSourceType.template, parsed_data={"html_data": {"表": {"cells": {"A1": 1}}}})
        db.add(live_f1)
        papers["F1"] = live_f1.id
        await db.commit()
        yield {"db": db, "pid": pid, "papers": papers}
    await engine.dispose()


async def _read(world, wp_code, sheet_key, cell, *, year=None):
    return await resolve_wp_cell(world["db"], world["pid"], year, wp_code, sheet_key, cell)


# ── 位置与签名 / 返回 ─────────────────────────────────────────────────────────

def test_signature_six_positional_or_keyword_params():
    assert inspect.iscoroutinefunction(resolve_wp_cell)
    params = list(inspect.signature(resolve_wp_cell).parameters.values())
    assert [p.name for p in params] == ["db", "project_id", "year", "wp_code", "sheet_key", "cell"]
    assert all(p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for p in params)
    assert all(p.default is inspect.Parameter.empty for p in params)


def test_return_type_is_frozen_dataclass_with_contract_fields():
    assert dataclasses.is_dataclass(WpCellRead) and WpCellRead.__dataclass_params__.frozen
    fields = {f.name: f for f in dataclasses.fields(WpCellRead)}
    for name in ("state", "value", "reason", "wp_id", "sheet_key", "matches", "candidates"):
        assert name in fields, name
    assert fields["matches"].default == 0 and fields["candidates"].default == ()


async def test_positional_call_like_acnr_three_arg(world):
    """ACNR 三参的位置调用 ``resolve_wp_cell(db, project_id, None, wp_code, column, field)`` 成立。"""
    read = await resolve_wp_cell(world["db"], world["pid"], None, "E1", "货币资金分析表E1-14", "C10")
    assert (read.state, read.value, read.reason) == ("ok", Decimal("0.125"), None)
    assert read.wp_id == world["papers"]["E1"] and read.sheet_key == "货币资金分析表E1-14"


# ── 年度 ─────────────────────────────────────────────────────────────────────

async def test_year_none_does_not_query_project_year(world, monkeypatch):
    async def _boom(*_a, **_k):
        raise AssertionError("year=None 不应查项目年度")

    monkeypatch.setattr(wp_cell_reader, "fetch_project_audit_year", _boom)
    assert (await _read(world, "E1", "货币资金审定表E1-1", "C10")).state == "ok"


@pytest.mark.parametrize("audit_year, state, reason_part", [
    (None, "blocked", "项目未设置审计年度"),
    (2024, "missing", "底稿年度与项目年度不符"),
    (2025, "ok", None),
])
async def test_year_gate(world, monkeypatch, audit_year, state, reason_part):
    calls = []

    async def _fake(db, project_id):
        calls.append(project_id)
        return audit_year

    monkeypatch.setattr(wp_cell_reader, "fetch_project_audit_year", _fake)
    read = await _read(world, "E1", "货币资金审定表E1-1", "C10", year=2025)
    assert calls == [world["pid"]]
    assert read.state == state
    if reason_part is None:
        assert read.value == Decimal("100.50") and read.reason is None
    else:
        assert read.value is None and reason_part in read.reason


# ── 底稿绑定 ─────────────────────────────────────────────────────────────────

async def test_no_paper_is_missing(world):
    read = await _read(world, "Z9", None, "A1")
    assert (read.state, read.value, read.wp_id) == ("missing", None, None)
    assert read.reason == "项目中没有底稿 Z9"


async def test_two_live_papers_is_blocked(world):
    read = await _read(world, "D2", None, "A1")
    assert (read.state, read.value, read.reason) == ("blocked", None, "底稿记录有歧义")
    assert len(read.candidates) == 2


async def test_deleted_paper_not_bound(world):
    read = await _read(world, "F1", "表", "A1")
    assert (read.state, read.value, read.wp_id) == ("ok", Decimal("1"), world["papers"]["F1"])


# ── 工作表 ───────────────────────────────────────────────────────────────────

async def test_two_arg_counts_sheets_and_takes_first(world):
    """sheet_key=None 不判表：C10 在两张表里都有，matches=2，值取 extract_custom_cells 顺序第一个。"""
    read = await _read(world, "E1", None, "c10")
    assert (read.state, read.value, read.matches) == ("ok", Decimal("100.50"), 2)
    assert read.sheet_key == "货币资金审定表E1-1"


async def test_same_a1_two_sheets_each_reads_its_own(world):
    a = await _read(world, "E1", "货币资金审定表E1-1", "C10")
    b = await _read(world, "E1", "货币资金分析表E1-14", "C10")
    assert (a.value, b.value) == (Decimal("100.50"), Decimal("0.125"))
    assert (a.matches, b.matches) == (1, 1)


async def test_sheet_key_normalized_both_sides(world):
    read = await _read(world, "E1", "银行存款明细表 E1-2", "B3")
    assert (read.state, read.value, read.sheet_key) == ("ok", Decimal("42"), "1. 银行存款明细表  E1-2")


def test_catalog_sheet_keys_first_landing_is_not_found():
    assert wp_cell_reader._catalog_sheet_keys("E1", "货币资金审定表E1-1") == CatalogSheetKeys(frozenset(), "not_found")


async def test_catalog_keys_extend_accepted_set(world, monkeypatch):
    monkeypatch.setattr(wp_cell_reader, "_catalog_sheet_keys",
                        lambda wp_code, key: CatalogSheetKeys(frozenset({"货币资金分析表E1-14"}), "found"))
    read = await _read(world, "E1", "E1-14", "C10")
    assert (read.state, read.value) == ("ok", Decimal("0.125"))


@pytest.mark.parametrize("verdict, reason", [("ambiguous", "工作表名有歧义"), ("alias_forbidden", "该别名不能用于取值")])
async def test_catalog_verdict_blocks_with_candidates(world, monkeypatch, verdict, reason):
    monkeypatch.setattr(wp_cell_reader, "_catalog_sheet_keys",
                        lambda wp_code, key: CatalogSheetKeys(frozenset(), verdict, ("E1/E1-1", "E1/E1-14")))
    read = await _read(world, "E1", "货币资金", "C10")
    assert (read.state, read.value, read.reason, read.candidates) == ("blocked", None, reason, ("E1/E1-1", "E1/E1-14"))


async def test_same_accepted_keys_two_values_is_blocked(world, monkeypatch):
    monkeypatch.setattr(wp_cell_reader, "_catalog_sheet_keys", lambda wp_code, key: CatalogSheetKeys(
        frozenset({"货币资金审定表E1-1", "货币资金分析表E1-14"}), "found"))
    read = await _read(world, "E1", "货币资金审定表E1-1", "C10")
    assert (read.state, read.value, read.reason) == ("blocked", None, "同一工作表有多份数据")
    assert set(read.candidates) == {"货币资金审定表E1-1", "货币资金分析表E1-14"}


# ── 单元格 ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("wp_code, sheet, cell, state, reason", [
    ("E1", "不存在的表", "C10", "missing", "没有该工作表的数据"),
    ("E1", "货币资金审定表E1-1", "Z99", "missing", "单元格未录入"),
    ("E1", "货币资金审定表E1-1", "E3", "missing", "单元格未录入"),
    ("E9", "任意表", "A1", "missing", "没有该工作表的数据"),
    ("E1", None, "Z99", "missing", "单元格未录入"),
])
async def test_missing_reasons(world, wp_code, sheet, cell, state, reason):
    read = await _read(world, wp_code, sheet, cell)
    assert (read.state, read.value, read.reason) == (state, None, reason)


async def test_text_cell_is_blocked_non_numeric(world):
    read = await _read(world, "E1", "货币资金审定表E1-1", "D5")
    assert (read.state, read.value) == ("blocked", None)
    assert read.reason.startswith("单元格内容不是数值：") and "结论" in read.reason


async def test_integer_cell_is_ok(world):
    assert (await _read(world, "E1", "货币资金审定表E1-1", "F2")).value == Decimal("7")


# ── 异常 ─────────────────────────────────────────────────────────────────────

async def test_database_error_propagates():
    """表不存在 ⇒ OperationalError 原样上抛，不转 missing。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession)() as db:
            with pytest.raises(OperationalError):
                await resolve_wp_cell(db, uuid.uuid4(), None, "E1", None, "A1")
    finally:
        await engine.dispose()


# ── formula_wp_semantics 登记（只钉读取函数这一条） ───────────────────────────

def test_reader_registered_and_points_to_real_function():
    from app.services.formula_wp_semantics import WP_CELL_READER_IMPL, impl_of

    rel, _, fn = WP_CELL_READER_IMPL.partition("::")
    tree = ast.parse((BACKEND / rel).read_text(encoding="utf-8"))
    defs = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == fn]
    assert len(defs) == 1, WP_CELL_READER_IMPL
    spec = impl_of(WP_CELL_READER_IMPL)
    assert spec is not None and spec.positional_args == ("wp_code", "sheet_key", "cell")
    assert "value=None" in spec.on_missing


def test_reader_does_not_reference_registry():
    names = {n.id for n in ast.walk(ast.parse(inspect.getsource(wp_cell_reader))) if isinstance(n, ast.Name)}
    mods = {n.module for n in ast.walk(ast.parse(inspect.getsource(wp_cell_reader))) if isinstance(n, ast.ImportFrom)}
    assert "formula_wp_semantics" not in names and "app.services.formula_wp_semantics" not in mods


# ── 真 PG：真实年度查询（只读回滚） ──────────────────────────────────────────

@pytest.mark.pg_only
async def test_real_year_gate_on_pg():
    from app.core.config import settings

    eng = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with async_sessionmaker(eng, expire_on_commit=False)() as s:
            await s.execute(text("SET TRANSACTION READ ONLY"))
            try:
                row = (await s.execute(text(
                    "SELECT p.id, p.audit_year, w.wp_code FROM projects p JOIN wp_index w ON w.project_id = p.id "
                    "JOIN working_paper wp ON wp.wp_index_id = w.id AND COALESCE(wp.is_deleted, false) = false "
                    "WHERE p.audit_year IS NOT NULL AND COALESCE(p.is_deleted, false) = false "
                    "GROUP BY p.id, p.audit_year, w.wp_code HAVING count(*) = 1 ORDER BY p.id, w.wp_code LIMIT 1"))).first()
                assert row is not None, "真库没有可用的项目 / 底稿（防空转）"
                pid, audit_year, wp_code = row
                wrong = await resolve_wp_cell(s, pid, audit_year + 1, wp_code, None, "ZZ9999")
                assert (wrong.state, wrong.value) == ("missing", None) and "底稿年度与项目年度不符" in wrong.reason
                right = await resolve_wp_cell(s, str(pid), audit_year, wp_code, None, "ZZ9999")
                assert (right.state, right.reason) == ("missing", "单元格未录入") and right.wp_id is not None
            finally:
                await s.rollback()
    finally:
        await eng.dispose()
