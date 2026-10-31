"""报表行新鲜度判据（spec formula-hub-integrity-closure 任务 14；需求 5.1 读取部分、5.5；ADR-FHIC-04；D13-A；变异 #20）。

被测 = ``services/report_freshness``：汇总类判据 ``stale_clause``（SQL）与逐行判据 ``is_effectively_stale``；夹具的行形态与
期望见 ``_freshness_world.SHAPES``（存量 NULL / 新鲜 / 公式改了 / 计算失败 / 口径留空 / 本项目覆盖 / 旧版本）。

- ``test_legacy_rows_read_as_stale``：计算版本为空的存量行（``is_stale = false``）两种读者都判过期（需求 5.5；变异 #20
  「stale_clause 去 calc_version 条件」必须让它红 —— 断言走真 SQL 计数与明细）；
- ``test_formula_text_change_reads_stale``：生成时公式与当前生效公式（准则行 ⊕ 本项目行）规范化后不同 ⇒ 逐行判过期；
  只差首尾空白不算；本项目覆盖与生成时一致不算；
- 报表视图 / 单表导出逐行给出 ``is_stale`` + ``calc_error`` + ``blank_reason``（TestClient 真发请求）；
- 真 PG（``pg_only``，只连快照库，``pg_tx`` 结束回滚）：V229 两列类型与可空、PG 方言下同一组期望。
"""
from __future__ import annotations

import io
from types import SimpleNamespace

import openpyxl
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from app.models.report_models import FinancialReport
from app.services import report_freshness as rf
from tests.formula_hub._freshness_world import (
    BLANK,
    BY_CODE,
    CALC_ERROR,
    ROW_STALE,
    SHAPES,
    SUMMARY_STALE,
    YEAR,
    pg_world,
    report_client,
    sqlite_world,
)

VIEW = "/api/reports/{pid}/{year}/balance_sheet"
EXPORT = VIEW + "/export-excel"


def _row(**fields):
    base = {"is_stale": False, "calc_version": rf.CALC_VERSION, "formula_used": "TB('1001','期末余额')",
            "calc_error": None, "blank_reason": None}
    return {**base, **fields}


# ── 纯判据 ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("fields", "effective", "expected"), [
    ({}, "TB('1001','期末余额')", False),
    ({"calc_version": None}, "TB('1001','期末余额')", True),
    ({"calc_version": rf.CALC_VERSION - 1}, "TB('1001','期末余额')", True),
    ({"calc_version": rf.CALC_VERSION + 1}, "TB('1001','期末余额')", True),
    ({"is_stale": True}, "TB('1001','期末余额')", True),
    ({"formula_used": "  TB('1001','期末余额')\n"}, "TB('1001','期末余额')", False),
    ({}, "TB('1002','期末余额')", True),
    ({}, None, True),
    ({"formula_used": None}, None, False),
    ({"formula_used": ""}, "   ", False),
])
def test_is_effectively_stale_cases(fields, effective, expected):
    row = _row(**fields)
    assert rf.is_effectively_stale(row, effective) is expected
    assert rf.is_effectively_stale(SimpleNamespace(**row), effective) is expected  # ORM 行与映射同口径


