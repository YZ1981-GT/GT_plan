"""附注空表判定 —— 后端侧。

🔴 本文件的用例与前端 `disclosureEmptyTable.spec.ts` **逐条镜像**（同名 case + 同预期），
任一侧改判定规则必须同步另一侧，否则模块页折叠与 Word 导出省略会出现两套口径。

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R4.1 / Task 1.3-1.4
Properties: Property 8（空表判定不吞非空数据）
"""
from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.note_empty_table_detector import (
    AMOUNT_FORMATS,
    SKIP_ROW_TYPES,
    empty_table_names,
    is_empty_table,
)

# ─── 固定夹具：模仿 F2 存货「开发成本」（单级 7 列，4 个数值列）─────────────
DEV_COST_COLUMNS: list[dict[str, Any]] = [
    {"key": "project_name", "label": "项目名称", "is_label": True, "flat": True},
    {"key": "start_date", "label": "开工时间"},
    {"key": "expected_complete_date", "label": "预计竣工时间"},
    {"key": "estimated_investment", "label": "预计总投资", "format": "amount"},
    {"key": "end_balance", "label": "期末数", "format": "amount"},
    {"key": "prior_balance", "label": "上年年末数", "format": "amount"},
    {"key": "end_impairment", "label": "期末跌价准备", "format": "amount"},
]


def _row(label: str, values: list[Any], **kw: Any) -> dict[str, Any]:
    return {"label": label, "values": values, "is_total": False, **kw}


# ════════════════════════════════════════════════════════════════════
# 基本判定
# ════════════════════════════════════════════════════════════════════


def test_no_rows_is_empty():
    assert is_empty_table([], DEV_COST_COLUMNS) is True


def test_none_rows_is_empty():
    assert is_empty_table(None, DEV_COST_COLUMNS) is True


def test_template_skeleton_with_labels_only_is_empty():
    """🔴 关键：模板骨架恒有行标签，若标签算进去则永不为空。"""
    rows = [
        _row("原材料", [None] * 6),
        _row("在产品", [None] * 6),
        _row("库存商品", [None] * 6),
    ]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is True


def test_all_zero_amounts_is_empty():
    rows = [_row("A 项目", ["", "", 0, 0, 0, 0])]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is True


def test_one_nonzero_amount_is_not_empty():
    rows = [_row("A 项目", ["", "", 0, 1200000.55, 0, 0])]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is False


def test_text_column_filled_is_not_empty():
    """文本列（开工时间）有内容也算非空。"""
    rows = [_row("A 项目", ["2024-03", "", 0, 0, 0, 0])]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is False


def test_tiny_amount_below_half_cent_is_empty():
    """< 半分视为零（附注金额保留 2 位小数）。"""
    rows = [_row("A", ["", "", 0.001, -0.004, 0, 0])]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is True


def test_one_cent_is_not_empty():
    rows = [_row("A", ["", "", 0.01, 0, 0, 0])]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is False


# ════════════════════════════════════════════════════════════════════
# 派生行 / 结构行不参与判定
# ════════════════════════════════════════════════════════════════════


def test_total_row_alone_is_empty():
    """只有合计行（派生值）→ 仍是空表，不能因合计有数就说有业务。"""
    rows = [
        _row("原材料", [None] * 6),
        {"label": "合计", "values": ["", "", 0, 0, 0, 0], "is_total": True},
    ]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is True


def test_total_row_with_value_does_not_make_table_nonempty():
    rows = [
        _row("原材料", [None] * 6),
        {"label": "合计", "values": ["", "", 0, 999, 0, 0], "is_total": True},
    ]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is True


@pytest.mark.parametrize("row_type", sorted(SKIP_ROW_TYPES))
def test_skipped_row_types_do_not_count(row_type: str):
    rows = [
        {"label": "一、账面原值", "values": ["", "", 123, 0, 0, 0], "row_type": row_type},
    ]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is True


def test_data_row_after_section_row_counts():
    """段标题行不算，其后的数据行要算（数据资源表形态）。"""
    rows = [
        {"label": "一、账面原值", "values": [None] * 6, "row_type": "section"},
        _row("1.期初余额", ["", "", 0, 100, 0, 0]),
    ]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is False


# ════════════════════════════════════════════════════════════════════
# 列定义缺省 / 异常形态
# ════════════════════════════════════════════════════════════════════


def test_no_columns_treats_all_as_text():
    """无列定义时按文本判定：'0' 是文本零 → 非空（保守，不吞数据）。"""
    rows = [_row("A", ["0"])]
    assert is_empty_table(rows, None) is False


def test_no_columns_blank_strings_is_empty():
    rows = [_row("A", ["", "   ", None])]
    assert is_empty_table(rows, None) is True


def test_values_shorter_than_columns_is_tolerated():
    rows = [_row("A", ["", ""])]  # 只给 2 个值，列有 6 个
    assert is_empty_table(rows, DEV_COST_COLUMNS) is True


