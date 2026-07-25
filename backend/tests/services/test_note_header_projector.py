"""note_header_projector 单元测试：legacy 空表头从 _cell_meta 语义派生。"""

from __future__ import annotations

from app.services.note_header_projector import (
    derive_headers_for_legacy_table,
    project_headers,
)


def _row(label, values, semantics):
    cm = {str(i): {"semantic": s} for i, s in enumerate(semantics)}
    return {"label": label, "values": values, "_cell_meta": cm}


def test_two_col_balance_pattern():
    """货币资金式 期末/上年 两列 → [项目, 期末余额, 上年年末余额]."""
    td = {
        "headers": [],
        "rows": [
            _row("库存现金", [376.73, None], ["closing_balance", "prior_year_value"]),
            _row("银行存款", [9182196.26, 1000.0], ["closing_balance", "prior_year_value"]),
        ],
    }
    assert derive_headers_for_legacy_table(td) == ["项目", "期末余额", "上年年末余额"]


def test_four_col_movement_pattern():
    """变动表 期初/增/减/期末 四列。"""
    td = {
        "headers": [],
        "rows": [
            _row("A", [1, 2, 3, 4], [
                "opening_balance", "current_year_increase",
                "current_year_decrease", "closing_balance",
            ]),
        ],
    }
    assert derive_headers_for_legacy_table(td) == [
        "项目", "期初余额", "本期增加", "本期减少", "期末余额",
    ]


def test_missing_semantic_col_blank_label():
    """无语义的值列 → 空标签，但列仍在（长度对齐 values）。"""
    td = {
        "headers": [],
        "rows": [_row("X", [1, 2], ["closing_balance", None])],
    }
    assert derive_headers_for_legacy_table(td) == ["项目", "期末余额", ""]


def test_no_cell_meta_uses_value_count():
    """行无 _cell_meta 但有 values → 按 values 长度出空标签列头。"""
    td = {"headers": [], "rows": [{"label": "X", "values": [1, 2]}]}
    assert derive_headers_for_legacy_table(td) == ["项目", "", ""]


def test_zero_value_cols_label_only():
    """无值列文本清单表 → 仅标签列。"""
    td = {"headers": [], "rows": [{"label": "条款一", "values": []}]}
    assert derive_headers_for_legacy_table(td) == ["项目"]


def test_existing_headers_untouched():
    td = {"headers": ["项目", "金额"], "rows": [_row("A", [1], ["closing_balance"])]}
    assert derive_headers_for_legacy_table(td) is None


def test_multitable_skipped():
    td = {"headers": [], "_tables": [{"name": "x"}], "rows": [_row("A", [1], ["cost"])]}
    assert derive_headers_for_legacy_table(td) is None


def test_empty_rows_skipped():
    assert derive_headers_for_legacy_table({"headers": [], "rows": []}) is None
    assert derive_headers_for_legacy_table({"headers": []}) is None
    assert derive_headers_for_legacy_table(None) is None


def test_project_headers_returns_new_dict_not_mutating():
    td = {"headers": [], "rows": [_row("A", [1], ["closing_balance"])]}
    out = project_headers(td)
    assert out is not None
    assert out["headers"] == ["项目", "期末余额"]
    assert td["headers"] == []  # 入参未被修改
    # rows 引用保留（浅拷贝）
    assert out["rows"] is td["rows"]


def test_project_headers_none_when_not_applicable():
    td = {"headers": ["项目", "金额"], "rows": [_row("A", [1], ["cost"])]}
    assert project_headers(td) is None


def test_max_value_len_across_rows():
    """列数取所有行 values 长度最大值（首行短、后行长）。"""
    td = {
        "headers": [],
        "rows": [
            {"label": "A", "values": [1]},
            _row("B", [1, 2, 3], ["cost", "closing_balance", "prior_year_value"]),
        ],
    }
    assert derive_headers_for_legacy_table(td) == [
        "项目", "成本", "期末余额", "上年年末余额",
    ]
