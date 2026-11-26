"""T12：ACNR 侧取值接线 ``wp_cell_target``（design §2.4 / D1，R2-F7）。

真实目录（``get_catalog()``，不 mock）+ SQLite 真 ORM：sheet 级 vs 父底稿绑定、借名 blocked、两 sheet 同 A1 各取各值、
目录外按原文读、多义 / 禁止别名不读、``effective_catalog`` 锁定命中按锁定目录判名、数据库异常上抛。
pg_only（回滚事务 + 自建样本）：原因细化（表单录入 / 只有文件）与库内值逐值相等。
"""
from __future__ import annotations

import ast
import inspect
import uuid
from decimal import Decimal

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
from app.services.acnr import wp_cell_target  # noqa: E402
from app.services.acnr.catalog import get_catalog  # noqa: E402
from app.services.acnr.limits import ACNR_BATCH_DEADLINE_S, ACNR_BATCH_LIMIT  # noqa: E402
from app.services.acnr.resolver import VersionNotFoundError  # noqa: E402
from app.services.acnr.wp_cell_target import (  # noqa: E402
    bind_wp_code, effective_catalog, read_entry_cell, read_formula_cell, sheet_key_for,
)

_TABLES = [User.__table__, Project.__table__, WpIndex.__table__, WorkingPaper.__table__]
#: 上一批目录：I1 的合并别名「I1-1」在这一批还不存在（T10 发布批次 20261027161822 才加）
_OLD_VERSION = "20261027145857"

_E1 = {"html_data": {
    "货币资金审定表E1-1": {"cells": {"C10": "100.50"}},
    "货币资金分析表E1-14": {"cells": {"C10": "0.125"}},
    "1-1": {"cells": {"B2": "9"}},
}}


def _sheet(addr: str) -> dict:
    return get_catalog().sheets_by_addr_id[addr]


@pytest.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        pid = uuid.uuid4()
        db.add(Project(id=pid, name="【测试】ACNR 取值接线", client_name="【测试】ACNR 取值接线",
                       status=ProjectStatus.execution, template_type="listed", report_scope="standalone",
                       audit_year=2025, scenario="normal"))
        await db.flush()
        papers = {}
        for code, parsed in (
            ("E1", _E1),
            ("D2", {"html_data": {"明细表D2-2": {"cells": {"B5": "1"}}}}),
            ("D2-2", {"html_data": {"明细表D2-2": {"cells": {"B5": "2"}}}}),
            ("I1", {"html_data": {"审定表I1": {"cells": {"C5": "11"}}, "I1-1": {"cells": {"C5": "22"}}}}),
            ("ZZ1", {"html_data": {"自定义表": {"cells": {"A1": "3.5"}}}}),
        ):
            idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=code, wp_name=f"【测试】{code}")
            db.add(idx)
            await db.flush()
            wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path=f"{code}.xlsx",
                              source_type=WpSourceType.template, parsed_data=parsed)
            db.add(wp)
            papers[code] = wp.id
        await db.commit()
        yield {"db": db, "pid": pid, "papers": papers}
    await engine.dispose()


def test_limits_shared_with_resolve_batch():
    assert (ACNR_BATCH_LIMIT, ACNR_BATCH_DEADLINE_S) == (50, 8)
    from app.routers import acnr as router_mod

    src = inspect.getsource(router_mod.acnr_resolve_batch)
    tree = ast.parse(src.lstrip())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    consts = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)}
    assert "ACNR_BATCH_LIMIT" in names and 50 not in consts


# ── sheet_key_for ────────────────────────────────────────────────────────────

def test_owned_name_is_normalized_key():
    cat = get_catalog()
    assert sheet_key_for(_sheet("E1/E1-14"), index=cat).key == "货币资金分析表E1-14"


def test_name_equal_to_own_code_is_owned():
    """S17/S17 的 sheet 名就是「S17」：按编码命中自身，不算借用（name_owner 不认编码命中，故不用它）。"""
    cat = get_catalog()
    assert sheet_key_for(_sheet("S17/S17"), index=cat).key == "S17"


def test_borrowed_and_ambiguous_names_block():
    cat = get_catalog()
    for addr in ("F2/F2-33", "F2/F2-34", "D1/D1"):
        res = sheet_key_for(_sheet(addr), index=cat)
        assert res.key is None and res.blocked.state == "blocked", addr
        assert res.blocked.reason_code == "sheet_name_borrowed" and addr in res.blocked.reason


