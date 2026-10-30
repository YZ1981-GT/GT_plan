"""附注公式按显示视图生效（spec note-chain-followup-optimizations R1）。SQLite 内存库 + 真 ORM。

判据：①底稿来源章节（``sub_table_data`` 投影）上，预设公式按投影表算、写回 ``sub_table_data`` 的源行业务键，跳过的
可扩位行不让写入错位，表对象包装照样写 ②底稿已有不同值时预设公式不改写、回报差异（``kept_workpaper``）③用户公式照常
覆盖并标 ``overrode_workpaper`` ④隐藏的旧 ``_tables`` 与旧 ``_formulas`` 不再参与 ⑤公式列表 / 目标清单 / 保存校验 /
覆盖率都按投影表 ⑥非底稿来源章节的视图就是存储本身。
"""
from __future__ import annotations

import copy
import uuid

import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.base import Base, ProjectStatus
from app.models.core import Project, User
from app.models.report_models import ContentType, DisclosureNote
from app.services.formula_settings import note_settings
from app.services.note_formula_generator import compute_formula_coverage, execute_note_formulas
from app.services.note_formula_service import preview_records
from app.services.note_formula_tables import formula_targets, formula_view, iter_note_tables, write_view_cell

YEAR = 2025
SECTION = "八、5"
AGING = "（1）按账龄披露应收账款"
COLUMNS = [
    {"key": "label", "label": "账 龄", "is_label": True},
    {"key": "end_amount", "label": "期末数", "format": "amount"},
    {"key": "prior_amount", "label": "期初数", "format": "amount"},
]


def _rows(total_end=None):
    return [
        {"label": "1年以内（含1年）", "end_amount": 800.0, "prior_amount": 600.0},
        {"label": "……", "row_type": "expandable"},  # 投影跳过 ⇒ 后面的显示行号与源行号错开一位
        {"label": "1至2年", "end_amount": 200.0, "prior_amount": None},
        {"label": "合 计", "end_amount": total_end, "prior_amount": None, "is_total": True},
    ]


