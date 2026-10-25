"""多表附注按表 binding、完整刷新与旧值保护回归。"""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.report_models import ContentType, DisclosureNote, SourceTemplate
from app.services import note_template_bindings_loader as loader
from app.services.disclosure_engine import DisclosureEngine

PROJECT = uuid4()
SECTION = "五、测试多表"
YEAR = 2025


def _engine() -> DisclosureEngine:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return DisclosureEngine(db)


def _template() -> dict:
    return {
        "note_section": SECTION,
        "content_type": "table",
        "tables": [
            {"name": "首表", "headers": ["项目", "期末"],
             "rows": [{"label": "相同行", "account_codes": ["1001"]}]},
            {"name": "次表", "headers": ["项目", "期末"],
             "rows": [{"label": "相同行", "account_codes": ["1122"]}]},
        ],
    }


def _binding(code: str) -> dict:
    return {
        "header_normalize": [{"semantic": "row_label"}, {"semantic": "closing_balance"}],
        "rows": {"相同行": {"binding": {"closing_balance": {
            "mode": "auto", "source": "trial_balance", "account_codes": [code],
            "field": "audited_amount", "agg": "sum",
        }}}},
    }


def _bindings(monkeypatch, *, second=True) -> None:
    bindings = [_binding("1001")]
    if second:
        bindings.append(_binding("1122"))
    monkeypatch.setattr(loader, "get_binding_for_section", lambda section: {
        "tables": bindings,
    } if section == SECTION else None)


def _cache(eng: DisclosureEngine) -> None:
    eng._tb_cache = {
        "1001": {"audited": 10, "opening": 1},
        "1122": {"audited": 20, "opening": 2},
    }


def _note(td: dict | None) -> DisclosureNote:
    return DisclosureNote(
        project_id=PROJECT, year=YEAR, note_section=SECTION,
        section_title="多表", content_type=ContentType.table,
        source_template=SourceTemplate.listed, table_data=td,
    )


def _one_result(note: DisclosureNote):
    result = MagicMock()
    result.scalar_one_or_none.return_value = note
    return result

@pytest.mark.asyncio
async def test_distinct_bindings_for_same_label_and_mirror(monkeypatch):
    eng = _engine()
    _cache(eng)
    _bindings(monkeypatch)
    td = await eng._build_section_table_data(PROJECT, YEAR, _template())
    assert td is not None
    assert [t["rows"][0]["values"][0] for t in td["_tables"]] == [10, 20]
    assert [t["name"] for t in td["_tables"]] == ["首表", "次表"]
    assert td["rows"] == td["_tables"][0]["rows"]
    assert td["name"] == "首表"
    assert td["_tables"][1]["rows"][0]["_cell_meta"]["0"]["binding_id"] == (
        f"{SECTION}.相同行.closing_balance"
    )


@pytest.mark.asyncio
async def test_missing_second_binding_never_borrows_first(monkeypatch):
    eng = _engine()
    _cache(eng)
    _bindings(monkeypatch, second=False)
    td = await eng._build_section_table_data(PROJECT, YEAR, _template())
    assert td is not None
    assert td["_tables"][0]["rows"][0]["values"] == [10]
    # 越界走 legacy，用本表 account_codes 取 1122，而不是借用首表 binding 的 1001。
    assert td["_tables"][1]["rows"][0]["values"] == [20]
    assert "_cell_modes" not in td["_tables"][1]["rows"][0]


@pytest.mark.asyncio
async def test_legacy_detail_metadata_survives_section_build(monkeypatch):
    eng = _engine()
    eng._wp_fine_cache = {"DETAIL": {"rows": {
        "one": {"is_detail": True, "label": "明细行", "closing_audited": 31},
    }}}
    monkeypatch.setattr(loader, "get_binding_for_section", lambda section: None)
    tmpl = {"note_section": SECTION, "tables": [{
        "name": "动态明细", "wp_code": "DETAIL", "headers": ["项目", "期末"],
        "rows": [{"label": "模板占位", "is_dynamic_detail": True}],
    }]}
    td = await eng._build_section_table_data(PROJECT, YEAR, tmpl)
    assert td is not None
    assert td["_tables"][0]["rows"] == [{
        "label": "明细行", "values": [31], "is_detail": True,
    }]


