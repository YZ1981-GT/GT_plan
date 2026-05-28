"""Sprint A.2.10 — is_empty 计算单测.

覆盖：
  1. 全 None values → empty
  2. 全 0 values → empty
  3. 任意非 0 数值 → 非空
  4. 任意非空字符串 → 非空
  5. 跳过 header_label / total / subtotal / dynamic_anchor / dynamic_marker_end
  6. 合计行有值但 data 行空 → empty（合计是衍生值，不算原始数据）
  7. 多表 _tables：任一非空 → 非空
  8. None / 非 dict / 缺 rows → empty
  9. threshold 阈值生效（绝对值 ≤ threshold 视为空）
 10. 章节级 is_section_empty — text_content / table_data 双重判定
 11. ORM duck-typing 兼容（SimpleNamespace 模拟）
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.note_is_empty_calc import (
    is_section_empty,
    is_table_data_empty,
)


# ---------------------------------------------------------------------------
# 1) 全 None / 全 0
# ---------------------------------------------------------------------------


def test_all_none_values_is_empty() -> None:
    td = {
        "rows": [
            {"label": "A", "values": [None, None], "row_type": "data"},
            {"label": "B", "values": [None, None], "row_type": "dynamic_data"},
        ],
    }
    assert is_table_data_empty(td) is True


def test_all_zero_values_is_empty() -> None:
    td = {
        "rows": [
            {"label": "A", "values": [0, 0], "row_type": "data"},
            {"label": "B", "values": [0.0, Decimal("0")], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td) is True


# ---------------------------------------------------------------------------
# 2) 任意非 0 / 非空字符串
# ---------------------------------------------------------------------------


def test_any_nonzero_value_is_not_empty() -> None:
    td = {
        "rows": [
            {"label": "A", "values": [None, 100.0], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td) is False


def test_negative_value_is_not_empty() -> None:
    """负数也算非空."""
    td = {
        "rows": [
            {"label": "A", "values": [-50.0], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td) is False


def test_text_value_is_not_empty() -> None:
    td = {
        "rows": [
            {"label": "A", "values": ["银行存款"], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td) is False


def test_empty_string_treated_as_empty() -> None:
    td = {
        "rows": [
            {"label": "A", "values": ["", "   "], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td) is True


# ---------------------------------------------------------------------------
# 3) 跳过非数据行
# ---------------------------------------------------------------------------


def test_total_row_with_value_does_not_count() -> None:
    """合计行有值但 data 行空 → empty（合计是衍生值）."""
    td = {
        "rows": [
            {"label": "A", "values": [None], "row_type": "data"},
            {"label": "合计", "values": [9999.0], "row_type": "total"},
        ],
    }
    assert is_table_data_empty(td) is True


def test_subtotal_row_with_value_does_not_count() -> None:
    td = {
        "rows": [
            {"label": "A", "values": [None], "row_type": "data"},
            {"label": "小计", "values": [9999.0], "row_type": "subtotal"},
        ],
    }
    assert is_table_data_empty(td) is True


def test_is_total_legacy_field_skipped() -> None:
    """is_total=True 的行也跳过（兼容老 schema）."""
    td = {
        "rows": [
            {"label": "A", "values": [None]},
            {"label": "合计", "values": [9999.0], "is_total": True},
        ],
    }
    assert is_table_data_empty(td) is True


def test_header_and_anchor_rows_skipped() -> None:
    td = {
        "rows": [
            {"label": "标题", "values": ["银行存款"], "row_type": "header_label"},
            {"label": "anchor", "values": ["占位"], "row_type": "dynamic_anchor"},
            {"label": "marker", "values": ["占位"], "row_type": "dynamic_marker_end"},
            {"label": "A", "values": [None], "row_type": "data"},
        ],
    }
    # header_label / dynamic_anchor / dynamic_marker_end 跳过 → 真正 data 行空
    assert is_table_data_empty(td) is True


# ---------------------------------------------------------------------------
# 4) 多表 _tables
# ---------------------------------------------------------------------------


def test_multi_tables_all_empty() -> None:
    td = {
        "_tables": [
            {"name": "T1", "rows": [{"label": "A", "values": [None], "row_type": "data"}]},
            {"name": "T2", "rows": [{"label": "B", "values": [0], "row_type": "data"}]},
        ],
    }
    assert is_table_data_empty(td) is True


def test_multi_tables_any_nonempty_returns_false() -> None:
    td = {
        "_tables": [
            {"name": "T1", "rows": [{"label": "A", "values": [None], "row_type": "data"}]},
            {"name": "T2", "rows": [{"label": "B", "values": [100.0], "row_type": "data"}]},
        ],
    }
    assert is_table_data_empty(td) is False


# ---------------------------------------------------------------------------
# 5) 边界
# ---------------------------------------------------------------------------


def test_none_or_non_dict_is_empty() -> None:
    assert is_table_data_empty(None) is True
    assert is_table_data_empty("not a dict") is True  # type: ignore[arg-type]
    assert is_table_data_empty([]) is True  # type: ignore[arg-type]


def test_missing_rows_is_empty() -> None:
    assert is_table_data_empty({}) is True
    assert is_table_data_empty({"headers": ["x"]}) is True


def test_empty_rows_list_is_empty() -> None:
    assert is_table_data_empty({"rows": []}) is True


# ---------------------------------------------------------------------------
# 6) threshold
# ---------------------------------------------------------------------------


def test_threshold_value_below_treated_as_empty() -> None:
    """绝对值 ≤ threshold 视为空."""
    td = {
        "rows": [
            {"label": "A", "values": [0.005], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td, threshold=0.01) is True
    assert is_table_data_empty(td, threshold=0.0) is False


def test_threshold_negative_clamped_to_zero() -> None:
    """负 threshold 钳制到 0."""
    td = {
        "rows": [
            {"label": "A", "values": [0.5], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td, threshold=-100) is False


# ---------------------------------------------------------------------------
# 7) 章节级 is_section_empty
# ---------------------------------------------------------------------------


def test_section_empty_when_no_text_no_table() -> None:
    note = {"text_content": "", "table_data": None}
    assert is_section_empty(note) is True


def test_section_nonempty_when_text_present() -> None:
    note = {
        "text_content": "本章节描述了银行存款的构成情况。",
        "table_data": None,
    }
    assert is_section_empty(note) is False


def test_section_nonempty_when_table_has_data() -> None:
    note = {
        "text_content": "",
        "table_data": {
            "rows": [{"label": "A", "values": [100.0], "row_type": "data"}]
        },
    }
    assert is_section_empty(note) is False


def test_section_empty_when_text_only_whitespace() -> None:
    note = {"text_content": "   \n\t  ", "table_data": {"rows": []}}
    assert is_section_empty(note) is True


def test_section_with_orm_like_object() -> None:
    """duck-typing：SimpleNamespace 模拟 ORM 实例也兼容."""
    note = SimpleNamespace(
        text_content="",
        table_data={"rows": [{"label": "A", "values": [None], "row_type": "data"}]},
    )
    assert is_section_empty(note) is True

    note2 = SimpleNamespace(
        text_content="",
        table_data={"rows": [{"label": "A", "values": [100.0], "row_type": "data"}]},
    )
    assert is_section_empty(note2) is False


def test_section_empty_handles_none_input() -> None:
    assert is_section_empty(None) is True


# ---------------------------------------------------------------------------
# 8) 数据兼容
# ---------------------------------------------------------------------------


def test_decimal_zero_treated_as_empty() -> None:
    td = {
        "rows": [
            {"label": "A", "values": [Decimal("0.00")], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td) is True


def test_decimal_nonzero_treated_as_nonempty() -> None:
    td = {
        "rows": [
            {"label": "A", "values": [Decimal("0.01")], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td) is False


def test_invalid_value_types_treated_as_empty() -> None:
    """非数值非字符串（如 list / dict）→ 视为空."""
    td = {
        "rows": [
            {"label": "A", "values": [[], {}, None], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td) is True


def test_string_numeric_zero_is_empty() -> None:
    """字符串 "0" / "0.0" 解析为数字 → 视为空."""
    td = {
        "rows": [
            {"label": "A", "values": ["0", "0.0"], "row_type": "data"},
        ],
    }
    assert is_table_data_empty(td) is True
