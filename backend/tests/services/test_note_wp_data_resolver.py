"""Sprint A.2.4 — wp_data 提数核心单测.

覆盖：
- extract_wp_cell (4 cases)
- extract_wp_table (5 cases)
- extract_wp_column_sum (3 cases)
- resolve_wp_data async (4 cases) — _wp_cache 命中 / DB 加载 / wp 不存在 / parsed_data 空

Validates: Requirements D3 / D4 + Sprint A.2.4 任务卡
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.note_source_resolvers import resolve_wp_data
from app.services.note_wp_data_resolver import (
    extract_wp_cell,
    extract_wp_column_sum,
    extract_wp_table,
)


# ===========================================================================
# extract_wp_cell (4 用例)
# ===========================================================================


class TestExtractWpCell:

    def test_hit_returns_decimal(self):
        """扁平 cells = {"sheet1!F5": 100} → Decimal(100)."""
        parsed = {"cells": {"分类构成!F5": 100}}
        val = extract_wp_cell(parsed, "分类构成", "F5")
        assert val == Decimal("100")

    def test_miss_returns_none(self):
        """空 cells → None."""
        assert extract_wp_cell({"cells": {}}, "s", "A1") is None
        assert extract_wp_cell({}, "s", "A1") is None

    def test_dict_value_extracts_value_field(self):
        """dict value {value, formula} → 取 value."""
        parsed = {"cells": {"s!A1": {"value": 50, "formula": "=B1+C1"}}}
        val = extract_wp_cell(parsed, "s", "A1")
        assert val == Decimal("50")

    def test_dict_value_v_field_compat(self):
        """dict value {v, f} 旧形态（Univer / wp_version_search 兼容）."""
        parsed = {"cells": {"s!A1": {"v": "75", "f": "=B1"}}}
        val = extract_wp_cell(parsed, "s", "A1")
        assert val == Decimal("75")

    def test_string_value_returns_str(self):
        """非数值字符串 → 原文本."""
        parsed = {"cells": {"s!A1": "审定数"}}
        val = extract_wp_cell(parsed, "s", "A1")
        assert val == "审定数"

    def test_nested_cells_format(self):
        """嵌套形态 cells[sheet][cell_ref] → 命中."""
        parsed = {"cells": {"分类构成": {"F5": 200}}}
        val = extract_wp_cell(parsed, "分类构成", "F5")
        assert val == Decimal("200")

    def test_invalid_cell_ref_returns_none(self):
        """非法 cell_ref → None（不抛）."""
        parsed = {"cells": {"s!A1": 1}}
        assert extract_wp_cell(parsed, "s", "INVALID") is None
        assert extract_wp_cell(parsed, "s", "") is None
        assert extract_wp_cell(parsed, "", "A1") is None


# ===========================================================================
# extract_wp_table (5 用例)
# ===========================================================================


class TestExtractWpTable:

    def test_basic_3_rows_2_cols(self):
        """3 行 × 2 列 → 3 dict."""
        parsed = {"cells": {
            "s!A2": "客户A", "s!F2": 100, "s!G2": 200,
            "s!A3": "客户B", "s!F3": 300, "s!G3": 400,
            "s!A4": "客户C", "s!F4": 500, "s!G4": 600,
        }}
        out = extract_wp_table(parsed, "s",
                               label_col="A",
                               value_cols={"col_end": "F", "col_start": "G"})
        assert len(out) == 3
        assert out[0]["label"] == "客户A"
        assert out[0]["values"]["col_end"] == Decimal("100")
        assert out[0]["values"]["col_start"] == Decimal("200")
        assert out[2]["label"] == "客户C"
        assert out[2]["values"]["col_end"] == Decimal("500")

    def test_row_filter_excludes_total_row(self):
        """is_total=False → 跳过 合计 行."""
        parsed = {"cells": {
            "s!A2": "客户A", "s!F2": 100,
            "s!A3": "客户B", "s!F3": 200,
            "s!A4": "合计",   "s!F4": 300,
        }}
        out = extract_wp_table(parsed, "s",
                               row_filter={"is_total": False},
                               label_col="A",
                               value_cols={"v": "F"})
        labels = [r["label"] for r in out]
        assert labels == ["客户A", "客户B"]

    def test_exclude_label_pattern_regex(self):
        """exclude_label_pattern='合计|小计' → regex 过滤."""
        parsed = {"cells": {
            "s!A2": "客户A",  "s!F2": 100,
            "s!A3": "小计",    "s!F3": 100,
            "s!A4": "客户B",  "s!F4": 200,
            "s!A5": "合计",    "s!F5": 300,
        }}
        out = extract_wp_table(parsed, "s",
                               row_filter={"exclude_label_pattern": "合计|小计"},
                               label_col="A",
                               value_cols={"v": "F"})
        labels = [r["label"] for r in out]
        assert labels == ["客户A", "客户B"]

    def test_empty_sheet_returns_empty_list(self):
        """无任何 cell → []."""
        assert extract_wp_table({"cells": {}}, "empty",
                                value_cols={"v": "A"}) == []
        assert extract_wp_table({}, "empty") == []

    def test_value_cols_multi_col_mapping(self):
        """多 col_id → col_letter 映射 → 多列输出."""
        parsed = {"cells": {
            "s!A1": "项目1",
            "s!B1": 10, "s!C1": 20, "s!D1": 30,
        }}
        out = extract_wp_table(parsed, "s",
                               label_col="A",
                               value_cols={
                                   "col_amount_end": "B",
                                   "col_amount_start": "C",
                                   "col_change": "D",
                               })
        assert len(out) == 1
        v = out[0]["values"]
        assert v["col_amount_end"] == Decimal("10")
        assert v["col_amount_start"] == Decimal("20")
        assert v["col_change"] == Decimal("30")

    def test_skips_completely_empty_rows(self):
        """label 空 + values 全空 → 跳过."""
        parsed = {"cells": {
            "s!A1": "客户A", "s!B1": 100,
            # 第 2 行完全空
            "s!A3": "客户B", "s!B3": 200,
        }}
        out = extract_wp_table(parsed, "s",
                               label_col="A",
                               value_cols={"v": "B"})
        labels = [r["label"] for r in out]
        assert labels == ["客户A", "客户B"]


# ===========================================================================
# extract_wp_column_sum (3 用例)
# ===========================================================================


class TestExtractWpColumnSum:

    def test_sum_with_row_range(self):
        """对 F2:F4 求和."""
        parsed = {"cells": {
            "s!F2": 100, "s!F3": 200, "s!F4": 300,
            "s!F5": 999,  # 超出 range
        }}
        val = extract_wp_column_sum(parsed, "s", "F", row_range=(2, 4))
        assert val == Decimal("600")

    def test_full_column_no_row_range(self):
        """row_range=None → 扫所有有数据的行."""
        parsed = {"cells": {
            "s!A1": "label1", "s!F1": 10,
            "s!A2": "label2", "s!F2": 20,
            "s!A3": "label3", "s!F3": 30,
        }}
        val = extract_wp_column_sum(parsed, "s", "F")
        assert val == Decimal("60")

    def test_empty_column_returns_none(self):
        """列无任何数值 → None."""
        assert extract_wp_column_sum({"cells": {}}, "s", "F", (1, 10)) is None
        # 列存在但无数字（仅文本）
        parsed = {"cells": {"s!F1": "header", "s!F2": "data"}}
        assert extract_wp_column_sum(parsed, "s", "F", (1, 2)) is None

    def test_mixed_types_only_sums_numbers(self):
        """混合数值 + 文本 → 仅累加数值."""
        parsed = {"cells": {
            "s!F1": "表头",
            "s!F2": 100,
            "s!F3": "N/A",
            "s!F4": 200,
            "s!F5": {"value": 50, "formula": "=A1"},
        }}
        val = extract_wp_column_sum(parsed, "s", "F", (1, 5))
        assert val == Decimal("350")

    def test_invalid_col_letter_returns_none(self):
        """非法列字母 → None."""
        assert extract_wp_column_sum({"cells": {}}, "s", "1A") is None
        assert extract_wp_column_sum({"cells": {}}, "s", "") is None


# ===========================================================================
# resolve_wp_data async (4 用例)
# ===========================================================================


def _ctx_for_wp(parsed_for: dict | None = None, db=None, project_id=None):
    """构造 wp_data 测试用 ctx — _wp_cache 直接缓存 parsed_data dict."""
    return {
        "project_id": project_id or uuid4(),
        "year": 2025,
        "db": db,
        "_wp_cache": dict(parsed_for or {}),
        "_tb_cache": {},
        "_prior_notes_cache": {},
    }


@pytest.mark.asyncio
async def test_wp_cache_hit_extract_cell():
    """_wp_cache 命中 + extract=cell → 取 cell 值."""
    ctx = _ctx_for_wp({
        "h08": {
            "wp_code": "h08",
            "cells": {"分类构成!F5": 12345.67},
        }
    })
    binding = {
        "source": "wp_data",
        "wp_code": "h08",
        "sheet": "分类构成",
        "extract": "cell",
        "cell_ref": "F5",
    }
    val = await resolve_wp_data(binding, ctx)
    assert val == Decimal("12345.67")


@pytest.mark.asyncio
async def test_wp_cache_miss_loads_from_db():
    """_wp_cache 未命中 + db 存在 → DB 加载 + 写回 cache."""
    parsed_data = {"wp_code": "h08", "cells": {"sheet1!A1": 42}}
    fake_wp = SimpleNamespace(parsed_data=parsed_data, is_deleted=False)

    db = MagicMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[fake_wp])
    result.scalars = MagicMock(return_value=scalars)
    db.execute = AsyncMock(return_value=result)

    ctx = _ctx_for_wp(db=db)
    assert "h08" not in ctx["_wp_cache"]

    binding = {
        "source": "wp_data",
        "wp_code": "h08",
        "sheet": "sheet1",
        "extract": "cell",
        "cell_ref": "A1",
    }
    val = await resolve_wp_data(binding, ctx)
    assert val == Decimal("42")
    # 缓存已写入
    assert "h08" in ctx["_wp_cache"]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_wp_not_found_returns_none():
    """DB 查不到匹配 wp_code → None."""
    db = MagicMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[])  # 空底稿列表
    result.scalars = MagicMock(return_value=scalars)
    db.execute = AsyncMock(return_value=result)

    ctx = _ctx_for_wp(db=db)
    binding = {
        "source": "wp_data",
        "wp_code": "missing_wp",
        "sheet": "s",
        "extract": "cell",
        "cell_ref": "A1",
    }
    val = await resolve_wp_data(binding, ctx)
    assert val is None


@pytest.mark.asyncio
async def test_parsed_data_empty_returns_none():
    """parsed_data 为空 dict / None → None."""
    ctx = _ctx_for_wp({"h08": {}})
    binding = {
        "source": "wp_data",
        "wp_code": "h08",
        "sheet": "s",
        "extract": "cell",
        "cell_ref": "A1",
    }
    assert await resolve_wp_data(binding, ctx) is None


@pytest.mark.asyncio
async def test_wp_data_extract_table_routes():
    """extract=table → 调 extract_wp_table 走多行返回."""
    ctx = _ctx_for_wp({
        "h08": {
            "wp_code": "h08",
            "cells": {
                "分类构成!A2": "客户A", "分类构成!F2": 100,
                "分类构成!A3": "客户B", "分类构成!F3": 200,
                "分类构成!A4": "合计",   "分类构成!F4": 300,
            },
        },
    })
    binding = {
        "source": "wp_data",
        "wp_code": "h08",
        "sheet": "分类构成",
        "extract": "table",
        "row_filter": {"is_total": False},
        "label_col": "A",
        "value_cols": {"col_end": "F"},
    }
    out = await resolve_wp_data(binding, ctx)
    assert isinstance(out, list)
    labels = [r["label"] for r in out]
    assert labels == ["客户A", "客户B"]
    assert out[0]["values"]["col_end"] == Decimal("100")


@pytest.mark.asyncio
async def test_wp_data_extract_column_sum_routes():
    """extract=column_sum → 调 extract_wp_column_sum."""
    ctx = _ctx_for_wp({
        "h08": {
            "wp_code": "h08",
            "cells": {
                "明细!F2": 100, "明细!F3": 200, "明细!F4": 300,
            },
        },
    })
    binding = {
        "source": "wp_data",
        "wp_code": "h08",
        "sheet": "明细",
        "extract": "column_sum",
        "col_letter": "F",
        "row_range": [2, 4],
    }
    val = await resolve_wp_data(binding, ctx)
    assert val == Decimal("600")


@pytest.mark.asyncio
async def test_wp_data_missing_wp_code_returns_none():
    """缺 wp_code / 缺 sheet → None（防御）."""
    ctx = _ctx_for_wp()
    assert await resolve_wp_data({"source": "wp_data"}, ctx) is None
    assert await resolve_wp_data({"source": "wp_data", "wp_code": "x"}, ctx) is None
