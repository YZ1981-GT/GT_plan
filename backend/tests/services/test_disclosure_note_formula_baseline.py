"""Characterization 基线 — 附注公式数据补全 spec Wave 0 (Task 1.1).

Spec:   .kiro/specs/disclosure-note-formula-data-population/
Design: §「Wave 0 核实结论」V4/V5/V8/V10/V11/V17
Reqs:   6.1 / 6.5

目的
----
在写入任何公式 binding **之前**锁定既有行为，作为后续 Property 8 / 10 / 12 的
逐字节对照基线：

- ``_backfill_totals`` 的求和范围口径（上一合计行之后 → 本合计行之前的**所有
  非合计行**，含 header_label 行；None 跳过）—— §V8
- ``_build_with_binding`` 的输出行序（= 模板 rows 列表序，**含 header_label 与
  合计行**）、``num_value_cols = len(headers) - 1``、缺 binding 的候选格
  ``values=None`` + ``_cell_modes='manual'`` —— §V4/V5，Property 10 的"声明性
  差异"对照点
- ``_cell_value_from_table`` 的 R/C 坐标口径（1-based，R 含合计行、C 为数值列
  序号不含 label 列）—— Property 7 参照
- ``_resolve_formula_sum`` 现有**纯字符串 cells** 写法的求值结果 —— Property 8
  向后兼容对照
- 灰度关闭时 ``resolve_formula`` 对所有 source 一律返 None —— Property 10 内核

pre-existing 失败基线（§V17，零回归门须以此区分，**不得**混为本 spec 回归）
-------------------------------------------------------------------------
``tests/services/test_disclosure_engine_v2.py``：7 failed / 53 passed
  1. test_seven_sources_have_resolvers            （断言 len(VALID_SOURCES)==8，代码已 9）
  2. test_binding_json_valid_sources_match        （json valid_sources 8 项缺 consol_aggregation）
  3. test_load_templates_merges_custom_override
  4. test_load_templates_inserts_custom_only_section
  5. test_load_templates_sorted_by_sort_order
  6. test_load_templates_no_custom_returns_baseline_only
  7. test_load_templates_custom_branch_unchanged
``tests/services/test_note_template_bindings.py``：全绿（含 cell.source ∈ 8 项
枚举断言 —— 故本 spec 不得写 ``source='sum'``，见 §V11）
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.disclosure_engine import DisclosureEngine
from app.services.note_source_resolvers import (
    _cell_value_from_table,
    _resolve_formula_sum,
    resolve_formula,
)

PRE_EXISTING_FAILURES_ENGINE_V2 = (
    "test_seven_sources_have_resolvers",
    "test_binding_json_valid_sources_match",
    "test_load_templates_merges_custom_override",
    "test_load_templates_inserts_custom_only_section",
    "test_load_templates_sorted_by_sort_order",
    "test_load_templates_no_custom_returns_baseline_only",
    "test_load_templates_custom_branch_unchanged",
)


def _make_engine() -> DisclosureEngine:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._wp_fine_cache = {}
    eng._prior_notes_cache = {}
    return eng


# ---------------------------------------------------------------------------
# §V8 —— _backfill_totals 求和范围口径
# ---------------------------------------------------------------------------


def test_backfill_totals_sums_all_non_total_rows_since_previous_total():
    """合计口径 = 上一合计行之后 → 本行之前的所有非合计行（含 header_label）。"""
    rows = [
        {"label": "分组一", "row_type": "header_label", "values": [None, None]},
        {"label": "甲", "row_type": "data", "values": [1.0, 10.0]},
        {"label": "乙", "row_type": "data", "values": [2.0, 20.0]},
        {"label": "小计一", "row_type": "subtotal", "is_total": True, "values": [None, None]},
        {"label": "丙", "row_type": "data", "values": [3.0, None]},
        {"label": "合计", "row_type": "total", "is_total": True, "values": [None, None]},
    ]
    DisclosureEngine._backfill_totals(rows, 2)

    # 小计一 = 甲 + 乙（header_label 行 values 全 None 不贡献）
    assert rows[3]["values"] == [3.0, 30.0]
    # 合计 = 上一个合计行之后的 丙（**不含**小计一之前的行）
    assert rows[5]["values"] == [3.0, None]


def test_backfill_totals_first_row_total_is_skipped():
    """首行即合计 → 不回填（i == 0 直接 continue）。"""
    rows = [
        {"label": "合计", "row_type": "total", "is_total": True, "values": [None]},
        {"label": "甲", "row_type": "data", "values": [5.0]},
    ]
    DisclosureEngine._backfill_totals(rows, 1)
    assert rows[0]["values"] == [None]


def test_backfill_totals_all_none_keeps_none():
    """范围内全无数值 → 保持 None（不写 0）。"""
    rows = [
        {"label": "甲", "row_type": "data", "values": [None]},
        {"label": "合计", "row_type": "total", "is_total": True, "values": [None]},
    ]
    DisclosureEngine._backfill_totals(rows, 1)
    assert rows[1]["values"] == [None]


# ---------------------------------------------------------------------------
# §V4/V5 —— _build_with_binding 行序 / 列数 / manual placeholder
# ---------------------------------------------------------------------------


def _template_with_header_label() -> dict:
    return {
        "headers": ["项目", "期初余额", "本期增加", "本期减少", "期末余额"],
        "rows": [
            {"label": "分类", "row_type": "header_label"},
            {"label": "甲资产", "row_type": "data"},
            {"label": "乙资产", "row_type": "data"},
            {"label": "合计", "row_type": "total", "is_total": True},
        ],
    }


def _binding_all_manual_todo() -> dict:
    def _cell() -> dict:
        return {
            "source": "manual",
            "field": "value",
            "account_codes": [],
            "mode": "manual",
            "todo": "待审计师手工填",
        }

    row = {
        "row_type": "data",
        "binding": {
            "opening_balance": _cell(),
            "current_year_increase": _cell(),
            "current_year_decrease": _cell(),
            "closing_balance": _cell(),
        },
    }
    return {
        "table_index": 0,
        "table_name": "变动表",
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            {"text": "期初余额", "semantic": "opening_balance"},
            {"text": "本期增加", "semantic": "current_year_increase"},
            {"text": "本期减少", "semantic": "current_year_decrease"},
            {"text": "期末余额", "semantic": "closing_balance"},
        ],
        # bindings 的 rows 是 dict keyed by label 且**排除 header_label 行**（§V4）
        "rows": {"甲资产": row, "乙资产": dict(row), "合计": {"row_type": "total"}},
    }


@pytest.mark.asyncio
async def test_build_with_binding_row_order_equals_template_rows():
    """输出 rows = 模板 rows 列表序（含 header_label 与合计行）—— 坐标 R 的基准。"""
    eng = _make_engine()
    out = await eng._build_with_binding(
        uuid4(), 2025, "八、99", _template_with_header_label(), _binding_all_manual_todo()
    )
    assert [r["label"] for r in out["rows"]] == ["分类", "甲资产", "乙资产", "合计"]
    # bindings rows dict 序（排除 header_label）与之**不同** —— §V4 反例
    assert list(_binding_all_manual_todo()["rows"].keys()) != [
        r["label"] for r in out["rows"]
    ]


@pytest.mark.asyncio
async def test_build_with_binding_num_value_cols_excludes_label_column():
    """values 长度 = len(headers) - 1（label 列不在 values 内）—— 坐标 C 的基准。"""
    eng = _make_engine()
    tpl = _template_with_header_label()
    out = await eng._build_with_binding(
        uuid4(), 2025, "八、99", tpl, _binding_all_manual_todo()
    )
    expected = len(tpl["headers"]) - 1
    for row in out["rows"]:
        assert len(row["values"]) == expected


@pytest.mark.asyncio
async def test_build_with_binding_manual_todo_cells_are_none_and_mode_manual():
    """manual+todo 候选格基线：values=None + _cell_modes='manual'。

    本 spec 把候选格改写为公式 binding 后，灰度关闭时 values **仍为 None**，
    但 _cell_modes 会变为 'auto'（Property 10 唯一声明性差异）。
    """
    eng = _make_engine()
    out = await eng._build_with_binding(
        uuid4(), 2025, "八、99", _template_with_header_label(), _binding_all_manual_todo()
    )
    data_row = out["rows"][1]
    assert data_row["values"] == [None, None, None, None]
    assert data_row["_cell_modes"] == {"0": "manual", "1": "manual", "2": "manual", "3": "manual"}
    assert data_row["_cell_meta"]["3"]["semantic"] == "closing_balance"
    # header_label 行无 binding → 全 manual placeholder
    assert out["rows"][0]["values"] == [None, None, None, None]


# ---------------------------------------------------------------------------
# Property 7 参照 —— _cell_value_from_table 坐标口径
# ---------------------------------------------------------------------------


def test_cell_value_from_table_coordinate_is_one_based_and_excludes_label():
    table_data = {
        "rows": [
            {"label": "分类", "values": [None, None]},
            {"label": "甲", "values": [11.0, 22.0]},
        ]
    }
    # R2C1 → rows[1].values[0]
    assert _cell_value_from_table(table_data, {"cell": "R2C1"}) == 11.0
    assert _cell_value_from_table(table_data, {"cell": "R2C2"}) == 22.0
    # 越界 → None（fail-open）
    assert _cell_value_from_table(table_data, {"cell": "R9C1"}) is None
    assert _cell_value_from_table(table_data, {"cell": "R2C9"}) is None


# ---------------------------------------------------------------------------
# Property 8 参照 —— _resolve_formula_sum 纯字符串 cells 写法
# ---------------------------------------------------------------------------


@pytest.fixture()
def formula_flag_on(monkeypatch):
    from app.core import config

    monkeypatch.setattr(
        config.settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", True, raising=False
    )
    return True


@pytest.mark.asyncio
async def test_resolve_formula_sum_pure_string_cells_baseline(formula_flag_on):
    """纯字符串 cells 逐项相加（当前唯一写法）—— 扩展后必须逐字节一致。"""
    ctx = {
        "cell_values": {"R2C1": 100.0, "R2C2": 30.0, "R2C3": 10.0},
        "db": None,
        "project_id": None,
        "year": 2025,
    }
    val = await _resolve_formula_sum({"cells": ["R2C1", "R2C2", "R2C3"]}, ctx)
    assert val == pytest.approx(140.0)


@pytest.mark.asyncio
async def test_resolve_formula_sum_skips_missing_cells(formula_flag_on):
    ctx = {"cell_values": {"R2C1": 5.0}, "db": None, "project_id": None, "year": 2025}
    assert await _resolve_formula_sum({"cells": ["R2C1", "R9C9"]}, ctx) == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_resolve_formula_sum_all_missing_returns_none(formula_flag_on):
    ctx = {"cell_values": {}, "db": None, "project_id": None, "year": 2025}
    assert await _resolve_formula_sum({"cells": ["R2C1"]}, ctx) is None


@pytest.mark.asyncio
async def test_resolve_formula_sum_empty_cells_returns_none(formula_flag_on):
    ctx = {"cell_values": {"R2C1": 1.0}, "db": None, "project_id": None, "year": 2025}
    assert await _resolve_formula_sum({"cells": []}, ctx) is None


# ---------------------------------------------------------------------------
# Property 10 内核 —— 灰度关闭时公式家族一律 None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["sum", "report", "aging", "formula", "manual"])
async def test_resolve_formula_returns_none_when_flag_off(monkeypatch, source):
    from app.core import config

    monkeypatch.setattr(
        config.settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", False, raising=False
    )
    ctx = {
        "cell_values": {"R2C1": 1.0},
        "report_data": {"BS-002": 9.0},
        "aging_data": {"1年以内": 3.0},
        "db": None,
        "project_id": None,
        "year": 2025,
    }
    binding = {
        "source": source,
        "cells": ["R2C1"],
        "row_code": "BS-002",
        "band": "1年以内",
    }
    assert await resolve_formula(binding, ctx) is None