def test_live_cells_under_borrowed_sheets_are_exactly_f2_two():
    """design §2.4「现算影响 F2-33/B20、F2-34/B20 两格」：遍历真实目录全部有效 cell 复算。

    spec wp-deeplink-locate-coverage-closure 逐格对模板复核后这两格（种子坐标与模板不符）已停用，借名 sheet 下不再有
    有效 cell；借名判定本身由 test_borrowed_and_ambiguous_names_block 覆盖。"""
    cat = get_catalog()
    hit = sorted(a for a, c in cat.cells_by_addr_id.items() if not c.get("deprecated")
                 and sheet_key_for(cat.sheets_by_addr_id[a.rsplit("/", 1)[0]], index=cat).key is None)
    assert len(cat.cells_by_addr_id) > 400
    assert hit == []
    assert all(cat.cells_by_addr_id[a].get("deprecated") for a in ("F2/F2-33/B20", "F2/F2-34/B20"))


# ── bind_wp_code ─────────────────────────────────────────────────────────────

async def test_sheet_level_paper_preferred_over_parent(world):
    db, pid = world["db"], world["pid"]
    assert await bind_wp_code(db, pid, _sheet("D2/D2-2")) == "D2-2"
    assert await bind_wp_code(db, pid, _sheet("E1/E1-14")) == "E1"
    got = await read_entry_cell(db, project_id=pid, year=None, entry=_sheet("D2/D2-2"), cell="B5", index=get_catalog())
    assert (got.bound_wp_code, got.read.value, got.read.wp_id) == ("D2-2", Decimal("2"), world["papers"]["D2-2"])


async def test_sheet_level_paper_without_data_does_not_fall_back(world):
    """sheet 级底稿存在但没有该格 ⇒ 照实 missing，不回落父底稿。"""
    got = await read_entry_cell(world["db"], project_id=world["pid"], year=None, entry=_sheet("D2/D2-2"),
                                cell="Z9", index=get_catalog())
    assert (got.bound_wp_code, got.read.state, got.read.reason_code) == ("D2-2", "missing", "cell_empty")


# ── read_formula_cell ────────────────────────────────────────────────────────

async def test_two_sheets_same_a1_each_reads_its_own(world):
    cat = get_catalog()
    a = await read_formula_cell(world["db"], project_id=world["pid"], year=None, wp_code="E1",
                                sheet_text="货币资金审定表E1-1", cell="C10", index=cat)
    b = await read_formula_cell(world["db"], project_id=world["pid"], year=None, wp_code="E1",
                                sheet_text="E1-14", cell="C10", index=cat)
    assert (a.read.value, b.read.value) == (Decimal("100.50"), Decimal("0.125"))
    assert (a.read.sheet_key, b.read.sheet_key) == ("货币资金审定表E1-1", "货币资金分析表E1-14")
    assert a.bound_wp_code == b.bound_wp_code == "E1"


async def test_not_in_catalog_reads_by_original_text(world):
    got = await read_formula_cell(world["db"], project_id=world["pid"], year=None, wp_code="ZZ1",
                                  sheet_text="自定义表", cell="A1", index=get_catalog())
    assert (got.read.state, got.read.value, got.bound_wp_code) == ("ok", Decimal("3.5"), "ZZ1")


async def test_sheet_not_found_in_catalog_parent_reads_raw_text(world):
    """父级在目录、表名目录里没有 ⇒ 按原文读（不拼伪地址、不取首格）。"""
    got = await read_formula_cell(world["db"], project_id=world["pid"], year=None, wp_code="E1",
                                  sheet_text="1-1", cell="B2", index=get_catalog())
    assert (got.read.state, got.read.value, got.read.sheet_key) == ("ok", Decimal("9"), "1-1")


@pytest.mark.parametrize("wp_code, sheet_text", [("F2", "底稿目录"), ("A18", "向监管部门报送审计小结的函")])
async def test_ambiguous_or_forbidden_does_not_read(world, wp_code, sheet_text, monkeypatch):
    async def _boom(*_a, **_k):
        raise AssertionError("多义 / 禁止别名不应读取")

    monkeypatch.setattr(wp_cell_target, "resolve_wp_cell", _boom)
    got = await read_formula_cell(world["db"], project_id=world["pid"], year=None, wp_code=wp_code,
                                  sheet_text=sheet_text, cell="B20", index=get_catalog())
    assert (got.read.state, got.read.reason_code, got.bound_wp_code) == ("blocked", "sheet_ambiguous", None)
    assert got.read.reason and got.read.candidates


async def test_refinement_is_skipped_on_sqlite(world):
    got = await read_formula_cell(world["db"], project_id=world["pid"], year=None, wp_code="E1",
                                  sheet_text="E1-14", cell="Z1", index=get_catalog())
    assert (got.read.state, got.read.reason_code) == ("missing", "cell_empty")


# ── effective_catalog（R2-F7） ────────────────────────────────────────────────

async def test_effective_catalog_unlocked_is_current(world):
    assert await effective_catalog(world["db"], world["pid"]) is get_catalog()
    assert await effective_catalog(world["db"], None) is get_catalog()


