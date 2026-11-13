"""合并附注自定义查询单格回写的人工保护标记（R3.6）。"""
from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.sql.elements import TextClause

from app.routers.custom_query_writeback import _writer_http_error
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_push_models import ConsolNoteFormula
from app.services.consol_note_formula_service import consol_note_tables, ensure_seeded, fill_by_formula
from app.services.consol_note_protection import ProtectionMetadataError
from app.services.custom_query.snapshot_writer_modules import write_note_cell
from tests.test_consol_push import Y, db, factory, group  # noqa: F401  复用真实 SQLite 集团夹具


class _FakeDb:
    """只模拟真实 writer 使用的 ORM SELECT 与原生 UPDATE。"""

    def __init__(self, record):
        self.record = record
        self.updates: list[dict] = []

    async def execute(self, statement, params=None):
        if isinstance(statement, TextClause):
            self.updates.append(dict(params or {}))
            return SimpleNamespace()
        return SimpleNamespace(scalar_one_or_none=lambda: self.record)


def _record(data):
    return SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        year=2025,
        section_id="五-1-1",
        node_key=None,
        data=data,
        updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        cell_state="auto",
        locked_cells=[],
    )


async def _write(record, cell_ref="C2", new_value=300):
    db = _FakeDb(record)
    result = await write_note_cell(
        db,
        MagicMock(),
        str(record.id),
        "附注",
        cell_ref,
        new_value,
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        check_lock=lambda opened_at, updated_at, user: None,
        note_record_id=str(record.id),
        note_project_id=str(record.project_id),
        note_section_id=record.section_id,
        note_year=record.year,
        note_node_key=record.node_key,
    )
    return result, db


async def _seed_real_formula_note_for_writeback(db, group):
    """用真实公式种子准备可由 ``write_note_cell`` 定位的数组行。"""
    await ensure_seeded(db, "soe")
    formulas = (await db.execute(
        sa.select(ConsolNoteFormula).where(
            ConsolNoteFormula.template_type == "soe",
            ConsolNoteFormula.is_deleted == sa.false(),
            ConsolNoteFormula.formula.like("TB(%"),
        ).order_by(ConsolNoteFormula.section_id, ConsolNoteFormula.row_index),
    )).scalars().all()
    for formula in formulas:
        if not isinstance(formula.row_index, int) or not 1 <= formula.col_index <= 4:
            continue
        table = next(
            (item for item in consol_note_tables("soe")
             if item.get("section_id") == formula.section_id),
            None,
        )
        if table is None:
            continue
        rows = deepcopy(table.get("rows") or [])
        headers = deepcopy(table.get("headers") or [])
        if formula.row_index >= len(rows) or formula.col_index >= len(headers):
            continue
        if not isinstance(rows[formula.row_index], list):
            continue
        rows[formula.row_index][formula.col_index] = "999.00"
        record = ConsolNoteData(
            project_id=group["G"].id,
            year=Y,
            section_id=formula.section_id,
            data={"headers": headers, "rows": rows},
        )
        db.add(record)
        await db.flush()
        return record, formula
    raise AssertionError("测试夹具未找到可由自定义查询回写的 TB 附注公式数组行")


def _cell_ref(row_index: int, col_index: int) -> str:
    """按现有 writer 的行号契约把零基坐标转换成 Excel 引用。"""
    return f"{chr(ord('A') + col_index)}{row_index + 2}"


@pytest.mark.asyncio
async def test_array_value_column_adds_manual_cell_and_returns_receipt():
    record = _record({"rows": [["现金", "旧本期", "旧上期"]]})

    result, db = await _write(record)

    assert result["marked_manual"] is True
    assert "manual_skip_reason" not in result
    assert record.data["rows"][0][2] == 300
    assert record.data["manual_cells"] == [{"row": 0, "col": 2}]
    assert json.loads(db.updates[0]["new_data"]) == record.data


