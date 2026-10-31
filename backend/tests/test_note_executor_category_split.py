"""S2 Task 2 (ADR-CCN-02)：附注执行器按类别分流测试。

三类别夹具：auto_calc 回写、logic_check 只产出校对结果、手工格不覆盖。
测试直接调用 execute_note_formulas 并观察其行为（非 fixture 自检）。

公式类型使用 vertical_sum（SUM(start:end, col)），这是 _exec_formula_value
唯一不依赖跨表数据（即纯表内引用）的类型，可在不连数据库的条件下求值。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest


_PROJECT = UUID("00000000-0000-0000-0000-000000000001")
_YEAR = 2025
_SECTION = "五、1"


def _fake_note(rows, formulas, user_formulas=None):
    """构造 DisclosureNote mock 对象，供 db.execute 返回。"""
    td = {"rows": rows, "_formulas": formulas, "headers": ["label", "金额"]}
    if user_formulas:
        td["_user_formulas"] = user_formulas
    note = MagicMock()
    note.table_data = td
    note.project_id = _PROJECT
    note.year = _YEAR
    note.note_section = _SECTION
    return note


async def _run_executor(note):
    """包装 execute_note_formulas 调用，mock 掉 DB 与跨表数据加载。"""
    mock_db = AsyncMock()
    result_proxy = MagicMock()
    result_proxy.scalar_one_or_none.return_value = note
    mock_db.execute = AsyncMock(return_value=result_proxy)
    mock_db.flush = AsyncMock()

    with patch(
        "app.services.note_formula_generator._load_cross_table_data",
        new_callable=AsyncMock,
        return_value={},
    ), patch(
        "app.services.note_formula_generator._resolve_cross_refs_via_acnr",
        new_callable=AsyncMock,
        return_value=[],
    ):
        from app.services.note_formula_generator import execute_note_formulas
        result = await execute_note_formulas(mock_db, _PROJECT, _YEAR, _SECTION)
    return result


class TestAutoCalcWritesBack:
    """auto_calc 类别公式正常回写"""

    @pytest.mark.asyncio
    async def test_auto_calc_writes_value_quantized(self):
        """auto_calc vertical_sum 公式写回量化到分的值（100.45 + 0.006 = 100.456 → 100.46）"""
        rows = [
            {"values": [100.45], "label": "子项1"},
            {"values": [0.006], "label": "子项2"},
            {"values": [None], "label": "合计"},  # target
        ]
        formulas = {
            "2:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)", "category": "auto_calc"},
        }
        note = _fake_note(rows, formulas)
        result = await _run_executor(note)

        # 值应被写回并量化到分
        assert note.table_data["rows"][2]["values"][0] == 100.46
        assert result["updated"] == 1
        assert result["executed"] >= 1
        assert formulas["2:0"]["last_value"] == 100.46

    @pytest.mark.asyncio
    async def test_auto_calc_mode_auto_writes(self):
        """_cell_modes == 'auto' 的格可以被写回（即使有旧值）"""
        rows = [
            {"values": [50.0], "label": "子项1"},
            {"values": [150.0], "label": "子项2"},
            {"values": [999.0], "label": "合计", "_cell_modes": {"0": "auto"}},
        ]
        formulas = {
            "2:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)", "category": "auto_calc"},
        }
        note = _fake_note(rows, formulas)
        result = await _run_executor(note)

        assert note.table_data["rows"][2]["values"][0] == 200.0
        assert result["updated"] == 1


class TestLogicCheckDoesNotWrite:
    """logic_check 类别公式不回写，只产出 checks"""

    @pytest.mark.asyncio
    async def test_logic_check_no_writeback(self):
        """logic_check 公式不修改单元格值，差额大时 status=failed"""
        rows = [
            {"values": [30.0], "label": "子项1"},
            {"values": [70.0], "label": "子项2"},
            {"values": [999.0], "label": "合计（手工填的）"},  # 期望 100，实际 999
        ]
        formulas = {
            "2:0": {
                "type": "vertical_sum",
                "expression": "SUM(0:1, 0)",
                "category": "logic_check",
                "description": "合计勾稽",
            },
        }
        note = _fake_note(rows, formulas)
        result = await _run_executor(note)

        # 值不变 — logic_check 不写回
        assert note.table_data["rows"][2]["values"][0] == 999.0
        assert result["updated"] == 0
        assert result["executed"] >= 1
        # checks 有产出
        assert len(result.get("checks", [])) >= 1
        check = result["checks"][0]
        assert check["status"] == "failed"  # 100 vs 999, diff >> 0.005

    @pytest.mark.asyncio
    async def test_reasonability_no_writeback(self):
        """reasonability 类别同样不回写"""
        rows = [
            {"values": [50.0], "label": "子项1"},
            {"values": [50.0], "label": "子项2"},
            {"values": [99.0], "label": "合计"},  # 期望 100，实际 99
        ]
        formulas = {
            "2:0": {
                "type": "vertical_sum",
                "expression": "SUM(0:1, 0)",
                "category": "reasonability",
            },
        }
        note = _fake_note(rows, formulas)
        result = await _run_executor(note)

        # 值不变
        assert note.table_data["rows"][2]["values"][0] == 99.0
        assert len(result.get("checks", [])) >= 1
        assert result["checks"][0]["status"] == "failed"  # diff=1.0 > 0.005

    @pytest.mark.asyncio
    async def test_logic_check_passed_when_close(self):
        """差额 <= 0.005 时校对结果为 passed"""
        rows = [
            {"values": [50.0], "label": "子项1"},
            {"values": [50.0], "label": "子项2"},
            {"values": [100.0], "label": "合计"},
        ]
        formulas = {
            "2:0": {
                "type": "vertical_sum",
                "expression": "SUM(0:1, 0)",
                "category": "logic_check",
            },
        }
        note = _fake_note(rows, formulas)
        result = await _run_executor(note)

        assert note.table_data["rows"][2]["values"][0] == 100.0  # 不回写
        assert len(result.get("checks", [])) >= 1
        assert result["checks"][0]["status"] == "passed"


class TestManualCellNotOverwritten:
    """手工格不被覆盖"""

    @pytest.mark.asyncio
    async def test_manual_mode_cell_skipped(self):
        """_cell_modes 标记为 manual 的格不覆盖"""
        rows = [
            {"values": [100.0], "label": "子项1"},
            {"values": [999.0], "label": "合计", "_cell_modes": {"0": "manual"}},
        ]
        formulas = {
            "1:0": {"type": "vertical_sum", "expression": "SUM(0:0, 0)", "category": "auto_calc"},
        }
        note = _fake_note(rows, formulas)
        result = await _run_executor(note)

        assert note.table_data["rows"][1]["values"][0] == 999.0
        assert any(r.get("status") == "skipped_manual" for r in result.get("results", []))

    @pytest.mark.asyncio
    async def test_no_mode_foreign_value_not_overwritten(self):
        """没有模式、有值、非本执行器写入（no last_value） → 不覆盖"""
        rows = [
            {"values": [100.0], "label": "子项1"},
            {"values": [999.0], "label": "合计"},  # 有值，没 mode，没 last_value
        ]
        formulas = {
            "1:0": {"type": "vertical_sum", "expression": "SUM(0:0, 0)", "category": "auto_calc"},
        }
        note = _fake_note(rows, formulas)
        result = await _run_executor(note)

        assert note.table_data["rows"][1]["values"][0] == 999.0
        assert any(r.get("status") == "skipped_manual" for r in result.get("results", []))


class TestLastValueOverwrite:
    """上次本执行器写入值可以被新值覆盖"""

    @pytest.mark.asyncio
    async def test_last_value_match_allows_overwrite(self):
        """当前值 == last_value → 可覆盖"""
        rows = [
            {"values": [200.0], "label": "子项1"},
            {"values": [100.0], "label": "合计"},  # 上次写入 100.0
        ]
        formulas = {
            "1:0": {
                "type": "vertical_sum",
                "expression": "SUM(0:0, 0)",
                "category": "auto_calc",
                "last_value": 100.0,  # 上次写入 == 当前值
            },
        }
        note = _fake_note(rows, formulas)
        result = await _run_executor(note)

        assert note.table_data["rows"][1]["values"][0] == 200.0
        assert result["updated"] == 1


class TestChecksInResult:
    """返回体中 checks 字段存在且正确"""

    @pytest.mark.asyncio
    async def test_checks_key_in_result(self):
        """result 包含 checks 键"""
        rows = [
            {"values": [10.0], "label": "子项"},
            {"values": [None], "label": "合计"},
        ]
        formulas = {
            "1:0": {"type": "vertical_sum", "expression": "SUM(0:0, 0)", "category": "auto_calc"},
        }
        note = _fake_note(rows, formulas)
        result = await _run_executor(note)
        assert "checks" in result