async def _set_lock(db, pid, version: str) -> None:
    project = await db.get(Project, pid)
    project.acnr_registry_version = version
    await db.flush()
    db.info.pop("acnr_locked_version", None)


async def test_locked_project_judges_identity_by_locked_catalog(world):
    """锁定上一批目录：I1 的「I1-1」在锁定目录里不是别名 ⇒ 按原文读「I1-1」表（22），当前目录读审定表I1（11）。"""
    db, pid = world["db"], world["pid"]
    current = await read_formula_cell(db, project_id=pid, year=None, wp_code="I1", sheet_text="I1-1", cell="C5",
                                      index=await effective_catalog(db, pid))
    assert current.read.value == Decimal("11")
    await _set_lock(db, pid, _OLD_VERSION)
    locked_index = await effective_catalog(db, pid)
    assert locked_index.registry_version == _OLD_VERSION
    locked = await read_formula_cell(db, project_id=pid, year=None, wp_code="I1", sheet_text="I1-1", cell="C5",
                                     index=locked_index)
    assert locked.read.value == Decimal("22")


async def test_locked_snapshot_missing_raises(world):
    await _set_lock(world["db"], world["pid"], "19990101000000")
    with pytest.raises(VersionNotFoundError):
        await effective_catalog(world["db"], world["pid"])


# ── 异常 ─────────────────────────────────────────────────────────────────────

async def test_database_error_propagates():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession)() as db:
            with pytest.raises(OperationalError):
                await read_entry_cell(db, project_id=uuid.uuid4(), year=None, entry=_sheet("D2/D2-2"),
                                      cell="B5", index=get_catalog())
    finally:
        await engine.dispose()


def test_module_does_not_touch_parsed_data_or_extract():
    tree = ast.parse(inspect.getsource(wp_cell_target))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "extract_custom_cells" not in names and "parsed_data" not in names
    assert "resolve_wp_cell" in names


# ── 真 PG（回滚事务，自带样本） ───────────────────────────────────────────────
#
# 🔴 2026-11-26：原先两条用例只读库里现成的底稿，判据随库内容漂移 —— 共享库只剩 7 个 A1 数值格
#    时「至少 20 格」恒红，CI 一次性空库又只能 skip（两头都不是在测代码）。改为在回滚事务里自建
#    【测试】项目与已知样本：判据只由本用例写入的数据决定，空库 / 共享库都真跑；库里已有的真实底稿
#    照样逐值比对（不计入门槛，只要读到就必须相等），事务结束一律回滚，不留任何数据。

#: 值比对样本：每张表一个 A1 数值格（含小数、负数、零、大数），表名不在目录里 ⇒ 按原文读
_PG_VALUE_SAMPLES = [(f"【测试】取值表{i:02d}", f"C{i + 5}", value) for i, value in enumerate([
    "100.50", "-3", "0", "1234567.89", "0.125", "42", "-0.01", "7", "999999999.99", "3.5",
    "12", "-12.75", "5000", "0.5", "88", "-1", "250.25", "60", "19.99", "1",
    "-77.7", "300", "0.001", "64",
])]
#: 目录内命中样本（走 read_entry_cell 分支）：E1 的两张目录表，项目里没有 sheet 级底稿 ⇒ 绑到 E1 本身
_PG_CATALOG_SAMPLES = [("货币资金审定表E1-1", "C10", "100.50"), ("货币资金分析表E1-14", "C10", "0.125")]


async def _pg_rollback(fn):
    """在 PG 上开一个事务跑 ``fn(session)``，结束一律回滚。"""
    from app.core.config import settings

    eng = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with async_sessionmaker(eng, expire_on_commit=False)() as s:
            try:
                return await fn(s)
            finally:
                await s.rollback()
    finally:
        await eng.dispose()


async def _seed_pg_project(s) -> uuid.UUID:
    pid = uuid.uuid4()
    s.add(Project(id=pid, name=f"【测试】ACNR 取值接线 PG {pid.hex[:8]}", client_name="【测试】ACNR 取值接线",
                  status=ProjectStatus.execution, template_type="listed", report_scope="standalone",
                  audit_year=2025, scenario="normal"))
    await s.flush()
    return pid


async def _seed_pg_paper(s, pid: uuid.UUID, wp_code: str, *, parsed=None, file_path: str = "") -> uuid.UUID:
    idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=wp_code, wp_name=f"【测试】{wp_code}")
    s.add(idx)
    await s.flush()
    wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path=file_path,
                      source_type=WpSourceType.template, parsed_data=parsed)
    s.add(wp)
    await s.flush()
    return wp.id


_PG_SAMPLE = (
    "SELECT w.project_id, i.wp_code FROM working_paper w JOIN wp_index i ON i.id = w.wp_index_id "
    "WHERE COALESCE(w.is_deleted, false) = false AND COALESCE(i.is_deleted, false) = false AND {cond} "
    "AND w.project_id = :pid ORDER BY i.wp_code LIMIT 1"
)


