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
from app.models.note_formula_models import NoteFormulaRun
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
            c, tables=[User.__table__, Project.__table__, DisclosureNote.__table__, NoteFormulaRun.__table__]))
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

    yield {"add": add, "run": run, "stored": stored, "factory": factory, "pid": pid}
    await engine.dispose()


async def test_every_table_gets_presets_written_to_tables(env):
    await env["add"](_td(AGING, BAD_DEBT))
    result = await env["run"]()
    td = await env["stored"]()

    t0, t1 = td["_tables"][0]["rows"], td["_tables"][1]["rows"]
    assert t0[2]["values"] == [1000.0, 600.0], "第 1 张表合计 = 明细之和（期初只有一行有数，照加）"
    assert td["rows"][2]["values"] == [1000.0, 600.0], "第 1 张表写进 _tables[0] 后顶层镜像跟着改"
    assert t1[5]["values"][0] == 1000.0 and t1[5]["values"][2] == 65.0, "第 2 张表合计：两个分类相加（其中明细不重复）"
    # 比例 / 损失率不加总：合计行按本行派生（R2.1）—— 比例 100、损失率 = 65 ÷ 1000 × 100
    assert t1[5]["values"][1] == 100.0 and t1[5]["values"][3] == 6.5, "比例 / 损失率按合计行派生，不是各行之和"
    assert [r["values"][4] for r in t1] == [80.0, 855.0, None, 570.0, 285.0, 935.0], "账面价值 = 余额 − 坏账准备"
    assert t1[2]["values"][1] is None, "「其中：」标记行没有比例"
    assert {r["table_index"] for r in result["results"]} == {0, 1}
    # 表一合计 2 格；表二合计 3 格（金额列 0 / 2 / 4）+ 明细行账面价值 4 格（「其中：」标记行不算）+ 合计行比例 / 损失率 2 格
    # （明细行比例 / 损失率与夹具值一致，不算更新）
    assert result["updated"] == 2 + 3 + 4 + 2


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
    td["_tables"][0]["rows"][0]["_cell_modes"] = {"0": "auto"}
    await env["add"](td)
    stale = await env["run"]()
    assert (await env["stored"]())["_tables"][0]["rows"][0]["values"][0] == 200.0, "存过的旧公式指错格（示意）"
    assert stale["updated"] == 1

    fixed = await env["run"](regenerate=True)
    td = await env["stored"]()
    assert "_formulas" not in td
    assert td["_tables"][0]["rows"][2]["values"] == [400.0, 600.0], "改用按当前结构现算的预设"
    assert fixed["updated"] == 2


async def test_formula_writeback_quantizes_decimal_result_to_cents(env):
    """公式内部用 Decimal，写入 JSONB 前按分量化，避免二进制浮点尾差。"""
    table = copy.deepcopy(AGING)
    table["rows"][0]["values"] = [0.1, 0.2]
    table["rows"][1]["values"] = [0.2, 0.1]
    await env["add"](_td(table))

    result = await env["run"]()
    stored = (await env["stored"]())["_tables"][0]["rows"][2]["values"]

    assert result["updated"] == 2
    assert stored == [0.3, 0.3]


async def test_s5_note_run_and_formula_provenance_are_queryable(env):
    await env["add"](_td(AGING, BAD_DEBT))
    result = await env["run"]()
    assert result.get("run_id")
    td = await env["stored"]()
    provenance = td.get("_formula_provenance")
    assert isinstance(provenance, dict) and provenance
    total = provenance["note:八、5!2:0"]
    assert total["calculation_applied"] is True
    assert total["applied_attempt"]["run_id"] == result["run_id"]
    assert total["last_calculation"]["input_count"] == 2
    assert {item["kind"] for item in total["last_calculation"]["inputs"]} == {"CELL"}
    assert total["last_calculation"]["definition_ref"]["kind"] == "preset"

    async with env["factory"]() as session:
        run = await session.get(NoteFormulaRun, uuid.UUID(result["run_id"]))
        assert run is not None
        assert (run.project_id, run.year, run.note_section) == (env["pid"], YEAR, SECTION)
        assert run.status == "succeeded"
        assert run.executed_count > 0 and run.updated_count > 0


