"""CP-02 防御：Word 导出保留多级表头的全部叶子列（空标题不裁）。

已复现缺陷（建议文档 §12.2 / §23.6）：
上市 五-5-2 有 6 列，其中 4 个 headers 为空串（子表头占位），`valid_indices` 把它们裁掉
→ 6 列变 2 列，5 个金额标记只保留 1 个。

修复：有 _column_groups / multi_header 时跳过空列裁剪。
本测试用 DOCX 保存后再读，逐列验证金额标记保留和列数正确。
"""
from __future__ import annotations

import io

import pytest
from docx import Document

from app.services.note_word_exporter import NoteWordExporter


def _exporter() -> NoteWordExporter:
    return NoteWordExporter(db=None)


def _render_and_read(table_data: dict) -> list[list[str]]:
    """渲染一张表到 DOCX BytesIO，再读回所有行的单元格文本。"""
    exporter = _exporter()
    doc = Document()
    exporter._render_table(doc, table_data)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    doc2 = Document(buf)
    assert len(doc2.tables) == 1, f"期望 1 张表，实际 {len(doc2.tables)}"
    return [[c.text.strip() for c in row.cells] for row in doc2.tables[0].rows]


# ─── 上市 五-5-2（6 列，无 _column_groups，headers[1:] 全空）─────────────────


def _listed_five_5_2() -> dict:
    """上市应收账款分类表：6 列，headers 只有 index 0 非空。"""
    return {
        "headers": ["类  别", "", "", "", "", ""],
        "multi_header": [
            ["类  别", "期末余额", "", "", "", ""],
            ["", "账面余额", "", "坏账准备", "", "账面价值"],
            ["", "金额", "比例(%)", "金额", "预期信用损失率(%)", ""],
        ],
        "rows": [
            {"label": "按单项计提", "cells": [
                {"value": 101}, {"value": 102}, {"value": 103}, {"value": 104}, {"value": 105},
            ]},
        ],
    }


def test_listed_6col_all_leaf_columns_preserved():
    """上市 6 列空标题不被裁掉，5 个金额标记全保留。"""
    rows = _render_and_read(_listed_five_5_2())
    # 至少 header + 1 data row
    assert len(rows) >= 2
    data_row = rows[-1]
    assert len(data_row) == 6, f"期望 6 列，实际 {len(data_row)} 列：{data_row}"
    # 5 个金额列的值都不为空
    amounts = [c for c in data_row[1:] if c]
    assert len(amounts) == 5, f"期望 5 个金额，实际 {len(amounts)}：{data_row}"


# ─── 上市带 _column_groups 的 6 列 ──────────────────────────────────────────


def _listed_with_column_groups() -> dict:
    """上市 6 列 + _column_groups（由 multi_header_to_column_groups 生成）。"""
    return {
        "headers": ["类  别", "", "", "", "", ""],
        "_column_groups": [{"group": "期末余额", "start": 1, "span": 5}],
        "rows": [
            {"label": "行1", "cells": [
                {"value": 201}, {"value": 202}, {"value": 203}, {"value": 204}, {"value": 205},
            ]},
        ],
    }


def test_listed_with_column_groups_preserves_all_columns():
    rows = _render_and_read(_listed_with_column_groups())
    data_row = rows[-1]
    assert len(data_row) == 6, f"期望 6 列，实际 {len(data_row)}：{data_row}"
    amounts = [c for c in data_row[1:] if c]
    assert len(amounts) == 5, f"期望 5 个金额：{data_row}"


# ─── 国企 11 列 + _column_groups ─────────────────────────────────────────────


def _soe_11col() -> dict:
    return {
        "headers": ["类  别", "", "", "", "", "", "", "", "", "", ""],
        "_column_groups": [
            {"group": "期末数", "start": 1, "span": 5},
            {"group": "期初数", "start": 6, "span": 5},
        ],
        "multi_header": [
            ["类  别", "期末数", "", "", "", "", "期初数", "", "", "", ""],
            ["", "账面余额", "", "坏账准备", "", "账面价值", "账面余额", "", "坏账准备", "", "账面价值"],
            ["", "金额", "比例(%)", "金额", "预期信用损失率(%)", "", "金额", "比例(%)", "金额", "预期信用损失率(%)", ""],
        ],
        "rows": [
            {"label": "行1", "cells": [
                {"value": i * 100 + 1} for i in range(10)
            ]},
        ],
    }


def test_soe_11col_all_leaf_columns_preserved():
    rows = _render_and_read(_soe_11col())
    data_row = rows[-1]
    assert len(data_row) == 11, f"期望 11 列，实际 {len(data_row)}：{data_row}"
    amounts = [c for c in data_row[1:] if c]
    assert len(amounts) == 10, f"期望 10 个金额：{data_row}"


# ─── 扁平表（无 multi_header/column_groups）的空列仍被裁 ────────────────────


def _flat_with_empty_cols() -> dict:
    return {
        "headers": ["项目", "", "期末", "", "期初"],
        "rows": [
            {"label": "行1", "cells": [
                {"value": 10}, {"value": 20}, {"value": 30}, {"value": 40},
            ]},
        ],
    }


def test_flat_table_still_trims_empty_columns():
    """无分组表头的废空列仍被裁掉（兼容旧行为）。"""
    rows = _render_and_read(_flat_with_empty_cols())
    data_row = rows[-1]
    # headers 裁掉 index 1 和 3，剩 ["项目", "期末", "期初"] = 3 列
    assert len(data_row) == 3, f"期望 3 列：{data_row}"


# ─── 变异证明：删掉修复后上市 6 列应只剩 2 列 ────────────────────────────────


def test_mutation_proof_old_logic_would_lose_columns():
    """证明旧逻辑（总是裁空标题）会把上市 6 列裁成 1~2 列。"""
    td = _listed_five_5_2()
    headers = td["headers"]
    old_valid = [i for i, h in enumerate(headers) if h and str(h).strip()]
    # 旧逻辑只保留 index 0（"类  别"），其余全空被裁
    assert old_valid == [0], f"旧逻辑应只保留 index 0，实际 {old_valid}"
