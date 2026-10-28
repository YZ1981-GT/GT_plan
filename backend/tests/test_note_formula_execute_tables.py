"""附注公式逐表执行（spec note-pull-header-formula-closure R3 任务 9~10）。SQLite 内存库 + 真 ORM。

判据：①第 2 张起的表有预设公式且写进 ``_tables``（原先只写顶层首表镜像、第 2 张起无公式）②第 1 张表写完顶层镜像
跟着改 ③人工 / 锁定格不动 ④明细全空不写 0（不盖掉公式推送按审定数写入的合计）⑤用户公式按表目标覆盖预设、审核类
不回填 ⑥值没变不算更新 ⑦已删除的附注不执行 ⑧「重新生成」丢掉存过的旧公式。
"""
from __future__ import annotations

import copy
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.base import Base, ProjectStatus
from app.models.core import Project, User
from app.models.report_models import ContentType, DisclosureNote
from app.services.note_formula_generator import execute_note_formulas

YEAR = 2025
SECTION = "八、5"


def _row(label, values, **kw):
    return {"label": label, "values": values, **kw}


AGING = {
    "name": "（1）按账龄披露应收账款", "headers": ["账 龄", "期末数", "期初数"],
    "rows": [_row("1年以内（含1年）", [800.0, 600.0]), _row("1至2年", [200.0, None]),
             _row("合 计", [None, None], is_total=True, row_type="total")],
}
BAD_DEBT = {
    "name": "（2）按坏账准备计提方法分类披露应收账款",
    "headers": ["类 别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值"],
    "_column_groups": [{"group": "账面余额", "start": 1, "span": 2}, {"group": "坏账准备", "start": 3, "span": 2}],
    "rows": [
        _row("按单项计提坏账准备", [100.0, 10.0, 20.0, 20.0, None]),
        _row("按组合计提坏账准备", [900.0, 90.0, 45.0, 5.0, None]),
        _row("其中：", [None] * 5),
        _row("应收中央企业客户", [600.0, 60.0, 30.0, 5.0, None]),
        _row("应收海外企业客户", [300.0, 30.0, 15.0, 5.0, None]),
        _row("合 计", [None] * 5, is_total=True, row_type="total"),
    ],
}


def _td(*tables):
    tables = [copy.deepcopy(t) for t in tables]
    return {"headers": list(tables[0]["headers"]), "rows": copy.deepcopy(tables[0]["rows"]), "_tables": tables}


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

    async def add(table_data, *, deleted=False, section=SECTION):
        async with factory() as s:
            s.add(DisclosureNote(project_id=pid, year=YEAR, note_section=section, section_title="应收账款",
                                 content_type=ContentType.table, table_data=table_data, is_deleted=deleted))
            await s.commit()

    async def run(**kw):
        async with factory() as s:
            result = await execute_note_formulas(s, pid, YEAR, kw.pop("section", SECTION), **kw)
            await s.commit()
            return result

    async def stored(section=SECTION):
        async with factory() as s:
            return (await s.execute(sa.select(DisclosureNote.table_data).where(
                DisclosureNote.project_id == pid, DisclosureNote.note_section == section))).scalar_one()

    yield {"add": add, "run": run, "stored": stored}
    await engine.dispose()


async def test_every_table_gets_presets_written_to_tables(env):
    await env["add"](_td(AGING, BAD_DEBT))
    result = await env["run"]()
    td = await env["stored"]()

    t0, t1 = td["_tables"][0]["rows"], td["_tables"][1]["rows"]
    assert t0[2]["values"] == [1000.0, 600.0], "第 1 张表合计 = 明细之和（期初只有一行有数，照加）"
    assert td["rows"][2]["values"] == [1000.0, 600.0], "第 1 张表写进 _tables[0] 后顶层镜像跟着改"
    assert t1[5]["values"][0] == 1000.0 and t1[5]["values"][2] == 65.0, "第 2 张表合计：两个分类相加（其中明细不重复）"
    assert t1[5]["values"][1] is None and t1[5]["values"][3] is None, "比例 / 损失率不加总"
    assert [r["values"][4] for r in t1] == [80.0, 855.0, None, 570.0, 285.0, 935.0], "账面价值 = 余额 − 坏账准备"
    assert {r["table_index"] for r in result["results"]} == {0, 1}
    # 表一合计 2 格；表二合计 3 格（金额列 0 / 2 / 4）+ 明细行账面价值 4 格（「其中：」标记行不算）
    assert result["updated"] == 2 + 3 + 4


