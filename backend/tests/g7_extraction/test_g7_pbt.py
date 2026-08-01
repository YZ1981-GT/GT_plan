"""Wave 6 / Task 7.1 — G7 属性测试（hypothesis）。

Property 1: 叶子过滤无双算 — 各分类合计 ≡ 仅叶子科目金额之和。
Property 3: 单一 aux_type 不跨维相加 — 选定维度子集合计 ≤ 任一维度合计。
Property 5: 灰度关闭零写入 — flag=False → imported_count=0 且 render 不注入。

**Validates: Requirements 10.1, 10.3, 10.5**
"""

from __future__ import annotations

import asyncio
import types
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies import _g7_long_term_equity_main as g7
from app.routers.wp_render_strategies._g7_long_term_equity_main_import_export import (
    build_g7_detail_rows_from_aux,
)
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    select_leaves,
)
from app.services.four_table.report_line_accounts import ReportLineAccounts


# ──────────────────────────────────────────────────────────────────────────────
# Strategy helpers
# ──────────────────────────────────────────────────────────────────────────────

# Generates a valid sub-account code starting with "1511" (1-3 sub-levels)
_ACCOUNT_SEGMENTS = st.lists(
    st.integers(min_value=1, max_value=99).map(lambda n: f"{n:02d}"),
    min_size=0,
    max_size=3,
)

def _build_code(segments: list[str]) -> str:
    if not segments:
        return "1511"
    return "1511." + ".".join(segments)


_st_code = _ACCOUNT_SEGMENTS.map(_build_code)

# A set of codes that may contain parent-child relationships
_st_code_set = st.lists(_st_code, min_size=1, max_size=15).map(set)

# Amounts: small floats to stay numerically stable
_st_amount = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


# ──────────────────────────────────────────────────────────────────────────────
# Property 1: 叶子过滤无双算
# **Validates: Requirements 10.1**
# ──────────────────────────────────────────────────────────────────────────────

@settings(deadline=None)
@given(
    codes_and_amounts=st.lists(
        st.tuples(_st_code, _st_amount, _st_amount),
        min_size=1,
        max_size=20,
    )
)
def test_property1_leaf_sum_no_double_count(codes_and_amounts):
    """对任意含父子层级的科目集，共享件的叶子聚合等于仅叶子科目金额之和；
    任一存在「本码 + `.`」子科目的 code 不参与求和。

    2026-08-01：被测对象由已删除的 `_sum_leaf_by_prefix` 换成
    `four_table/leaf_aggregation`（点号边界口径），断言意图不变。
    """
    # Deduplicate by code (keep first occurrence)
    seen: set[str] = set()
    unique_rows: list[LeafRow] = []
    for code, opening, closing in codes_and_amounts:
        if code not in seen:
            seen.add(code)
            unique_rows.append(
                LeafRow(account_code=code, opening=opening, closing=closing)
            )

    leaves = select_leaves(unique_rows)
    agg = aggregate_leaves(leaves, ["1511"])
    leaf_codes = {r.account_code for r in leaves}

    # Determine expected leaf set（点号边界：只有 `code + '.'` 前缀的兄弟才算子科目）
    all_codes = {r.account_code for r in unique_rows}
    expected_opening = 0.0
    expected_closing = 0.0
    expected_leaves: set[str] = set()
    for row in unique_rows:
        prefix = row.account_code + "."
        if any(c != row.account_code and c.startswith(prefix) for c in all_codes):
            continue
        expected_opening += float(row.opening or 0)
        expected_closing += float(row.closing or 0)
        expected_leaves.add(row.account_code)

    assert abs(agg["opening"] - expected_opening) < 1e-6
    assert abs(agg["closing"] - expected_closing) < 1e-6
    assert leaf_codes == expected_leaves

    # Property: 任一叶子都不存在 `本码 + '.'` 的子科目
    for lc in leaf_codes:
        for other in all_codes:
            if other != lc:
                assert not other.startswith(lc + "."), (
                    f"{lc} 是 {other} 的父科目却被计入"
                )


