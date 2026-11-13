"""S2 Task 2 (ADR-CCN-02)：附注执行器按类别分流单测。

命名按任务规格：
- test_auto_calc_writes_back
- test_logic_check_no_writeback
- test_reasonability_no_writeback
- test_manual_cell_not_overwritten
- test_prev_written_cell_overwritten
- test_mode_manual_not_overwritten

不依赖真实数据库，全部 mock。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

_PROJECT = UUID("00000000-0000-0000-0000-000000000002")
_YEAR = 2025
_SECTION = "五、99"


def _fake_note(rows, formulas, cell_modes=None, user_formulas=None):
    """构造 DisclosureNote mock，供 db.execute 返回。"""
    td: dict = {"rows": rows, "_formulas": formulas, "headers": ["label", "金额"]}
    if cell_modes:
        td["_cell_modes"] = cell_modes
    if user_formulas:
        td["_user_formulas"] = user_formulas
    note = MagicMock()
    note.table_data = td
    note.project_id = _PROJECT
    note.year = _YEAR
    note.note_section = _SECTION
    return note


async def _run(note):
    """调用 execute_note_formulas，mock 掉 DB 副作用。"""
    mock_db = AsyncMock()
    proxy = MagicMock()
    proxy.scalar_one_or_none.return_value = note
    mock_db.execute = AsyncMock(return_value=proxy)
    mock_db.flush = AsyncMock()
    with (
        patch(
            "app.services.note_formula_generator._load_cross_table_data",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "app.services.note_formula_generator._resolve_cross_refs_via_acnr",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        from app.services.note_formula_generator import execute_note_formulas

        return await execute_note_formulas(mock_db, _PROJECT, _YEAR, _SECTION)


# ── auto_calc ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_calc_writes_back():
    """auto_calc 公式的结果写回单元格，updated 增加。"""
    rows = [
        {"values": [50.0], "label": "子项1"},
        {"values": [30.0], "label": "子项2"},
        {"values": [None], "label": "合计"},
    ]
    formulas = {
        "2:0": {
            "type": "vertical_sum",
            "expression": "SUM(0:1, 0)",
            "category": "auto_calc",
        }
    }
    note = _fake_note(rows, formulas)
    result = await _run(note)

    assert note.table_data["rows"][2]["values"][0] == 80.0
    assert result["updated"] == 1
    assert result["executed"] >= 1
    assert "checks" in result


# ── logic_check ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_logic_check_no_writeback():
    """logic_check 公式不改写单元格，但在 checks 列表中有结果。"""
    rows = [
        {"values": [40.0], "label": "子项1"},
        {"values": [60.0], "label": "子项2"},
        {"values": [999.0], "label": "合计（手工）"},  # 期望 100，实际 999
    ]
    formulas = {
        "2:0": {
            "type": "vertical_sum",
            "expression": "SUM(0:1, 0)",
            "category": "logic_check",
            "description": "勾稽检验",
        }
    }
    note = _fake_note(rows, formulas)
    result = await _run(note)

    # 值不变
    assert note.table_data["rows"][2]["values"][0] == 999.0
    assert result["updated"] == 0
    # checks 有条目
    assert len(result.get("checks", [])) >= 1
    chk = result["checks"][0]
    assert chk["status"] == "failed"  # diff=899 >> 0.005


# ── reasonability ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reasonability_no_writeback():
    """reasonability 公式不改写单元格，checks 有合理性检验结果。"""
    rows = [
        {"values": [50.0], "label": "子项1"},
        {"values": [50.0], "label": "子项2"},
        {"values": [50.0], "label": "合计"},  # 期望 100，实际 50
    ]
    formulas = {
        "2:0": {
            "type": "vertical_sum",
            "expression": "SUM(0:1, 0)",
            "category": "reasonability",
            "description": "合理性校验",
        }
    }
    note = _fake_note(rows, formulas)
    result = await _run(note)

    assert note.table_data["rows"][2]["values"][0] == 50.0
    assert result["updated"] == 0
    assert len(result.get("checks", [])) >= 1
    chk = result["checks"][0]
    assert chk["status"] == "failed"  # diff=50 >> 0.005


# ── manual cell not overwritten ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_cell_not_overwritten():
    """没有模式、有值、非本执行器上次写入 → auto_calc 不覆盖。"""
    rows = [
        {"values": [100.0], "label": "子项1"},
        {"values": [777.0], "label": "合计"},  # 有值，no mode，no last_value
    ]
    formulas = {
        "1:0": {
            "type": "vertical_sum",
            "expression": "SUM(0:0, 0)",
            "category": "auto_calc",
        }
    }
    note = _fake_note(rows, formulas)
    result = await _run(note)

    assert note.table_data["rows"][1]["values"][0] == 777.0
    assert result["updated"] == 0
    statuses = [r.get("status") for r in result.get("results", [])]
    assert "skipped_manual" in statuses


# ── prev written cell overwritten ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_prev_written_cell_overwritten():
    """当前值 == last_value → 本执行器上次写入，允许覆盖新计算结果。"""
    rows = [
        {"values": [200.0], "label": "子项1"},
        {"values": [100.0], "label": "合计"},  # 上次执行器写入 100.0
    ]
    formulas = {
        "1:0": {
            "type": "vertical_sum",
            "expression": "SUM(0:0, 0)",
            "category": "auto_calc",
            "last_value": 100.0,  # 上次写入值 == 当前值 → 可覆盖
        }
    }
    note = _fake_note(rows, formulas)
    result = await _run(note)

    assert note.table_data["rows"][1]["values"][0] == 200.0
    assert result["updated"] == 1


# ── mode manual not overwritten ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_mode_manual_not_overwritten():
    """_cell_modes 明确标记 manual → 即使有新计算结果也不覆盖。"""
    rows = [
        {"values": [100.0], "label": "子项1"},
        {"values": [555.0], "label": "合计", "_cell_modes": {"0": "manual"}},
    ]
    formulas = {
        "1:0": {
            "type": "vertical_sum",
            "expression": "SUM(0:0, 0)",
            "category": "auto_calc",
        }
    }
    note = _fake_note(rows, formulas)
    result = await _run(note)

    assert note.table_data["rows"][1]["values"][0] == 555.0
    assert result["updated"] == 0
    statuses = [r.get("status") for r in result.get("results", [])]
    assert "skipped_manual" in statuses