@pytest.mark.asyncio
async def test_incremental_refresh_keeps_both_tables_and_cell_modes(monkeypatch):
    eng = _engine()
    _cache(eng)
    _bindings(monkeypatch)
    old = await eng._build_section_table_data(PROJECT, YEAR, _template())
    assert old is not None
    old["_tables"][0]["rows"][0]["values"] = [1]
    old["_tables"][1]["rows"][0]["values"] = [999]
    old["_tables"][1]["rows"][0]["_cell_modes"]["0"] = "manual"
    old["_tables"][1]["rows"][0]["_cell_meta"]["0"]["manual_value"] = 999
    old["rows"] = deepcopy(old["_tables"][0]["rows"])
    note = _note(old)
    eng.db.execute.return_value = _one_result(note)
    eng._get_active_template_type = AsyncMock(return_value="listed")
    eng._load_templates = AsyncMock(return_value=[_template()])
    with patch("sqlalchemy.orm.attributes.flag_modified") as flag:
        assert await eng.update_note_values(PROJECT, YEAR, ["1122"]) == 1
    assert len(note.table_data["_tables"]) == 2
    assert note.table_data["_tables"][0]["rows"][0]["values"] == [10]
    assert note.table_data["_tables"][1]["rows"][0]["values"] == [999]
    assert note.table_data["_tables"][1]["rows"][0]["_cell_modes"]["0"] == "manual"
    assert note.table_data["rows"] == note.table_data["_tables"][0]["rows"]
    flag.assert_called_once_with(note, "table_data")
    eng.db.flush.assert_awaited_once()
    eng.db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_incremental_refresh_locked_and_workpaper_source(monkeypatch):
    eng = _engine()
    _cache(eng)
    _bindings(monkeypatch)
    td = await eng._build_section_table_data(PROJECT, YEAR, _template())
    assert td is not None
    td["_tables"][1]["rows"][0]["_cell_modes"]["0"] = "locked"
    td["_tables"][1]["rows"][0]["values"] = [777]
    note = _note(td)
    eng.db.execute.return_value = _one_result(note)
    eng._get_active_template_type = AsyncMock(return_value="listed")
    eng._load_templates = AsyncMock(return_value=[_template()])
    with patch("sqlalchemy.orm.attributes.flag_modified"):
        await eng.update_note_values(PROJECT, YEAR)
    assert note.table_data["_tables"][1]["rows"][0]["values"] == [777]
    note.table_data["_source"] = "workpaper_html"
    before = deepcopy(note.table_data)
    with patch("sqlalchemy.orm.attributes.flag_modified"):
        await eng.update_note_values(PROJECT, YEAR)
    assert note.table_data == before

@pytest.mark.asyncio
async def test_empty_detail_rebuilds_both_tables(monkeypatch):
    eng = _engine()
    _cache(eng)
    _bindings(monkeypatch)
    note = _note(None)
    eng.db.execute.return_value = _one_result(note)
    eng._load_templates = AsyncMock(return_value=[_template()])
    with patch("sqlalchemy.orm.attributes.flag_modified") as flag:
        result = await eng.get_note_detail(PROJECT, YEAR, SECTION)
    assert result is note
    assert [t["rows"][0]["values"][0] for t in note.table_data["_tables"]] == [10, 20]
    assert note.table_data["rows"] == note.table_data["_tables"][0]["rows"]
    flag.assert_called_once_with(note, "table_data")
    eng.db.flush.assert_awaited_once()
    eng.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_incremental_refresh_skips_unrelated_accounts(monkeypatch):
    eng = _engine()
    _cache(eng)
    _bindings(monkeypatch)
    note = _note({"_tables": []})
    eng.db.execute.return_value = _one_result(note)
    eng._get_active_template_type = AsyncMock(return_value="listed")
    eng._load_templates = AsyncMock(return_value=[_template()])
    assert await eng.update_note_values(PROJECT, YEAR, ["9999"]) == 0
    eng.db.execute.assert_not_awaited()
    eng.db.flush.assert_awaited_once()