def _workpaper_td(*, total_end=None, wrap=False, legacy_tables=False, user_formulas=None, stored_formulas=False):
    rows = _rows(total_end)
    td = {
        "_source": "workpaper",
        "_last_sync_wp_id": str(uuid.uuid4()),
        "sub_table_data": {AGING: {"rows": rows} if wrap else rows},
        "_sub_table_columns": {AGING: copy.deepcopy(COLUMNS)},
    }
    if legacy_tables:  # 旧生成器留下、编辑器看不见的存储表（结构与投影表不同：4 行 × 3 个金额列）
        td["_tables"] = [{"name": "旧表", "headers": ["项目", "期末余额", "期初余额", "本期增加"],
                          "rows": [{"label": "甲", "values": [1.0, 2.0, 3.0]}, {"label": "乙", "values": [3.0, 4.0, 5.0]},
                                   {"label": "丙", "values": [5.0, 6.0, 7.0]},
                                   {"label": "合计", "values": [None, None, None], "is_total": True}]}]
    if user_formulas is not None:
        td["_user_formulas"] = user_formulas
    if stored_formulas:
        td["_formulas"] = {"0:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)", "category": "auto_calc"}}
    return td


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[User.__table__, Project.__table__, DisclosureNote.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    pid = uuid.uuid4()
    async with factory() as s:
        s.add(Project(id=pid, name="甲_2025", client_name="甲公司", template_type="soe",
                      report_scope="standalone", status=ProjectStatus.execution))
        await s.commit()

    async def add(table_data):
        async with factory() as s:
            s.add(DisclosureNote(project_id=pid, year=YEAR, note_section=SECTION, section_title="应收账款",
                                 content_type=ContentType.table, table_data=table_data))
            await s.commit()

    async def run():
        async with factory() as s:
            result = await execute_note_formulas(s, pid, YEAR, SECTION)
            await s.commit()
            return result

    async def stored():
        async with factory() as s:
            return (await s.execute(sa.select(DisclosureNote.table_data).where(
                DisclosureNote.project_id == pid, DisclosureNote.note_section == SECTION))).scalar_one()

    async def problems(formulas):
        async with factory() as s:
            return await note_settings.target_problems(s, pid, YEAR, SECTION, formulas)

    yield {"add": add, "run": run, "stored": stored, "problems": problems, "factory": factory, "pid": pid}
    await engine.dispose()


def _raw_total(td):
    raw = td["sub_table_data"][AGING]
    return (raw["rows"] if isinstance(raw, dict) else raw)[3]


def test_view_is_the_projection_for_workpaper_sections_and_the_storage_otherwise():
    td = _workpaper_td(legacy_tables=True)
    view = formula_view(td)
    assert view is not td and [t["name"] for _i, t in iter_note_tables(view)] == [AGING], "隐藏的旧表不在视图里"
    assert [r["label"] for r in view["_tables"][0]["rows"]] == ["1年以内（含1年）", "1至2年", "合 计"]
    plain = {"_tables": [{"name": "表", "rows": [{"label": "甲", "values": [1.0]}]}]}
    assert formula_view(plain) is plain, "非底稿来源：视图就是存储本身（就地写即落库位置）"
    empty = {"_source": "workpaper", "sub_table_data": {}, "_tables": plain["_tables"]}
    assert formula_view(empty) is empty, "投影为空时与编辑器同口径，退回存储"


def test_write_view_cell_maps_display_row_to_source_row_and_unwraps_table_objects():
    for wrap in (False, True):
        td = _workpaper_td(wrap=wrap)
        table = formula_view(td)["_tables"][0]
        assert write_view_cell(td, table, 2, 0, 1000.0) is True  # 显示第 3 行 = 源第 4 行（中间跳过一行可扩位）
        assert _raw_total(td)["end_amount"] == 1000.0
        assert table["rows"][2]["values"][0] == 1000.0, "视图行同步更新，供同表后续公式读到新值"
        assert write_view_cell(td, table, 2, 9, 1.0) is False and write_view_cell(td, table, 9, 0, 1.0) is False


async def test_presets_fill_empty_cells_and_write_back_to_sub_table_data(env):
    await env["add"](_workpaper_td(legacy_tables=True))
    result = await env["run"]()
    td = await env["stored"]()
    assert _raw_total(td)["end_amount"] == 1000.0 and _raw_total(td)["prior_amount"] == 600.0
    assert td["_tables"][0]["rows"][3]["values"] == [None, None, None], "隐藏的旧表一格不动"
    assert result["updated"] == 2 and result["anomalies"] == []


async def test_presets_keep_differing_workpaper_values_and_report(env):
    await env["add"](_workpaper_td(total_end=999.0))
    result = await env["run"]()
    td = await env["stored"]()
    assert _raw_total(td)["end_amount"] == 999.0, "底稿是数值权威：预设公式不改写已有的不同值"
    assert _raw_total(td)["prior_amount"] == 600.0, "空格照常补"
    kept = [(r["cell"], r["old"], r["new"]) for r in result["results"] if r["status"] == "kept_workpaper"]
    assert kept == [("2:0", 999.0, 1000.0)], "显示行号（跳过可扩位行后）作目标"
    assert [a["kind"] for a in result["anomalies"]] == ["workpaper_differs"]
    assert "保留底稿值" in result["anomalies"][0]["message"]
    assert result["updated"] == 1


async def test_user_formula_overrides_workpaper_value_and_is_flagged(env):
    await env["add"](_workpaper_td(total_end=999.0, user_formulas=[
        {"target": "2:0", "formula": "cell(0,0) + 1", "category": "auto_calc"}]))
    result = await env["run"]()
    td = await env["stored"]()
    assert _raw_total(td)["end_amount"] == 801.0
    item = next(r for r in result["results"] if r["cell"] == "2:0")
    assert item["status"] == "ok" and item.get("overrode_workpaper") is True
    assert not [r for r in result["results"] if r["status"] == "kept_workpaper"]


async def test_stored_formulas_for_the_old_structure_are_not_applied_to_the_projection(env):
    await env["add"](_workpaper_td(stored_formulas=True))
    result = await env["run"]()
    td = await env["stored"]()
    # 旧 _formulas 的「0:0 = SUM(0:1, 0)」按投影套会把 800 改成 800 + 200；视图是投影时按现算预设
    assert td["sub_table_data"][AGING][0]["end_amount"] == 800.0
    assert _raw_total(td)["end_amount"] == 1000.0
    assert "0:0" not in {r["cell"] for r in result["results"]}


async def test_listing_targets_validation_and_coverage_follow_the_projection(env):
    td = _workpaper_td(legacy_tables=True)
    presets = preview_records(td, SECTION)
    assert {r["target"] for r in presets} == {"2:0", "2:1"}, "预设按投影表的合计行生成（不是隐藏旧表）"
    assert [t["name"] for t in formula_targets(formula_view(td))] == [AGING]
    coverage = compute_formula_coverage(td)
    assert coverage["total_cells"] == 6 and coverage["configured_cells"] == 2
    await env["add"](td)
    assert await env["problems"]([{"target": "2:1", "formula": "cell(0,1)"}]) == []
    issues = await env["problems"]([{"target": "3:2", "formula": "1"}])  # 只在隐藏旧表里存在的格
    assert issues and "超出" in issues[0]["message"], "隐藏旧表不再是可选目标"


async def test_refresh_reports_kept_workpaper_cells_as_formula_differs(env):
    """刷新回执带 ``formula_differs``（前端据此提示核对）；推送后的公式汇总带 ``differs``。"""
    from app.services.note_wp_mapping_service import _apply_final_note_formulas

    await env["add"](_workpaper_td(total_end=999.0))
    async with env["factory"]() as s:
        formulas = await _apply_final_note_formulas(s, env["pid"], YEAR, [SECTION, SECTION])
        await s.rollback()
    assert formulas["formula_differs"] == 1 and formulas["formula_updated"] == 1
    assert formulas["formula_errors"] == []


async def test_positional_source_rows_keep_their_manual_marks_like_formula_push(env):
    """来源行还按位置存（旧 binding 快照迁入：没有业务键、有 ``values``）且标了人工 / 锁定 ⇒ 公式不写（推送同样不写）；
    用户在编辑器里改过的格写的是业务键，模式随之失效、照常按自动算。"""
    td = _workpaper_td()
    rows = td["sub_table_data"][AGING]
    rows[3] = {"label": "合 计", "values": [None, None], "is_total": True,
               "_cell_modes": {"0": "manual", "1": "locked"}}
    await env["add"](copy.deepcopy(td))
    result = await env["run"]()
    stored = await env["stored"]()
    assert stored["sub_table_data"][AGING][3] == rows[3], "人工 / 锁定的位置化格一格不动"
    assert result["updated"] == 0

    rows[3]["end_amount"] = None  # 编辑器写过业务键：这一列不再按位置判模式
    async with env["factory"]() as s:
        note = (await s.execute(sa.select(DisclosureNote).where(DisclosureNote.project_id == env["pid"]))).scalar_one()
        note.table_data = copy.deepcopy(td)
        await s.commit()
    result = await env["run"]()
    stored = await env["stored"]()
    assert stored["sub_table_data"][AGING][3]["end_amount"] == 1000.0
    assert "prior_amount" not in stored["sub_table_data"][AGING][3], "期初列仍按位置锁定，不写"
    assert result["updated"] == 1
