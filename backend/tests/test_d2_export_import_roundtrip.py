"""D2 导入导出往返契约验证（回归守卫）。

背景：现有 `test_d_cycle_export_import_verification.py` 只校验 componentType 注册，
不校验实际 xlsx 往返。批量 Tab 导入导出 Playwright 实测揭示 3 个真实 bug：
  1. `import_data`/`export_data` 用 `wb.active` 读/写 → 模板首个 sheet 是"编制说明"，
     导致所有 sheet 导入误读说明 sheet（列名不匹配）+ 导出数据误写说明 sheet。
  2. D2-2 曾用 2 行合并表头，与导入解析器（只读单行扁平表头）不兼容 → 导出模板无法被自身导入。

本测试锚定"导出模板必须能被自身导入校验通过"的往返契约（纯函数，无 DB）。
"""
from __future__ import annotations

import io

import openpyxl
import pytest

from app.routers.wp_render_strategies._d2_import_export import (
    _create_template_workbook,
    _select_data_ws,
    _validate_columns,
    _parse_rows,
    get_d2_2_columns,
)


class _Seg:
    """模拟 AgingSegment（仅需 key/label）。"""

    def __init__(self, key: str, label: str):
        self.key = key
        self.label = label


_SEGMENTS = [_Seg("within1", "1年以内"), _Seg("y1to2", "1-2年"), _Seg("y2to3", "2-3年")]


def _roundtrip_ws(sheet: str, segments=None):
    """生成模板 → 存取一轮 → 返回数据工作表（模拟真实导入的 load_workbook）。"""
    wb = _create_template_workbook(sheet, segments)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    wb2 = openpyxl.load_workbook(buf, data_only=True)
    return wb2, _select_data_ws(wb2, sheet)


@pytest.mark.parametrize("sheet", ["D2-1", "D2-3", "D2-4", "D2-6"])
def test_flat_sheet_template_passes_own_import_validation(sheet: str):
    """扁平表头 sheet：导出模板选中数据 sheet 后，导入列校验必须通过（无非法列）。"""
    _wb, ws = _roundtrip_ws(sheet)
    # 选中的必须是数据 sheet 而非"编制说明"
    assert ws.title != "编制说明", f"{sheet} 选中了编制说明 sheet"
    invalid = _validate_columns(ws, sheet)
    assert invalid == [], f"{sheet} 导出模板未通过自身导入校验：{invalid}"


def test_d2_2_multi_aging_template_passes_own_import_validation():
    """D2-2 动态账龄明细表：扁平表头导出模板必须通过自身导入校验（往返契约核心）。"""
    _wb, ws = _roundtrip_ws("D2-2", _SEGMENTS)
    assert ws.title != "编制说明"
    invalid = _validate_columns(ws, "D2-2")
    assert invalid == [], f"D2-2 导出模板未通过自身导入校验：{invalid}"


def test_d2_2_header_matches_get_d2_2_columns():
    """D2-2 模板表头必须与 get_d2_2_columns（导入解析器同源）逐列一致。"""
    _wb, ws = _roundtrip_ws("D2-2", _SEGMENTS)
    actual = [str(c.value).strip() for c in ws[1] if c.value is not None]
    expected = get_d2_2_columns(_SEGMENTS)
    assert actual == expected, f"D2-2 表头不匹配\nactual={actual}\nexpected={expected}"


def test_d2_2_filled_row_parses_with_aging_columns():
    """D2-2 填入一行数据后，_parse_rows 应读出该行且账龄扁平列均在。"""
    wb = _create_template_workbook("D2-2", _SEGMENTS)
    ws = _select_data_ws(wb, "D2-2")
    cols = get_d2_2_columns(_SEGMENTS)
    # 数据从第 2 行开始（扁平单行表头）
    row_vals = []
    for name in cols:
        if name == "序号":
            row_vals.append(1)
        elif name == "客户名称":
            row_vals.append("往返测试客户")
        elif name == "1年以内(期初审定)":
            row_vals.append(1000)
        else:
            row_vals.append("")
    ws.append(row_vals)
    # 回存后解析
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    wb2 = openpyxl.load_workbook(buf, data_only=True)
    ws2 = _select_data_ws(wb2, "D2-2")
    rows, _warning = _parse_rows(ws2, "D2-2")
    assert len(rows) == 1
    assert rows[0].get("客户名称") == "往返测试客户"
    # 账龄扁平列被保留（供 _parse_d2_2_rows 按 label 匹配）
    assert any("年" in k for k in rows[0].keys()), "账龄列未被保留"


def test_select_data_ws_skips_instruction_sheet():
    """_select_data_ws 必须跳过"编制说明"，选中真正的数据 sheet。"""
    wb = _create_template_workbook("D2-3")
    # 模板首个 sheet 是编制说明（active）
    assert wb.active.title == "编制说明"
    ws = _select_data_ws(wb, "D2-3")
    assert ws.title == "D2-3"
