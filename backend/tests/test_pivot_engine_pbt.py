"""PivotEngine 属性测试（advanced-query-module Task 10.3 / 10.4）.

本文件以 Hypothesis 实现 PivotEngine 的两条正确性属性：

- **Property 5**：结果/透视单元格 addr_id ⇔ 单一源格（Validates: Requirements 4.1, 4.5, 6.5, 6.6）。
  交叉单元格携带 addr_id（且可下钻）当且仅当其值恰由**单一可解析源格**产生；由多个源格
  聚合或无源格产生的单元格不携带 addr_id、渲染为不可下钻普通文本。
- **Property 11**：透视列基数上限（Validates: Requirements 6.4）。
  列维度产生的列数超过配置上限时，返回描述性错误标明实际列数与上限，不执行透视、
  不修改数据、不返回部分结果。

注：按平台测试提速铁律，每条属性显式使用 ``@settings(max_examples=5)``（优先于 conftest
的 fast profile），保持属性测试稳定且快速。
"""

from __future__ import annotations

import copy

import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.custom_query.pivot_engine import PivotConfig, PivotEngine


# ─────────────────────────────────────────────────────────────────────────────
# 生成器：随机源格组合（行维 × 列维 × 值 × 可选 addr_id）
# ─────────────────────────────────────────────────────────────────────────────
@st.composite
def _source_rows(draw):
    """随机平铺源行集合。

    - 行/列维度值取自小集合，令交叉单元格既可能无源、单源，也可能多源聚合。
    - 每行可选携带**唯一** addr_id（模拟可解析源格），以便断言单源保留精确身份。
    """
    n = draw(st.integers(min_value=0, max_value=8))
    rows: list[dict] = []
    for i in range(n):
        row = {
            "r": draw(st.sampled_from(["r0", "r1", "r2"])),
            "c": draw(st.sampled_from(["c0", "c1", "c2"])),
            "v": draw(st.integers(min_value=-100, max_value=100)),
        }
        if draw(st.booleans()):
            # 唯一 addr_id（含行序号），确保单源单元格携带精确身份
            row["addr_id"] = f"D2/S1/A{i}"
        rows.append(row)
    return rows


# Feature: advanced-query-module, Property 5: 结果/透视单元格 addr_id ⇔ 单一源格
@given(rows=_source_rows())
@settings(max_examples=5)
def test_p5_cell_addr_id_iff_single_source(rows):
    """交叉单元格携带 addr_id 当且仅当其值恰由单一可解析源格产生。

    Feature: advanced-query-module, Property 5: 结果/透视单元格 addr_id ⇔ 单一源格
    Validates: Requirements 4.1, 4.5, 6.5, 6.6
    """
    eng = PivotEngine()
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")
    grid = eng.pivot(rows, cfg)

    # 重算 (row_label, col_label) → 源行桶（单维度组合标签即维度值本身）
    buckets: dict[tuple, list[dict]] = {}
    for row in rows:
        buckets.setdefault((row["r"], row["c"]), []).append(row)

    for r_idx, rl in enumerate(grid.row_labels):
        for c_idx, cl in enumerate(grid.col_labels):
            cell = grid.cells[r_idx][c_idx]
            sources = buckets.get((rl, cl), [])
            single = len(sources) == 1
            single_resolvable = single and sources[0].get("addr_id") is not None

            # 核心 IFF：携带 addr_id ⇔ 恰一个携带 addr_id 的源格
            assert (cell.addr_id is not None) == single_resolvable

            if single:
                # 单源 → addr_id 精确等于该源格身份（可能为 None）
                assert cell.addr_id == sources[0].get("addr_id")
            else:
                # 无源（R6.7 空值）或多源聚合（R6.6 不可下钻）→ 不携带 addr_id
                assert cell.addr_id is None
                if not sources:
                    assert cell.value is None  # 空组合 → None（非 0）


# ─────────────────────────────────────────────────────────────────────────────
# Property 11: 透视列基数上限
# ─────────────────────────────────────────────────────────────────────────────
# Feature: advanced-query-module, Property 11: 透视列基数上限
@given(
    n_cols=st.integers(min_value=1, max_value=20),
    limit=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=5)
def test_p11_pivot_col_cardinality_limit(n_cols, limit):
    """列数超上限 → 描述性错误标明实际列数与上限，不执行、不修改数据、无部分结果。

    Feature: advanced-query-module, Property 11: 透视列基数上限
    Validates: Requirements 6.4
    """
    eng = PivotEngine()
    # 单行维度 + n_cols 个不同列值 → 列组合基数恰为 n_cols
    rows = [{"r": "a", "c": f"col{i}", "v": i} for i in range(n_cols)]
    original = copy.deepcopy(rows)
    cfg = PivotConfig(row_dims=["r"], col_dims=["c"], value_field="v", agg="sum")

    if n_cols > limit:
        with pytest.raises(HTTPException) as ei:
            eng.pivot(rows, cfg, max_cols=limit)
        detail = ei.value.detail
        assert ei.value.status_code == 400
        assert detail["error_code"] == "PIVOT_COL_LIMIT"
        # 描述性错误标明实际列数与上限
        assert detail["actual"] == n_cols
        assert detail["limit"] == limit
        assert str(n_cols) in detail["message"]
        assert str(limit) in detail["message"]
        # 不修改数据 / 不返回部分结果（纯函数，入参不被 mutate）
        assert rows == original
    else:
        grid = eng.pivot(rows, cfg, max_cols=limit)
        assert grid.n_cols == n_cols  # 未超上限 → 正常执行