@pytest.mark.pg_only
@pytest.mark.parametrize("cond, code", [
    ("EXISTS (SELECT 1 FROM checklist_responses c WHERE c.wp_id = w.id)", "value_in_form_storage"),
    ("(w.parsed_data -> 'html_data') IS NULL AND NULLIF(w.file_path, '') IS NOT NULL "
     "AND NOT EXISTS (SELECT 1 FROM checklist_responses c WHERE c.wp_id = w.id)", "value_in_file"),
])
async def test_pg_reason_refinement(cond, code):
    async def run(s):
        pid = await _seed_pg_project(s)
        # 表单录入：数据只在 checklist_responses；只有文件：既无 html_data 也无表单行，只有底稿文件
        form_wp = await _seed_pg_paper(s, pid, "ZZFORM1", parsed={}, file_path="ZZFORM1.xlsx")
        await s.execute(text(
            "INSERT INTO checklist_responses (project_id, wp_id, item_id, remark) VALUES (:p, :w, 'ZZFORM1-r1', '1')"
        ), {"p": pid, "w": form_wp})
        await _seed_pg_paper(s, pid, "ZZFILE1", parsed={}, file_path="ZZFILE1.xlsx")

        row = (await s.execute(text(_PG_SAMPLE.format(cond=cond)), {"pid": pid})).first()
        assert row is not None, f"自建样本里没有 {code} 形态的底稿（样本构造与判据不符）"
        _, wp_code = row
        got = await read_formula_cell(s, project_id=pid, year=None, wp_code=wp_code, sheet_text="不存在的表",
                                      cell="ZZ9999", index=get_catalog())
        assert (got.read.state, got.read.reason_code) == ("missing", code), (wp_code, got.read)
        assert got.read.reason in (wp_cell_target.FORM_STORAGE_REASON, wp_cell_target.FILE_ONLY_REASON)
        assert s.info[wp_cell_target._STORAGE_MEMO_KEY][got.read.wp_id] == code

    await _pg_rollback(run)


@pytest.mark.pg_only
async def test_pg_values_equal_stored_cells():
    """带 html_data 的底稿：每张表抽一个数值格，经 read_formula_cell 按原文表名读回的值与库内值相等。

    自建样本覆盖两条取值分支：目录外按原文读（24 张）与目录内命中（E1 两张）；门槛只由它们决定，
    库里已有的真实底稿同样逐值比对。
    """
    from app.services.address_registry import extract_custom_cells

    async def run(s):
        pid = await _seed_pg_project(s)
        html = {sheet: {"cells": {cell: value}} for sheet, cell, value in _PG_VALUE_SAMPLES}
        await _seed_pg_paper(s, pid, "ZZVAL1", parsed={"html_data": html}, file_path="ZZVAL1.xlsx")
        e1 = {sheet: {"cells": {cell: value}} for sheet, cell, value in _PG_CATALOG_SAMPLES}
        await _seed_pg_paper(s, pid, "E1", parsed={"html_data": e1}, file_path="E1.xlsx")

        rows = (await s.execute(text(
            "SELECT w.project_id, i.wp_code, w.parsed_data FROM working_paper w JOIN wp_index i ON i.id = w.wp_index_id "
            "WHERE COALESCE(w.is_deleted, false) = false AND (w.parsed_data -> 'html_data') IS NOT NULL"))).all()
        checked_seeded = 0
        cat = get_catalog()
        for row_pid, wp_code, parsed in rows:
            seen = set()
            for rec in extract_custom_cells(parsed):
                if rec.sheet in seen or rec.value in (None, ""):
                    continue
                try:
                    expected = Decimal(str(rec.value).strip())
                except Exception:  # noqa: BLE001 —— 文本格不在本例范围
                    continue
                if not expected.is_finite():
                    continue
                seen.add(rec.sheet)
                got = await read_formula_cell(s, project_id=row_pid, year=None, wp_code=wp_code, sheet_text=rec.sheet,
                                              cell=rec.cell, index=cat)
                if got.read.reason_code in ("sheet_name_borrowed", "sheet_ambiguous"):
                    continue
                if got.bound_wp_code != wp_code:
                    continue  # 目录判到 sheet 级底稿，属绑定规则，不在本例比对
                assert got.read.state in ("ok", "blocked"), (wp_code, rec.sheet, rec.cell, got.read)
                if got.read.state == "ok":
                    assert got.read.value == expected, (wp_code, rec.sheet, rec.cell)
                    if row_pid == pid:
                        checked_seeded += 1
        return checked_seeded

    assert await _pg_rollback(run) == len(_PG_VALUE_SAMPLES) + len(_PG_CATALOG_SAMPLES)
