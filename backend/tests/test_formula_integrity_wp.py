"""WP 公式取数完整性：真实模型与内存 SQLite，不导入应用或共享引擎。"""
from decimal import Decimal

import pytest

from app.services.formula_engine import FormulaEvalError, WPExecutor
from tests.formula_integrity_support import add_wp
from tests.formula_integrity_support import integrity_world as integrity_world


async def test_formula_integrity_fixture_is_explicitly_isolated(integrity_world):
    world = integrity_world
    assert world.db.get_bind().dialect.name == "sqlite"
    assert world.project.audit_year == world.other.audit_year == 2025
    assert world.project.id != world.other.id


@pytest.mark.parametrize("year,reason", [
    (None, "缺少本次审计年度"), (True, "本次审计年度无效"),
    (False, "本次审计年度无效"), ("2025", "本次审计年度无效"),
    (2024, "底稿年度与项目年度不符"),
])
async def test_formula_integrity_wp_requires_matching_explicit_year(integrity_world, year, reason):
    world = integrity_world
    await add_wp(world, "E1", {"audited_amount": "23.50"})
    with pytest.raises(FormulaEvalError, match=reason):
        await WPExecutor.execute(world.db, world.project.id, "E1", year=year)


async def test_formula_integrity_wp_rejects_unknown_project_year(integrity_world):
    world = integrity_world
    world.project.audit_year = None
    await add_wp(world, "E1", {"audited_amount": "23.50"})
    with pytest.raises(FormulaEvalError, match="项目未设置审计年度"):
        await WPExecutor.execute(world.db, world.project.id, "E1", year=2025)


@pytest.mark.parametrize("value", [None, "", "  ", "非金额", True, False, "NaN", "Infinity", "-Infinity"])
async def test_formula_integrity_wp_invalid_amount_is_not_zero(integrity_world, value):
    world = integrity_world
    await add_wp(world, "E1", {"audited_amount": value})
    with pytest.raises(FormulaEvalError):
        await WPExecutor.execute(world.db, world.project.id, "E1", year=2025)


@pytest.mark.parametrize("value", [0, "0", "-0.00", "23.50"])
async def test_formula_integrity_wp_valid_zero_and_amount_are_preserved(integrity_world, value):
    world = integrity_world
    await add_wp(world, "E1", {"audited_amount": value})
    await add_wp(world, "E1", {"audited_amount": "999"}, project=world.other)
    actual = await WPExecutor.execute(world.db, world.project.id, "E1", year=2025)
    assert actual == Decimal(str(value))


@pytest.mark.parametrize("parsed", [None, {}, [], "不合法解析数据"])
async def test_formula_integrity_wp_missing_parsed_data_fails(integrity_world, parsed):
    world = integrity_world
    await add_wp(world, "E1", parsed)
    with pytest.raises(FormulaEvalError):
        await WPExecutor.execute(world.db, world.project.id, "E1", year=2025)


@pytest.mark.parametrize("kind", ["index_deleted", "paper_deleted", "index_other_project", "paper_other_project"])
async def test_formula_integrity_wp_requires_both_sides_active_and_in_project(integrity_world, kind):
    world = integrity_world
    await add_wp(world, "E1", {"audited_amount": "23.50"},
                 project=world.other if kind == "paper_other_project" else world.project,
                 index_project=world.other if kind == "index_other_project" else world.project,
                 index_deleted=kind == "index_deleted", paper_deleted=kind == "paper_deleted")
    with pytest.raises(FormulaEvalError, match="不存在或未找到"):
        await WPExecutor.execute(world.db, world.project.id, "E1", year=2025)


async def empty_catalog(monkeypatch):
    from app.services.acnr import wp_cell_target
    from app.services.acnr.catalog import CatalogIndex

    async def load_catalog(db, project_id):
        return CatalogIndex({"sheets": [], "cells": []})

    monkeypatch.setattr(wp_cell_target, "effective_catalog", load_catalog)