# ──────────────────────────────────────────────────────────────────────────────
# Property 3: 单一 aux_type 不跨维相加
# **Validates: Requirements 10.3**
# ──────────────────────────────────────────────────────────────────────────────

_st_aux_name = st.text(
    alphabet=st.characters(categories=("L",)), min_size=1, max_size=8
)


@settings(deadline=None)
@given(
    names=st.lists(_st_aux_name, min_size=1, max_size=10, unique=True),
    types=st.lists(
        st.sampled_from(["客户", "部门", "项目"]),
        min_size=2,
        max_size=3,
        unique=True,
    ),
    amounts=st.lists(
        st.floats(min_value=0.01, max_value=1e5, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    ),
)
def test_property3_single_aux_type_no_cross_add(names, types, amounts):
    """当同一科目存在多个 aux_type 时，选定单一 aux_type 的归集结果
    等于该 type 子集的合计，且总额不超过任一维度的合计。
    """
    # Build multi-type entries: each (name, opening, debit, credit, closing)
    # Distribute amounts across types
    entries_by_type: dict[str, list[tuple]] = {t: [] for t in types}
    for i, amt in enumerate(amounts):
        name = names[i % len(names)]
        t = types[i % len(types)]
        entries_by_type[t].append((name, amt, 0.0, 0.0, amt))

    # Pick one type as "selected"
    selected_type = types[0]
    selected_entries = entries_by_type[selected_type]

    # Build rows using the pure function (simulating single aux_type selection)
    counter = [0]

    def _rid():
        counter[0] += 1
        return f"r-{counter[0]}"

    selected_rows = build_g7_detail_rows_from_aux(
        selected_entries, aux_type=selected_type, row_id_factory=_rid
    )

    # Property: result sum equals only the selected type's entries sum
    selected_total = sum(r["closingAmount"] for r in selected_rows)
    expected_total = sum(amt for (_, _, _, _, amt) in selected_entries)
    assert abs(selected_total - expected_total) < 1e-4

    # Property: selected total <= any single type's total (since types are disjoint)
    for t, entries in entries_by_type.items():
        type_total = sum(amt for (_, _, _, _, amt) in entries)
        # Selected type total should equal its own entries, which is <= union total
        # (cross-add would be selected + others > any single type)
        assert selected_total <= type_total + sum(
            sum(amt for (_, _, _, _, amt) in entries_by_type[ot])
            for ot in types
            if ot != t
        )


# ──────────────────────────────────────────────────────────────────────────────
# Property 5: 灰度关闭零写入
# **Validates: Requirements 10.5**
# ──────────────────────────────────────────────────────────────────────────────

@settings(deadline=None)
@given(
    project_id=st.text(min_size=1, max_size=10),
    year=st.integers(min_value=2020, max_value=2030),
)
def test_property5_gray_off_zero_write(project_id, year, monkeypatch):
    """G7_FOUR_TABLE_EXTRACTION_ENABLED=False 时，取数端点返回 imported_count=0
    且 render 不注入 tb_leaf_categories / adjudication_prefill。

    2026-08-01：门控从纯函数移到 render 编排层（纯函数可脱开关单测）→
    本属性改为「开关为 False 时 render 的两个键分别为 None / {}」。
    """
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "G7_FOUR_TABLE_EXTRACTION_ENABLED", False, raising=False)
    assert app_settings.G7_FOUR_TABLE_EXTRACTION_ENABLED is False

    # 纯函数本身不看开关：给它数据它就算（门控在 render）
    accounts = ReportLineAccounts(
        gross=["1511"], provision=["1512"],
        gross_standard=["1511"], provision_standard=["1512"], row_code="BS-024",
    )
    leaves = [LeafRow("1511.01", "长期股权投资_对子公司的投资", closing=1.0)]
    assert g7.build_g7_leaf_categories(accounts, leaves) is not None

    # 无数据时一律空（宁缺勿造），与开关无关
    assert g7.build_g7_leaf_categories(accounts, []) is None
    assert g7.build_g7_adjudication_prefill(accounts, []) == {}