def test_stale_clause_sql_text():
    """两种方言都编出「is_stale 为真 OR calc_version 与当前版本不同（NULL 算不同）」；表对象与 ORM 类同一判据。"""
    pg = str(rf.stale_clause().compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert pg == f"financial_report.is_stale = true OR financial_report.calc_version IS DISTINCT FROM {rf.CALC_VERSION}"
    table = str(rf.stale_clause(FinancialReport.__table__).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert table == pg
    lite = str(rf.stale_clause().compile(dialect=sqlite.dialect()))
    assert lite == "financial_report.is_stale = 1 OR financial_report.calc_version IS NOT ?"


def test_row_status_and_note():
    status = rf.row_status(_row(is_stale=True, calc_error="除数为 0"), "TB('1001','期末余额')")
    assert status == {"is_stale": True, "calc_error": "除数为 0", "blank_reason": None}
    assert rf.status_note(status) == "已过期；计算失败：除数为 0"
    blank = rf.row_status(_row(blank_reason="取数超出合并口径"), "TB('1001','期末余额')")
    assert blank == {"is_stale": False, "calc_error": None, "blank_reason": "取数超出合并口径"}
    assert rf.status_note(blank) == "留空：取数超出合并口径"
    assert rf.status_note(rf.row_status(_row(), "TB('1001','期末余额')")) == ""


# ── SQLite：真 SQL 判据 + 读者 ───────────────────────────────────────────────────────────


async def _stale_codes_sql(world) -> list[str]:
    result = await world.session.execute(
        sa.select(FinancialReport.row_code).where(
            FinancialReport.project_id == world.project_id, FinancialReport.year == YEAR,
            FinancialReport.is_deleted == sa.false(), rf.stale_clause()))
    return sorted(result.scalars().all())


async def _row_stale_codes(world) -> list[str]:
    formulas = await rf.load_effective_formulas(world.session, world.project_id)
    rows = (await world.session.execute(sa.select(FinancialReport).where(
        FinancialReport.project_id == world.project_id, FinancialReport.year == YEAR,
        FinancialReport.is_deleted == sa.false()))).scalars().all()
    return sorted(r.row_code for r in rows if rf.is_effectively_stale(r, rf.formula_for(formulas, r)))


async def _assert_legacy_reads_stale(world) -> None:
    legacy = [s.code for s in SHAPES if s.calc_version is None]
    assert legacy == ["FHT14-001"] and not BY_CODE["FHT14-001"].is_stale  # 夹具非空转：存量行未标过期
    stale = await _stale_codes_sql(world)
    assert stale == SUMMARY_STALE and set(legacy) <= set(stale), stale
    counts = await rf.count_summary(world.session, world.project_id, YEAR)
    assert counts == rf.FreshnessCounts(total=len(SHAPES), stale=len(SUMMARY_STALE),
                                        calc_error=len(CALC_ERROR), blank=len(BLANK)), counts
    listed = await rf.list_rows(world.session, world.project_id, YEAR, rf.stale_clause())
    assert [r["row_code"] for r in listed] == SUMMARY_STALE and all(r["is_stale"] for r in listed)
    assert set(legacy) <= set(await _row_stale_codes(world))


@pytest.mark.asyncio
async def test_legacy_rows_read_as_stale():
    """需求 5.5 / D13-A：计算版本为空的存量行读取侧判过期（汇总计数、明细、逐行三处）；已删行与上一年度不计。"""
    async with sqlite_world() as world:
        await _assert_legacy_reads_stale(world)


@pytest.mark.asyncio
async def test_formula_text_change_reads_stale():
    """需求 5.1：生成时公式与当前生效公式规范化后不同 ⇒ 逐行判过期；汇总判据不含这一条（由任务 15 同事务标过期补上）。"""
    async with sqlite_world() as world:
        assert await _row_stale_codes(world) == ROW_STALE
        assert "FHT14-003" in ROW_STALE and "FHT14-003" not in SUMMARY_STALE
        assert "FHT14-002" not in ROW_STALE  # 只差首尾空白
        assert "FHT14-006" not in ROW_STALE  # 有效定义取本项目覆盖（准则行公式不同）
        formulas = await rf.load_effective_formulas(world.session, world.project_id)
        assert rf.formula_for(formulas, {"report_type": "balance_sheet", "row_code": "FHT14-006"}) == "TB('1601','期末余额')"


def _assert_view(rows: list[dict]) -> None:
    got = {r["row_code"]: r for r in rows if r["row_code"].startswith("FHT14-")}
    assert sorted(got) == sorted(BY_CODE)
    for code, shape in BY_CODE.items():
        assert (got[code]["is_stale"], got[code]["calc_error"], got[code]["blank_reason"]) == (
            shape.row_stale, shape.calc_error, shape.blank_reason), code


def _assert_export(content: bytes) -> None:
    ws = openpyxl.load_workbook(io.BytesIO(content)).active
    header, *body = list(ws.iter_rows(values_only=True))
    assert list(header) == ["行次代码", "项目", "期末余额", "年初余额", "说明"]
    notes = {r[0]: (r[4] or "") for r in body}
    for code, shape in BY_CODE.items():
        expected = rf.status_note({"is_stale": shape.row_stale, "calc_error": shape.calc_error,
                                   "blank_reason": shape.blank_reason})
        assert notes[code] == expected, code
    assert notes["FHT14-001"] == "已过期" and notes["FHT14-005"] == "留空：取数超出合并口径"


def test_report_view_and_export_rows():
    """报表视图逐行 is_stale / calc_error / blank_reason；单表导出「说明」列同口径（TestClient 真发请求）。"""
    with report_client(sqlite_world(tag="fh_fresh_view")) as (client, world):
        view = client.get(VIEW.format(pid=world.project_id, year=YEAR))
        assert view.status_code == 200, view.text
        _assert_view(view.json())
        export = client.get(EXPORT.format(pid=world.project_id, year=YEAR))
        assert export.status_code == 200, export.text
        _assert_export(export.content)


# ── 真 PG（只连快照库）──────────────────────────────────────────────────────────────────


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_v208_columns_on_snapshot(pg_tx):
    """V229：calc_version integer、calc_error varchar(500)，均可空（快照库已按 MigrationRunner 执行）。"""
    rows = (await pg_tx.execute(sa.text(
        "SELECT column_name, data_type, character_maximum_length, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'financial_report' "
        "AND column_name IN ('calc_version', 'calc_error') ORDER BY column_name"))).all()
    assert [tuple(r) for r in rows] == [("calc_error", "character varying", 500, "YES"),
                                        ("calc_version", "integer", None, "YES")]


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_legacy_rows_read_as_stale_pg():
    """同一组期望在 PG 方言（IS DISTINCT FROM）下成立。"""
    async with pg_world() as world:
        await _assert_legacy_reads_stale(world)
        assert await _row_stale_codes(world) == ROW_STALE


@pytest.mark.pg_only
def test_report_view_and_export_rows_pg():
    with report_client(pg_world(tag="fh_fresh_view_pg")) as (client, world):
        view = client.get(VIEW.format(pid=world.project_id, year=YEAR))
        assert view.status_code == 200, view.text
        _assert_view(view.json())
        export = client.get(EXPORT.format(pid=world.project_id, year=YEAR))
        assert export.status_code == 200, export.text
        _assert_export(export.content)