async def test_second_run_reports_no_update(env):
    await env["add"](_td(AGING, BAD_DEBT))
    await env["run"]()
    again = await env["run"]()
    assert again["updated"] == 0 and again["executed"] > 0


async def test_manual_and_locked_cells_are_kept(env):
    td = _td(AGING, BAD_DEBT)
    total = td["_tables"][1]["rows"][5]
    total["values"][0] = 1.0
    total["_cell_modes"] = {"0": "manual", "2": "locked"}
    total["values"][2] = 2.0
    await env["add"](td)
    await env["run"]()
    row = (await env["stored"]())["_tables"][1]["rows"][5]
    assert row["values"][0] == 1.0 and row["values"][2] == 2.0
    assert row["values"][4] == 935.0, "同一行的 auto 格照算"


async def test_empty_details_keep_pushed_total(env):
    aging = copy.deepcopy(AGING)
    for r in aging["rows"][:2]:
        r["values"] = [None, None]
    aging["rows"][2]["values"] = [500.0, 300.0]  # 公式推送按审定数写入的合计（明细未取到）
    await env["add"](_td(aging))
    result = await env["run"]()
    assert (await env["stored"]())["_tables"][0]["rows"][2]["values"] == [500.0, 300.0]
    reasons = {r["reason"] for r in result["results"] if r["status"] == "skipped"}
    assert reasons == {"引用的单元格都没有数"} and result["updated"] == 0


async def test_user_formulas_target_tables_and_checks_are_not_written(env):
    td = _td(AGING, BAD_DEBT)
    td["_user_formulas"] = [
        {"target": "t1:5:0", "formula": "cell(0,0) + cell(1,0) + 1", "category": "auto_calc"},
        {"target": "t1:5:2", "formula": "SUM(0:1, 2)", "category": "logic_check"},
    ]
    await env["add"](td)
    result = await env["run"]()
    row = (await env["stored"]())["_tables"][1]["rows"][5]
    assert row["values"][0] == 1001.0, "用户公式按表目标覆盖预设"
    assert row["values"][2] is None, "审核类公式不回填（同目标的预设被用户集覆盖）"
    assert any(r["cell"] == "t1:5:2" and r["reason"] == "审核类公式不回填单元格" for r in result["results"])


async def test_deleted_note_is_not_executed(env):
    await env["add"](_td(AGING), deleted=True)
    result = await env["run"]()
    assert result["executed"] == 0
    assert (await env["stored"]())["_tables"][0]["rows"][2]["values"] == [None, None]


async def test_regenerate_drops_stale_stored_formulas(env):
    td = _td(AGING)
    td["_formulas"] = {"0:0": {"type": "vertical_sum", "expression": "SUM(1:2, 0)", "category": "auto_calc"}}
    await env["add"](td)
    stale = await env["run"]()
    assert (await env["stored"]())["_tables"][0]["rows"][0]["values"][0] == 200.0, "存过的旧公式指错格（示意）"
    assert stale["updated"] == 1

    fixed = await env["run"](regenerate=True)
    td = await env["stored"]()
    assert "_formulas" not in td
    assert td["_tables"][0]["rows"][2]["values"] == [400.0, 600.0], "改用按当前结构现算的预设"
    assert fixed["updated"] == 2
