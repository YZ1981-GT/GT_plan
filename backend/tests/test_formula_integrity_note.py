"""NOTE 真实读库、行列定位和来源记录；所有数据仅在内存 SQLite。"""
from decimal import Decimal

import pytest

from app.services.formula_inputs import collect
from app.services.report_engine import ReportFormulaParser
from tests.formula_integrity_support import add_note, note_table
from tests.formula_integrity_support import integrity_world as integrity_world


@pytest.mark.parametrize("column,expected", [(None, "23.50"), ("期初", "7.25"),
                                             ("期末余额", "23.50"), ("期初余额", "7.25")])
async def test_formula_integrity_note_full_reference_and_source(integrity_world, column, expected):
    world = integrity_world
    await add_note(world, note_table())
    await add_note(world, note_table("999", "888"), project=world.other)
    await add_note(world, note_table("777", "666"), year=2024)
    parser = ReportFormulaParser(world.db, world.project.id, 2025)
    formula = "NOTE('五、1','合计'" + (f",'{column}')" if column else ")")
    with collect() as inputs:
        result = await parser.execute_with_status(formula, {})
    assert result.ok, result.errors
    assert result.value == Decimal(expected)
    assert len(inputs) == 1
    atom = inputs[0]
    assert (atom.kind, atom.key, Decimal(str(atom.value))) == ("NOTE", formula, Decimal(expected))
    assert atom.source_ref == "disclosure_note:五、1"
    assert atom.source_project_id == world.project.id


@pytest.mark.parametrize("value", [None, "", "  ", "非金额", True, False, "NaN", "Infinity", "-Infinity"])
async def test_formula_integrity_note_invalid_value_is_failure(integrity_world, value):
    world = integrity_world
    await add_note(world, note_table(value))
    result = await ReportFormulaParser(world.db, world.project.id, 2025).execute_with_status(
        "NOTE('五、1','合计')", {})
    assert not result.ok
    assert result.value is None
    assert result.errors


@pytest.mark.parametrize("value", [0, "0", "-0.00"])
async def test_formula_integrity_note_real_zero_is_success(integrity_world, value):
    world = integrity_world
    await add_note(world, note_table(value))
    result = await ReportFormulaParser(world.db, world.project.id, 2025).execute_with_status(
        "NOTE('五、1','合计')", {})
    assert result.ok, result.errors
    assert result.value == Decimal(0)


@pytest.mark.parametrize("shape,reason", [
    ("missing", "没有章节"), ("other_project", "没有章节"),
    ("other_year", "没有章节"), ("deleted", "没有章节"),
    ("row_missing", "没有「合计」行"), ("duplicate_rows", "行出现多次"),
    ("column_missing", "没有「期初」列"), ("duplicate_columns", "列「期初」出现多次"),
    ("short_values", "表头与数据列数不一致"), ("ambiguous_tables", "多张表格"),
])
async def test_formula_integrity_note_missing_and_ambiguous_fail_closed(integrity_world, shape, reason):
    world = integrity_world
    table = note_table()
    column = "期初"
    if shape == "row_missing":
        table["rows"][0]["label"] = "明细"
    elif shape == "duplicate_rows":
        table["rows"].append(dict(table["rows"][0]))
    elif shape == "column_missing":
        table["headers"] = ["项目", "本期发生额", "累计计提"]
    elif shape == "duplicate_columns":
        table["headers"] = ["项目", "期初", "期初"]
    elif shape == "short_values":
        table["rows"][0]["values"] = ["3"]
    elif shape == "ambiguous_tables":
        table = {"_tables": [dict(note_table("1"), name="甲"), dict(note_table("2"), name="乙")]}
    if shape != "missing":
        await add_note(world, table, project=world.other if shape == "other_project" else world.project,
                       year=2024 if shape == "other_year" else 2025, deleted=shape == "deleted")
    with collect() as inputs:
        result = await ReportFormulaParser(world.db, world.project.id, 2025).execute_with_status(
            f"NOTE('五、1','合计','{column}')", {})
    assert not result.ok
    assert result.value is None
    assert reason in "；".join(result.errors)
    assert inputs == []


async def test_formula_integrity_note_prefers_main_and_caches_full_three_arg_key(integrity_world):
    world = integrity_world
    table = note_table("13.25", "2.50")
    table["_tables"] = [dict(note_table("999", "888"), name="子表")]
    await add_note(world, table)
    with collect() as inputs:
        result = await ReportFormulaParser(world.db, world.project.id, 2025).execute_with_status(
            "NOTE('五、1','合计')+NOTE('五、1','合计','期初')+NOTE('五、1','合计','期初')", {})
    assert result.ok, result.errors
    assert result.value == Decimal("18.25")
    assert [(a.key, Decimal(str(a.value))) for a in inputs] == [
        ("NOTE('五、1','合计')", Decimal("13.25")),
        ("NOTE('五、1','合计','期初')", Decimal("2.50")),
    ]
