"""附注公式模式切换的多表容器遍历回归。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.note_wp_mapping_service import NoteWpMappingService

PROJECT_ID = uuid4()
YEAR = 2025
SECTION = "五、测试多表"


def _service_for_table_data(table_data: dict) -> tuple[NoteWpMappingService, SimpleNamespace]:
    note = SimpleNamespace(
        project_id=PROJECT_ID,
        year=YEAR,
        note_section=SECTION,
        table_data=table_data,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = note
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    return NoteWpMappingService(db), note


@pytest.mark.asyncio
async def test_clear_formulas_visits_nested_tables_once_not_top_level_mirror():
    first = {"label": "首表行", "values": [10], "_cell_modes": {"0": "auto"}}
    second = {"label": "次表行", "values": [20], "_cell_modes": {"0": "auto"}}
    mirror = {"label": "首表行", "values": [999], "_cell_modes": {"0": "auto"}}
    td = {
        "_tables": [
            {"name": "首表", "rows": [first]},
            {"name": "次表", "rows": [second]},
        ],
        # 顶层 rows 是首表兼容镜像，不能再次计数。
        "rows": [mirror],
        "metadata": {"keep": True},
    }
    service, note = _service_for_table_data(td)

    with patch("sqlalchemy.orm.attributes.flag_modified"):
        cleared = await service.clear_formulas(PROJECT_ID, YEAR, SECTION)

    assert cleared == 2
    assert first["_cell_modes"] == {"0": "manual"}
    assert second["_cell_modes"] == {"0": "manual"}
    assert mirror["_cell_modes"] == {"0": "auto"}
    assert note.table_data["metadata"] == {"keep": True}


@pytest.mark.asyncio
async def test_workpaper_clear_writes_raw_business_key_rows_not_projection_sentinel():
    raw_row = {
        "label": "原始行",
        "amount": 11,
        "_cell_modes": {"0": "auto"},
    }
    projected_row = {
        "label": "原始行",
        "values": [999],
        "_cell_modes": {"0": "auto"},
    }
    td = {
        "_source": "workpaper",
        "sub_table_data": {"明细": [raw_row], "_note_texts": [{"text": "保留"}]},
        "_tables": [{"name": "明细", "rows": [projected_row]}],
    }
    service, note = _service_for_table_data(td)

    with patch("sqlalchemy.orm.attributes.flag_modified"):
        cleared = await service.clear_formulas(PROJECT_ID, YEAR, SECTION)

    assert cleared == 1
    assert raw_row["_cell_modes"] == {"0": "manual"}
    assert projected_row["_cell_modes"] == {"0": "auto"}
    assert raw_row["amount"] == 11
    assert note.table_data["sub_table_data"]["_note_texts"] == [{"text": "保留"}]


@pytest.mark.asyncio
async def test_legacy_rows_and_three_modes_are_preserved():
    row = {
        "label": "旧格式",
        "values": [1, 2, 3],
        "_cell_modes": {"0": "auto", "1": "manual", "2": "locked"},
    }
    service, note = _service_for_table_data({"rows": [row]})

    with patch("sqlalchemy.orm.attributes.flag_modified"):
        cleared = await service.clear_formulas(PROJECT_ID, YEAR, SECTION)

    assert cleared == 1
    assert row["values"] == [1, 2, 3]
    assert row["_cell_modes"] == {"0": "manual", "1": "manual", "2": "locked"}

    service.refresh_from_workpapers = AsyncMock()
    with patch("sqlalchemy.orm.attributes.flag_modified"):
        restored = await service.restore_auto_mode(PROJECT_ID, YEAR, SECTION)

    assert restored == 2
    assert row["_cell_modes"] == {"0": "auto", "1": "auto", "2": "locked"}
    service.refresh_from_workpapers.assert_awaited_once_with(PROJECT_ID, YEAR)
    assert note.table_data["rows"][0]["values"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_restore_auto_visits_all_nested_tables_and_ignores_mirror():
    first = {"values": [1], "_cell_modes": {"0": "manual"}}
    second = {"values": [2], "_cell_modes": {"0": "manual", "1": "locked"}}
    mirror = {"values": [100], "_cell_modes": {"0": "manual"}}
    td = {
        "_tables": [{"rows": [first]}, {"rows": [second]}],
        "rows": [mirror],
    }
    service, _note = _service_for_table_data(td)
    service.refresh_from_workpapers = AsyncMock()

    with patch("sqlalchemy.orm.attributes.flag_modified"):
        restored = await service.restore_auto_mode(PROJECT_ID, YEAR, SECTION)

    assert restored == 2
    assert first["_cell_modes"] == {"0": "auto"}
    assert second["_cell_modes"] == {"0": "auto", "1": "locked"}
    assert mirror["_cell_modes"] == {"0": "manual"}
    service.refresh_from_workpapers.assert_awaited_once_with(PROJECT_ID, YEAR)