@pytest.mark.asyncio
@pytest.mark.parametrize("manual_cells", [None, ["0:2"], [{"row": 0, "col": 2}]])
async def test_existing_manual_cell_is_not_duplicated(manual_cells):
    record = _record({"rows": [["现金", "旧本期", "旧上期"]], "manual_cells": manual_cells})

    result, _db = await _write(record)

    assert result["marked_manual"] is True
    if manual_cells is None:
        assert record.data["manual_cells"] == [{"row": 0, "col": 2}]
    elif manual_cells == ["0:2"] or manual_cells == [{"row": 0, "col": 2}]:
        assert record.data["manual_cells"] == manual_cells
        assert len(record.data["manual_cells"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "cell_ref", "reason"),
    [
        ({"rows": [["现金", "旧本期", "旧上期"]]}, "A2", "项目名列不参与取数"),
        ({"rows": [{"code": "1001", "year_end": 10}]}, "C2", "旧格式字典行没有格坐标"),
    ],
)
async def test_project_name_or_dict_row_is_not_marked(data, cell_ref, reason):
    record = _record(data)

    result, _db = await _write(record, cell_ref=cell_ref, new_value=999)

    assert result["marked_manual"] is False
    assert result["manual_skip_reason"] == reason
    assert "manual_cells" not in record.data


@pytest.mark.asyncio
async def test_invalid_manual_cells_rejects_write_before_update():
    original = {"rows": [["现金", "旧本期", "旧上期"]], "manual_cells": "损坏"}
    record = _record(deepcopy(original))
    db = _FakeDb(record)

    with pytest.raises(ProtectionMetadataError) as exc:
        await write_note_cell(
            db,
            MagicMock(),
            str(record.id),
            "附注",
            "C2",
            300,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            check_lock=lambda opened_at, updated_at, user: None,
            note_record_id=str(record.id),
            note_project_id=str(record.project_id),
            note_section_id=record.section_id,
            note_year=record.year,
            note_node_key=record.node_key,
        )

    assert "manual_cells" in str(exc.value)
    assert db.updates == []
    assert record.data == original


def test_invalid_manual_cells_maps_to_422_protected_cells_error():
    mapped = _writer_http_error(ProtectionMetadataError("manual_cells 必须是数组，本章节未写入"))

    assert mapped is not None
    assert mapped.status_code == 422
    assert mapped.detail == {
        "error_code": "PROTECTED_CELLS_INVALID",
        "message": "manual_cells 必须是数组，本章节未写入",
    }


@pytest.mark.asyncio
async def test_writeback_then_fill_by_formula_preserves_custom_value(db, group):
    """生产回写后走生产公式链，回写格必须继续受 manual_cells 保护。"""
    record, formula = await _seed_real_formula_note_for_writeback(db, group)
    row_index, col_index = formula.row_index, formula.col_index
    cell_ref = _cell_ref(row_index, col_index)
    writeback_value = "custom-query-writeback-value"

    write_result = await write_note_cell(
        db,
        SimpleNamespace(id=uuid.uuid4()),
        str(record.id),
        "附注",
        cell_ref,
        writeback_value,
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        check_lock=lambda opened_at, updated_at, user: None,
        note_record_id=str(record.id),
        note_project_id=str(record.project_id),
        note_section_id=record.section_id,
        note_year=record.year,
        note_node_key=record.node_key,
    )
    await db.refresh(record)

    fill_result = await fill_by_formula(
        db,
        group["G"].id,
        Y,
        record.section_id,
        template_type="soe",
    )
    await db.refresh(record)

    expected_coordinate = {"row": row_index, "col": col_index}
    assert write_result["marked_manual"] is True
    assert fill_result["status"] == "persisted"
    assert fill_result["kept_manual_count"] == 1
    assert expected_coordinate in record.data["manual_cells"]
    assert record.data["rows"][row_index][col_index] == writeback_value
    assert fill_result["data"]["rows"][row_index][col_index] == writeback_value
