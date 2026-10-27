"""``read_acnr_target_values``：acnr_results 块的逐项取值（acnr-foundation-defect-closure T14，design §2.2）。

真实目录 + 真实解析（``resolve_acnr_targets``）+ SQLite 真 ORM（项目年度查询在下一层 ``wp_cell_reader`` 换成 2025，
SQLite 上原生 SQL 按 ``str(uuid)`` 绑定匹配不到）：两张 sheet 同一 A1 各取各值；文本格 ``text``；单元格为空
``missing`` 不给 0；未生成底稿 ``wp_missing``；有 sheet 级底稿读它、没有读父底稿且 ``jump_route`` 非空并带 ``sheet=``；
顺序与重复项逐项对应。端点与鉴权在 T15 的 ``test_acnr_targets_query_e2e.py``。
"""
from __future__ import annotations

import uuid

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
from app.services.acnr.wp_cell_target import sheet_key_for  # noqa: E402
from app.services.custom_query.acnr_target_values import read_acnr_target_values, resolve_acnr_targets  # noqa: E402

_TABLES = [User.__table__, Project.__table__, WpIndex.__table__, WorkingPaper.__table__]
_E1_15 = get_catalog().sheets_by_addr_id["E1/E1-15"]["sheet_name"]
_D2_2 = get_catalog().sheets_by_addr_id["D2/D2-2"]["sheet_name"]
_PAPERS = {
    "E1": {"html_data": {
        "货币资金分析表E1-14": {"cells": {"C10": "0.125", "B30": "结论文本"}},
        _E1_15: {"cells": {"C8": "222", "C10": "999"}},
    }},
    "D2": {"html_data": {_D2_2: {"cells": {"E100": "1"}}}},
    "D2-2": {"html_data": {_D2_2: {"cells": {"E100": "2"}}}},
}


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
        db.add(Project(id=pid, name="【测试】acnr_targets 取值", client_name="【测试】acnr_targets 取值",
                       status=ProjectStatus.execution, template_type="listed", report_scope="standalone",
                       audit_year=2025, scenario="normal"))
        await db.flush()
        ids = {}
        for code, parsed in _PAPERS.items():
            idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=code, wp_name=f"【测试】{code}")
            db.add(idx)
            await db.flush()
            wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path=f"{code}.xlsx",
                              source_type=WpSourceType.template, parsed_data=parsed)
            db.add(wp)
            ids[code] = wp.id
        await db.commit()
        yield db, pid, ids
    await engine.dispose()


async def _run(db, pid, raws, year=2025):
    resolved = await resolve_acnr_targets(raws, project_id=str(pid), db=db)
    return await read_acnr_target_values(resolved, project_id=str(pid), year=year, db=db)


async def test_two_sheets_same_a1_each_read_their_own(world):
    db, pid, ids = world
    got = await _run(db, pid, ["E1/E1-14/C10", "E1/E1-15/C8"])
    assert got["registry_version"] == get_catalog().registry_version and got["year"] == 2025
    a, b = got["items"]
    assert (a["state"], a["value"], a["text"]) == ("ok", "0.125", "0.125")
    assert (b["state"], b["value"]) == ("ok", "222")
    assert a["source"]["sheet_key"] == "货币资金分析表E1-14" and b["source"]["sheet_key"] == _E1_15
    assert a["source"]["wp_id"] == str(ids["E1"]) and a["formula_ref"] == "WP('E1','货币资金分析表E1-14','C10')"
    assert set(a) == {"input", "addr_id", "display_label", "formula_ref", "state", "value", "text",
                      "reason_code", "reason", "source"}
    assert set(a["source"]) == {"wp_code", "sheet_code", "sheet_key", "cell", "wp_id", "jump_route"}


async def test_text_cell_and_empty_cell(world):
    db, pid, _ = world
    text_item, empty = (await _run(db, pid, ["E1/E1-14/B30", "E1/E1-15/B25"]))["items"]
    assert (text_item["state"], text_item["value"], text_item["text"], text_item["reason_code"]) == (
        "text", None, "结论文本", "non_numeric")
    assert (empty["state"], empty["value"], empty["reason_code"]) == ("missing", None, "cell_empty")
    assert empty["reason"]


async def test_missing_paper_is_wp_missing_not_zero(world):
    """项目里没有 D2-5 的 sheet 级底稿 ⇒ 回落父底稿 D2；D2 存在但没有这张表 ⇒ sheet_missing；夹具之外的底稿（父级与 sheet 级都没生成）⇒ wp_missing。"""
    db, pid, _ = world
    (item,) = (await _run(db, pid, ["D2/D2-5/C15"]))["items"]
    assert (item["state"], item["value"], item["reason_code"]) == ("missing", None, "sheet_missing")
    cat = get_catalog()
    other = sorted(a for a, c in cat.cells_by_addr_id.items()
                   if not c.get("deprecated") and not {a.split("/")[0], a.split("/")[1]} & set(_PAPERS)
                   and sheet_key_for(cat.sheets_by_addr_id[c["parent_addr_id"]], index=cat).key)[0]
    (item,) = (await _run(db, pid, [other]))["items"]
    assert (item["state"], item["value"], item["reason_code"]) == ("missing", None, "wp_missing")
    assert item["source"]["wp_id"] is None and item["source"]["jump_route"] is None


async def test_sheet_level_paper_preferred_and_parent_route_has_sheet(world):
    db, pid, ids = world
    (sheet_level,) = (await _run(db, pid, ["D2/D2-2/E100"]))["items"]
    assert (sheet_level["source"]["wp_code"], sheet_level["value"]) == ("D2-2", "2")
    assert sheet_level["source"]["wp_id"] == str(ids["D2-2"])
    (parent,) = (await _run(db, pid, ["E1/E1-15/C8"]))["items"]
    route = parent["source"]["jump_route"]
    assert parent["source"]["wp_code"] == "E1" and route and str(ids["E1"]) in route and "sheet=E1-15" in route


async def test_order_and_duplicates_one_item_each(world):
    db, pid, _ = world
    raws = ["E1/E1-15/C8", "WP('E1','货币资金分析表E1-14','C10')", "E1/E1-15/C8"]
    items = (await _run(db, pid, raws))["items"]
    assert [i["input"] for i in items] == raws
    assert [i["addr_id"] for i in items] == ["E1/E1-15/C8", "E1/E1-14/C10", "E1/E1-15/C8"]
    assert [i["value"] for i in items] == ["222", "0.125", "222"]


async def test_year_mismatch_is_missing(world):
    db, pid, _ = world
    (item,) = (await _run(db, pid, ["E1/E1-14/C10"], year=2024))["items"]
    assert (item["state"], item["value"], item["reason_code"]) == ("missing", None, "year_mismatch")


async def test_no_targets_no_block(world):
    db, pid, _ = world
    assert await read_acnr_target_values([], project_id=str(pid), year=2025, db=db) is None
