"""合并附注人工保护元数据与自动写入回归。

spec: consol-note-save-integrity-closure R3.1 / R3.4 / R3.5，design §4 / §7。

保护元数据测试只调用生产解析器；公式写入测试走真实 ``fill_by_formula`` 链路。
明细映射、子树汇总、前 N 名的生产路径坏元数据回归分别保留在各自 service
测试中，避免复制它们的完整企业树 / 模板夹具。
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

import tests.conftest  # noqa: F401  注册全部模型与 SQLite 方言补丁
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_push_models import ConsolNoteFormula
from app.services.consol_note_formula_service import (
    NoteFormulaError,
    consol_note_tables,
    ensure_seeded,
    fill_by_formula,
)
from app.services.consol_note_protection import (
    ProtectionMetadataError,
    parse_locked_cells,
    parse_manual_cells,
    protected_cells,
    section_locked,
)
from tests.test_consol_push import Y, db, factory, group  # noqa: F401  复用真实 SQLite 集团夹具


# ─────────────────────────────── 解析器 ───────────────────────────────


def test_manual_cells_accepts_all_supported_wire_shapes() -> None:
    data = {
        "manual_cells": [
            {"row": 0, "col": 1},
            [2, 3],
            "4:5",
        ]
    }
    assert parse_manual_cells(data) == {(0, 1), (2, 3), (4, 5)}


def test_locked_cells_are_parsed_and_protection_is_the_coordinate_union() -> None:
    record = SimpleNamespace(
        cell_state="auto",
        locked_cells=[{"row_index": 6, "col_index": 7}, {"row_index": 6, "col_index": 7}],
    )
    data = {"manual_cells": [{"row": 1, "col": 2}, "3:4"]}

    assert parse_locked_cells(record) == {(6, 7)}
    assert not section_locked(record)
    assert protected_cells(record, data) == {(1, 2), (3, 4), (6, 7)}


def test_section_locked_uses_the_persisted_cell_state() -> None:
    assert section_locked(SimpleNamespace(cell_state="locked")) is True
    assert section_locked(SimpleNamespace(cell_state="manual")) is False
    assert section_locked(SimpleNamespace(cell_state=None)) is False


@pytest.mark.parametrize("data", [{}, {"manual_cells": None}])
def test_missing_or_null_manual_cells_means_empty(data) -> None:
    assert parse_manual_cells(data) == set()


@pytest.mark.parametrize("record", [SimpleNamespace(), SimpleNamespace(locked_cells=None)])
def test_missing_or_null_locked_cells_means_empty(record) -> None:
    assert parse_locked_cells(record) == set()


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not-an-array", "manual_cells 必须是数组"),
        ([{"row": 0}], "第 1 项"),
        ([[0, 1, 2]], "第 1 项"),
        (["0"], "第 1 项"),
        (["0:1:2"], "第 1 项"),
        ([[True, 1]], "布尔"),
        ([[1, -1]], "负数"),
        ([[1.5, 1]], "整数"),
        ([["1", 1]], "整数"),
    ],
)
def test_manual_cells_rejects_each_invalid_shape(raw, message) -> None:
    with pytest.raises(ProtectionMetadataError) as exc:
        parse_manual_cells({"manual_cells": raw})
    assert message in str(exc.value)
    if isinstance(raw, list):
        assert "第 1 项" in str(exc.value)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not-an-array", "locked_cells 必须是数组"),
        ([{}], "第 1 项"),
        ([[0, 1]], "第 1 项"),
        (["0:1"], "第 1 项"),
        ([{"row_index": True, "col_index": 1}], "布尔"),
        ([{"row_index": 1, "col_index": -1}], "负数"),
        ([{"row_index": 1.5, "col_index": 1}], "整数"),
        ([{"row_index": "1", "col_index": 1}], "整数"),
    ],
)
def test_locked_cells_rejects_each_invalid_shape(raw, message) -> None:
    with pytest.raises(ProtectionMetadataError) as exc:
        parse_locked_cells(SimpleNamespace(locked_cells=raw))
    assert message in str(exc.value)
    if isinstance(raw, list):
        assert "第 1 项" in str(exc.value)


# ─────────────────────────────── 公式生产路径 ───────────────────────────────


def _cell_value(row, col: int):
    if isinstance(row, (list, tuple)):
        return row[col]
    if isinstance(row, dict):
        values = row.get("values") or row.get("cells") or {}
        if isinstance(values, dict):
            return values.get(str(col), values.get(col))
        return values[col]
    raise AssertionError(f"测试夹具出现未知行形态：{type(row)!r}")


def _set_cell(row, col: int, value: str) -> None:
    if isinstance(row, list):
        row[col] = value
        return
    if isinstance(row, dict):
        values = row.setdefault("values", {})
        if isinstance(values, dict):
            values[str(col)] = value
            return
    raise AssertionError(f"测试夹具出现不可写行形态：{type(row)!r}")


async def _seed_formula_note(db, group, *, manual_cells=None, locked_cells=None):
    """准备一条真实公式和附注行，不替换 ``fill_by_formula`` 的任何生产步骤。"""
    await ensure_seeded(db, "soe")
    formulas = (await db.execute(
        sa.select(ConsolNoteFormula).where(
            ConsolNoteFormula.template_type == "soe",
            ConsolNoteFormula.is_deleted == sa.false(),
            ConsolNoteFormula.formula.like("TB(%"),
        ).order_by(ConsolNoteFormula.section_id, ConsolNoteFormula.row_index),
    )).scalars().all()
    formula = None
    table = None
    for candidate in formulas:
        candidate_table = next(
            (item for item in consol_note_tables("soe") if item.get("section_id") == candidate.section_id),
            None,
        )
        if candidate_table is None:
            continue
        rows = candidate_table.get("rows") or []
        headers = candidate_table.get("headers") or []
        if candidate.row_index < len(rows) and candidate.col_index < len(headers):
            formula, table = candidate, candidate_table
            break
    assert formula is not None and table is not None, "测试夹具未找到可执行的 TB 附注公式"

    rows = deepcopy(table["rows"])
    _set_cell(rows[formula.row_index], formula.col_index, "999.00")
    data = {
        "headers": deepcopy(table["headers"]),
        "rows": rows,
        "manual_cells": deepcopy(manual_cells),
    }
    record = ConsolNoteData(
        project_id=group["G"].id,
        year=Y,
        section_id=formula.section_id,
        data=data,
        locked_cells=deepcopy(locked_cells) if locked_cells is not None else [],
    )
    db.add(record)
    await db.flush()
    return record, formula


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("manual_cells", "locked_cells", "reason"),
    [
        ("坏的 manual_cells", [], "manual_cells"),
        (None, "坏的 locked_cells", "locked_cells"),
    ],
)
async def test_fill_by_formula_rejects_bad_protection_without_any_write(
    db, group, manual_cells, locked_cells, reason,
) -> None:
    record, _formula = await _seed_formula_note(
        db, group, manual_cells=manual_cells, locked_cells=locked_cells,
    )
    before_data = deepcopy(record.data)
    before_updated_at = record.updated_at
    before_source_mode = record.source_mode

    with pytest.raises(NoteFormulaError) as exc:
        await fill_by_formula(
            db,
            group["G"].id,
            Y,
            record.section_id,
            template_type="soe",
        )

    assert exc.value.status == 422
    assert reason in str(exc.value)
    await db.refresh(record)
    assert record.data == before_data
    assert record.updated_at == before_updated_at
    assert record.source_mode == before_source_mode


@pytest.mark.asyncio
async def test_fill_by_formula_preserves_manual_value_and_reports_exact_count(db, group) -> None:
    record, formula = await _seed_formula_note(
        db, group, manual_cells=[{"row": 0, "col": 1}], locked_cells=[],
    )
    expected = _cell_value(record.data["rows"][formula.row_index], formula.col_index)

    result = await fill_by_formula(
        db,
        group["G"].id,
        Y,
        record.section_id,
        template_type="soe",
    )

    assert result["status"] == "persisted"
    assert result["kept_manual_count"] == 1
    assert len(result["kept_manual"]) == 1
    assert result["kept_manual"][0]["current"] == expected
    assert _cell_value(result["data"]["rows"][formula.row_index], formula.col_index) == expected