@pytest.mark.parametrize("three_args", [False, True])
@pytest.mark.parametrize("value", ["23.50", "0", None, " ", "金额", "NaN", "Infinity", True])
async def test_formula_integrity_a1_reads_real_cell_or_fails(integrity_world, monkeypatch, three_args, value):
    world = integrity_world
    await empty_catalog(monkeypatch)
    await add_wp(world, "E1", {"html_data": {"明细": {"cells": {"D6": value}}}})
    if value in ("23.50", "0"):
        actual = await WPExecutor.execute(world.db, world.project.id, "E1",
                                          "明细" if three_args else "d6",
                                          field="d6" if three_args else None, year=2025)
        assert actual == Decimal(value)
    else:
        with pytest.raises(FormulaEvalError):
            await WPExecutor.execute(world.db, world.project.id, "E1",
                                     "明细" if three_args else "D6",
                                     field="D6" if three_args else None, year=2025)


async def test_formula_integrity_three_arg_a1_rejects_deleted_index(integrity_world, monkeypatch):
    world = integrity_world
    await empty_catalog(monkeypatch)
    await add_wp(world, "E1", {"html_data": {"明细": {"cells": {"D6": "23.50"}}}},
                 index_deleted=True)
    with pytest.raises(FormulaEvalError, match="不存在或未找到"):
        await WPExecutor.execute(world.db, world.project.id, "E1", "明细", field="D6", year=2025)


async def test_formula_integrity_two_arg_a1_does_not_choose_first_sheet(integrity_world):
    world = integrity_world
    await add_wp(world, "E1", {"html_data": {
        "明细甲": {"cells": {"D6": "23"}}, "明细乙": {"cells": {"D6": "91"}},
    }})
    with pytest.raises(FormulaEvalError, match="歧义|多个"):
        await WPExecutor.execute(world.db, world.project.id, "E1", "D6", year=2025)


@pytest.mark.parametrize("parent_present", [False, True])
@pytest.mark.parametrize("requested_code", ["E1", "E1-2"])
async def test_formula_integrity_acnr_reads_bound_child_not_parent(
    integrity_world, monkeypatch, parent_present, requested_code,
):
    from app.services.acnr import wp_cell_target
    from app.services.acnr.catalog import CatalogIndex

    world = integrity_world
    catalog = CatalogIndex({"sheets": [{
        "addr_id": "E1/E1-2", "parent_wp_code": "E1", "sheet_code": "E1-2",
        "sheet_name": "明细",
    }], "cells": []})

    async def load_catalog(db, project_id):
        assert db is world.db and project_id == world.project.id
        return catalog

    monkeypatch.setattr(wp_cell_target, "effective_catalog", load_catalog)
    if parent_present:
        await add_wp(world, "E1", {"html_data": {"明细": {"cells": {"D6": "999"}}}})
    await add_wp(world, "E1-2", {"html_data": {"明细": {"cells": {"D6": "23.50"}}}})
    actual = await WPExecutor.execute(world.db, world.project.id, requested_code,
                                      "明细", field="D6", year=2025)
    assert actual == Decimal("23.50")


@pytest.mark.parametrize("paper_deleted", [False, True])
async def test_formula_integrity_acnr_bound_child_missing_does_not_fall_back(
    integrity_world, monkeypatch, paper_deleted,
):
    from app.services.acnr import wp_cell_target
    from app.services.acnr.catalog import CatalogIndex

    world = integrity_world
    catalog = CatalogIndex({"sheets": [{
        "addr_id": "E1/E1-2", "parent_wp_code": "E1", "sheet_code": "E1-2",
        "sheet_name": "明细",
    }], "cells": []})

    async def load_catalog(db, project_id):
        return catalog

    monkeypatch.setattr(wp_cell_target, "effective_catalog", load_catalog)
    await add_wp(world, "E1", {"html_data": {"明细": {"cells": {"D6": "999"}}}})
    await add_wp(world, "E1-2", {"html_data": {"明细": {"cells": {"D6": None}}}},
                 paper_deleted=paper_deleted)
    with pytest.raises(FormulaEvalError):
        await WPExecutor.execute(world.db, world.project.id, "E1", "明细", field="D6", year=2025)
