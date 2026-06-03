# Feature: custom-workpaper-formula-binding, Property — extract_custom_cells 单元测试（任务 4.10）
"""extract_custom_cells 两种 parsed_data 结构 + 中文行名。"""

from app.services.address_registry import extract_custom_cells


def test_html_data_nested_scalar_cell():
    parsed = {
        "html_data": {
            "审定表": {
                "cells": {
                    "A5": "货币资金",
                    "B5": 1000,
                }
            }
        }
    }
    recs = extract_custom_cells(parsed)
    by_cell = {(r.sheet, r.cell): r for r in recs}
    assert ("审定表", "B5") in by_cell
    assert by_cell[("审定表", "B5")].row_label == "货币资金"
    assert by_cell[("审定表", "B5")].value == 1000


def test_html_data_nested_dict_cell_value():
    parsed = {
        "html_data": {
            "Sheet1": {
                "cells": {
                    "C12": {"value": 99, "label": "期末余额"},
                }
            }
        }
    }
    recs = extract_custom_cells(parsed)
    assert len(recs) == 1
    assert recs[0].cell == "C12"
    assert recs[0].row_label == "期末余额"
    assert recs[0].value == 99


def test_flat_sheet_field_structure():
    parsed = {
        "明细表": {
            "A3": "应收账款",
            "D3": 500,
        }
    }
    recs = extract_custom_cells(parsed)
    cells = {r.cell for r in recs if r.sheet == "明细表"}
    assert "A3" in cells
    assert "D3" in cells


def test_bad_input_returns_empty():
    assert extract_custom_cells(None) == []
    assert extract_custom_cells({}) == []
    assert extract_custom_cells({"html_data": "bad"}) == []