async def test_s5_manual_and_locked_cells_record_unapplied_attempts(env):
    td = _td(AGING, BAD_DEBT)
    total = td["_tables"][1]["rows"][5]
    total["values"][0] = 1.0
    total["values"][2] = 2.0
    total["_cell_modes"] = {"0": "manual", "2": "locked"}
    await env["add"](td)
    result = await env["run"]()
    stored = await env["stored"]()
    provenance = stored["_formula_provenance"]
    manual = provenance["note:八、5!t1:5:0"]
    locked = provenance["note:八、5!t1:5:2"]
    assert manual["value_state"] == "manual"
    assert locked["value_state"] == "locked"
    assert manual["calculation_applied"] is False
    assert locked["calculation_applied"] is False
    assert manual["last_calculation"]["calculation_status"] == "succeeded"
    assert locked["last_calculation"]["run_id"] == result["run_id"]


async def test_s5_cell_sources_returns_provenance_and_run_summary(env):
    from app.services.note_cell_sources import diagnose_cell

    await env["add"](_td(AGING))
    result = await env["run"]()
    async with env["factory"]() as session:
        source = await diagnose_cell(
            session, env["pid"], YEAR, SECTION, table_index=0, row=2, col=0,
        )
    assert source["formula_provenance"]["applied_attempt"]["run_id"] == result["run_id"]
    assert source["formula_run"]["id"] == result["run_id"]
    assert source["formula_run"]["status"] == "succeeded"
    assert source["inputs_redacted"] is False


async def test_s5_editor_save_preserves_formula_provenance_sidecar(env):
    from app.services.disclosure_engine import DisclosureEngine

    await env["add"](_td(AGING))
    result = await env["run"]()
    before = await env["stored"]()
    assert before["_formula_provenance"]
    incoming = copy.deepcopy(before)
    expected = copy.deepcopy(incoming.pop("_formula_provenance"))
    incoming.pop("_formula_last_values", None)
    async with env["factory"]() as session:
        note = (await session.execute(sa.select(DisclosureNote).where(
            DisclosureNote.project_id == env["pid"], DisclosureNote.note_section == SECTION,
        ))).scalar_one()
        await DisclosureEngine(session).update_note(note.id, table_data=incoming)
        await session.commit()
    stored = await env["stored"]()
    assert stored["_formula_provenance"] == expected
    assert stored["_formula_provenance"]["note:八、5!2:0"]["applied_attempt"]["run_id"] == result["run_id"]

async def test_ratio_with_blank_numerator_is_skipped_not_written_as_zero(env):
    """比例 / 损失率：分子格为空 ⇒ 不算、不写 0，结果写明原因（R2.1，预设的 ``requires`` 在执行时生效）。

    分母（合计行）有数时，严格求值也会把空分子按 0 算出 0% —— 没有这道判断，「按单项计提」没发生的表会被写满 0。
    """
    table = copy.deepcopy(BAD_DEBT)
    table["rows"][0]["values"] = [None, None, None, None, None]  # 按单项计提：账面余额、坏账准备都没数
    await env["add"](_td(AGING, table))
    result = await env["run"]()
    t1 = (await env["stored"]())["_tables"][1]["rows"]
    assert t1[5]["values"][0] == 900.0, "合计照算（分母有数）"
    assert t1[0]["values"][1] is None and t1[0]["values"][3] is None, "分子为空的比例 / 损失率留空，不写 0"
    skipped = {r["cell"]: r.get("reason") for r in result["results"]
               if r["table_index"] == 1 and r["status"] == "skipped"}
    assert skipped.get("t1:0:1") == "本行金额为空，不算比例"