def test_values_longer_than_columns_extra_treated_as_text():
    rows = [_row("A", ["", "", 0, 0, 0, 0, "额外"])]
    assert is_empty_table(rows, DEV_COST_COLUMNS) is False


def test_non_dict_rows_are_skipped():
    assert is_empty_table(["not a dict", None, 42], DEV_COST_COLUMNS) is True


def test_values_not_a_list_is_skipped():
    assert is_empty_table([{"label": "A", "values": "oops"}], DEV_COST_COLUMNS) is True


def test_columns_without_is_label_drops_first_column():
    """无 is_label 时按投影器规则把第一列当标签列（values 从第 2 列起对齐）。"""
    cols = [
        {"key": "name", "label": "项目"},
        {"key": "amt", "label": "金额", "format": "amount"},
    ]
    assert is_empty_table([_row("A", [0])], cols) is True
    assert is_empty_table([_row("A", [5])], cols) is False


# ════════════════════════════════════════════════════════════════════
# 数值文本形态（千分符 / 括号负数 / 非数值）
# ════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "val,expect_empty",
    [
        ("0", True),
        ("0.00", True),
        ("1,234.50", False),
        ("1，234.50", False),   # 全角逗号
        ("(500)", False),        # 括号负数
        ("(0)", True),
        ("  ", True),
        ("不适用", False),        # 数值列里的说明文字 → 视为有内容，不吞
    ],
)
def test_amount_string_forms(val: str, expect_empty: bool):
    cols = [
        {"key": "label", "label": "项目", "is_label": True},
        {"key": "amt", "label": "金额", "format": "amount"},
    ]
    assert is_empty_table([_row("A", [val])], cols) is expect_empty


@pytest.mark.parametrize("fmt", sorted(AMOUNT_FORMATS))
def test_all_amount_formats_treat_zero_as_blank(fmt: str):
    cols = [
        {"key": "label", "label": "项目", "is_label": True},
        {"key": "v", "label": "值", "format": fmt},
    ]
    assert is_empty_table([_row("A", [0])], cols) is True
    assert is_empty_table([_row("A", [1])], cols) is False


# ════════════════════════════════════════════════════════════════════
# 批量
# ════════════════════════════════════════════════════════════════════


def test_empty_table_names_keeps_order():
    tables = [
        {"name": "存货分类", "columns": DEV_COST_COLUMNS,
         "rows": [_row("原材料", ["", "", 0, 100, 0, 0])]},
        {"name": "开发成本", "columns": DEV_COST_COLUMNS, "rows": [_row("A", [None] * 6)]},
        {"name": "开发产品", "columns": DEV_COST_COLUMNS, "rows": []},
        {"name": "周转房", "columns": DEV_COST_COLUMNS, "rows": [_row("B", [None] * 6)]},
    ]
    assert empty_table_names(tables) == ["开发成本", "开发产品", "周转房"]


def test_empty_table_names_tolerates_garbage():
    assert empty_table_names(None) == []
    assert empty_table_names(["x", 1, None]) == []


# ════════════════════════════════════════════════════════════════════
# PBT — Property 8：任一非零数值或非空文本 → 必返回 False
# ════════════════════════════════════════════════════════════════════

_AMOUNT_COLS = [
    {"key": "label", "label": "项目", "is_label": True},
    {"key": "a", "label": "A", "format": "amount"},
    {"key": "b", "label": "B", "format": "amount"},
]


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.lists(
        st.tuples(
            st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
            st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=6,
    )
)
def test_pbt_any_nonzero_amount_means_not_empty(pairs: list[tuple[float, float]]) -> None:
    rows = [_row(f"r{i}", [a, b]) for i, (a, b) in enumerate(pairs)]
    has_nonzero = any(abs(a) >= 0.005 or abs(b) >= 0.005 for a, b in pairs)
    assert is_empty_table(rows, _AMOUNT_COLS) is (not has_nonzero)


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.text(max_size=8), min_size=1, max_size=6))
def test_pbt_any_nonblank_text_means_not_empty(texts: list[str]) -> None:
    cols = [
        {"key": "label", "label": "项目", "is_label": True},
        {"key": "t", "label": "说明"},
    ]
    rows = [_row(f"r{i}", [t]) for i, t in enumerate(texts)]
    has_content = any(t.strip() for t in texts)
    assert is_empty_table(rows, cols) is (not has_content)


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False), min_size=1, max_size=5))
def test_pbt_total_rows_never_affect_result(vals: list[float]) -> None:
    """合计行无论填什么都不改变判定（Property 8 的推论）。"""
    base = [_row("r0", [0.0, 0.0])]
    with_total = base + [
        {"label": "合计", "values": [v, v], "is_total": True} for v in vals
    ]
    assert is_empty_table(with_total, _AMOUNT_COLS) is is_empty_table(base, _AMOUNT_COLS)
