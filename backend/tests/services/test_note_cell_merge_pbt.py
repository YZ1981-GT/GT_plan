"""Sprint A.2.9 — note_cell_merge 行+列三态合并 PBT.

使用 hypothesis 做 property-based testing，验证行级 + 列级合并的不变量：

行级 PBT（merge_table_data_preserving_cell_modes / merge_row_preserving_cell_modes）
  - PBT-R1：merge(td, td) 在 _cell_modes 全 auto / 无 _legacy 标时与 td 等价
  - PBT-R2：任何 _cell_modes[i]=='manual' 的 cell，merge 后 values[i] 不变
  - PBT-R3：任何 _cell_modes[i]=='locked' 的 cell，无论 new 是什么，old 值都保留

列级 PBT（merge_columns_preserving_cell_modes）
  - PBT-C1：合并后 _columns_meta 中 id 全表唯一（CI-3）
  - PBT-C2：合并后每行 len(values) == len(_columns_meta)
  - PBT-C3：列级 manual 跟随 col_id 而不是 col 位置（重排后值仍跟列）

普通单测（4 个）：
  - 边界 1：列消失 → _legacy_cells 保留
  - 边界 2：列增加 → 新列 cell_modes 默认 auto
  - 边界 3：列 id 重复 → 抛 ValueError
  - 边界 4：纯函数 — 不 mutate 入参

Validates: Requirements R1.3 验收 10/11/12 + Sprint A.2.9 + CI-3
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from app.services.note_cell_merge import (
    merge_columns_preserving_cell_modes,
    merge_row_preserving_cell_modes,
    merge_table_data_preserving_cell_modes,
)


# ---------------------------------------------------------------------------
# 通用 strategies
# ---------------------------------------------------------------------------


_finite_floats = st.floats(
    min_value=-1e6,
    max_value=1e6,
    allow_nan=False,
    allow_infinity=False,
).map(lambda x: round(x, 2))

_cell_value = st.one_of(_finite_floats, st.none())
_mode = st.sampled_from(["auto", "manual", "locked"])


@st.composite
def row_strategy(
    draw: st.DrawFn, *, n_cols: int, modes_required: bool = False
) -> dict[str, Any]:
    """生成单 row：固定列数 + values + _cell_modes + _cell_meta."""
    label = draw(
        st.text(
            min_size=1,
            max_size=8,
            alphabet=st.characters(min_codepoint=65, max_codepoint=90),  # A-Z
        )
    )
    values = draw(st.lists(_cell_value, min_size=n_cols, max_size=n_cols))
    if modes_required:
        modes = {str(i): draw(_mode) for i in range(n_cols)}
    else:
        modes = {}
        for i in range(n_cols):
            if draw(st.booleans()):
                modes[str(i)] = draw(_mode)
    meta = {
        str(i): {"manual_value": None, "semantic": None, "binding_id": None}
        for i in range(n_cols)
    }
    return {
        "label": label,
        "values": values,
        "_cell_modes": modes,
        "_cell_meta": meta,
        "row_type": "data",
    }


@st.composite
def table_data_strategy(draw: st.DrawFn) -> dict[str, Any]:
    """生成单表 table_data：含 _columns_meta + rows."""
    n_cols = draw(st.integers(min_value=1, max_value=5))
    n_rows = draw(st.integers(min_value=0, max_value=10))
    columns_meta = [
        {"id": f"col_{i}", "label": f"L{i}", "col_type": "fixed"}
        for i in range(n_cols)
    ]
    # 保证 row labels 唯一（避免 label 对齐歧义）— 用 row_<idx>
    rows = []
    for r in range(n_rows):
        row = draw(row_strategy(n_cols=n_cols))
        row["label"] = f"row_{r}"
        rows.append(row)
    return {"_columns_meta": columns_meta, "rows": rows}


# ===========================================================================
# 行级 PBT
# ===========================================================================


class TestRowMergePBT:
    """行级三态合并 PBT — 验证核心不变量."""

    @given(td=table_data_strategy())
    @settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pbt_merge_idempotent_when_all_auto(self, td: dict[str, Any]) -> None:
        """PBT-R1：所有 cell 都是 auto 时，merge(td, td) 的 values 与 td 等价.

        Validates: Requirements R1.3 验收 10
        """
        # 把所有 cell 都设为 auto
        td_auto = copy.deepcopy(td)
        for r in td_auto["rows"]:
            r["_cell_modes"] = {}  # 默认 auto

        merged = merge_table_data_preserving_cell_modes(td_auto, td_auto)

        for i, row in enumerate(td_auto["rows"]):
            assert merged["rows"][i]["values"] == row["values"]
            assert merged["rows"][i]["label"] == row["label"]

    @given(td=table_data_strategy())
    @settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pbt_manual_value_always_preserved(self, td: dict[str, Any]) -> None:
        """PBT-R2：任何 _cell_modes[i]=='manual' 的 cell，merge 后 values[i] 不变.

        Validates: Requirements R1.3 验收 11
        """
        # 给每行随机选一些 col 设为 manual
        old_td = copy.deepcopy(td)
        for r in old_td["rows"]:
            n = len(r["values"])
            modes = {}
            for i in range(n):
                if i % 2 == 0:
                    modes[str(i)] = "manual"
                else:
                    modes[str(i)] = "auto"
            r["_cell_modes"] = modes

        # 构造一个完全不同的 new_td（值都改）
        new_td = copy.deepcopy(td)
        for r in new_td["rows"]:
            r["values"] = [9999.99] * len(r["values"])
            # new 不带 _cell_modes（模板权威）
            r.pop("_cell_modes", None)

        merged = merge_table_data_preserving_cell_modes(old_td, new_td)

        for old_row, merged_row in zip(old_td["rows"], merged["rows"]):
            for i in range(len(old_row["values"])):
                if old_row["_cell_modes"].get(str(i)) == "manual":
                    assert merged_row["values"][i] == old_row["values"][i], (
                        f"manual cell at i={i} should be preserved, "
                        f"got {merged_row['values'][i]}"
                    )

    @given(td=table_data_strategy())
    @settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pbt_locked_value_never_recomputed(self, td: dict[str, Any]) -> None:
        """PBT-R3：任何 _cell_modes[i]=='locked' 的 cell，无论 new 是什么，old 值都保留.

        Validates: Requirements R1.3 验收 12
        """
        old_td = copy.deepcopy(td)
        for r in old_td["rows"]:
            n = len(r["values"])
            r["_cell_modes"] = {str(i): "locked" for i in range(n)}

        new_td = copy.deepcopy(td)
        for r in new_td["rows"]:
            r["values"] = [-12345.67] * len(r["values"])
            r.pop("_cell_modes", None)

        merged = merge_table_data_preserving_cell_modes(old_td, new_td)

        for old_row, merged_row in zip(old_td["rows"], merged["rows"]):
            assert merged_row["values"] == old_row["values"]


# ===========================================================================
# 列级 PBT
# ===========================================================================


@st.composite
def column_meta_strategy(draw: st.DrawFn, *, prefix: str = "col") -> dict[str, Any]:
    idx = draw(st.integers(min_value=0, max_value=20))
    return {
        "id": f"{prefix}_{idx}",
        "label": f"L_{idx}",
        "col_type": "fixed",
    }


@st.composite
def col_merge_table_strategy(draw: st.DrawFn) -> dict[str, Any]:
    """生成 _columns_meta + 对应行的 table_data（保证 col_id 唯一）."""
    n_cols = draw(st.integers(min_value=1, max_value=5))
    # 从一个固定 pool 中无重抽样得到唯一 col_id（避免 reject sampling 慢）
    col_ids = draw(
        st.lists(
            st.sampled_from([f"col_{i}" for i in range(20)]),
            min_size=n_cols,
            max_size=n_cols,
            unique=True,
        )
    )
    columns = [
        {"id": cid, "label": cid.upper(), "col_type": "fixed"} for cid in col_ids
    ]
    n_rows = draw(st.integers(min_value=0, max_value=8))
    rows = []
    for r in range(n_rows):
        row = draw(row_strategy(n_cols=n_cols))
        row["label"] = f"row_{r}"
        rows.append(row)
    return {"_columns_meta": columns, "rows": rows}


class TestColumnMergePBT:
    """列级三态合并 PBT — 加列 / 删列 / 重排都不破坏不变量."""

    @given(
        old_td=col_merge_table_strategy(),
        new_td=col_merge_table_strategy(),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pbt_column_id_uniqueness_after_merge(
        self, old_td: dict[str, Any], new_td: dict[str, Any]
    ) -> None:
        """PBT-C1：合并后 _columns_meta 中 id 全表唯一（CI-3）."""
        merged = merge_columns_preserving_cell_modes(old_td, new_td)
        ids = [
            c["id"]
            for c in merged.get("_columns_meta", [])
            if isinstance(c, dict) and "id" in c
        ]
        assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"

    @given(
        old_td=col_merge_table_strategy(),
        new_td=col_merge_table_strategy(),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pbt_value_alignment_after_merge(
        self, old_td: dict[str, Any], new_td: dict[str, Any]
    ) -> None:
        """PBT-C2：合并后每行 len(values) == len(_columns_meta)."""
        merged = merge_columns_preserving_cell_modes(old_td, new_td)
        n_cols = len(merged.get("_columns_meta", []))
        for row in merged.get("rows", []):
            if not isinstance(row, dict):
                continue
            assert len(row.get("values", [])) == n_cols, (
                f"row.values len {len(row.get('values', []))} != n_cols {n_cols}"
            )

    @given(td=col_merge_table_strategy())
    @settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pbt_manual_follows_col_id_after_reorder(
        self, td: dict[str, Any]
    ) -> None:
        """PBT-C3：列重排后，manual cell 仍按 col_id 跟随（不按位置）."""
        n_cols = len(td["_columns_meta"])
        if n_cols < 2:
            return  # 重排无意义

        # 把所有 cell 设为 manual
        old_td = copy.deepcopy(td)
        for r in old_td["rows"]:
            r["_cell_modes"] = {str(i): "manual" for i in range(n_cols)}

        # new = 列顺序倒置 + values 全改
        new_td = copy.deepcopy(td)
        new_td["_columns_meta"] = list(reversed(new_td["_columns_meta"]))
        for r in new_td["rows"]:
            r["values"] = [9999.0] * n_cols
            r.pop("_cell_modes", None)

        merged = merge_columns_preserving_cell_modes(old_td, new_td)

        # 每行：检查 col_id → value 映射在合并后跟随原 col_id
        old_col_ids = [c["id"] for c in old_td["_columns_meta"]]
        new_col_ids = [c["id"] for c in merged["_columns_meta"]]

        for old_row, merged_row in zip(old_td["rows"], merged["rows"]):
            for old_pos, cid in enumerate(old_col_ids):
                if cid not in new_col_ids:
                    continue
                new_pos = new_col_ids.index(cid)
                # manual 应保留 old.values[old_pos]
                assert merged_row["values"][new_pos] == old_row["values"][old_pos], (
                    f"col_id {cid} manual value not preserved after reorder"
                )


# ===========================================================================
# 普通单测（边界场景）
# ===========================================================================


def test_column_disappearance_preserves_in_legacy_cells() -> None:
    """边界 1：旧列消失 → values 删除，_legacy_cells 保留."""
    old_td = {
        "_columns_meta": [
            {"id": "col_a", "label": "A"},
            {"id": "col_b", "label": "B"},
        ],
        "rows": [
            {
                "label": "R1",
                "values": [10.0, 20.0],
                "_cell_modes": {"0": "manual", "1": "manual"},
                "_cell_meta": {
                    "0": {"manual_value": 10.0, "semantic": None, "binding_id": None},
                    "1": {"manual_value": 20.0, "semantic": None, "binding_id": None},
                },
            },
        ],
    }
    new_td = {
        "_columns_meta": [{"id": "col_a", "label": "A"}],  # col_b 消失
        "rows": [{"label": "R1", "values": [99.0]}],
    }

    merged = merge_columns_preserving_cell_modes(old_td, new_td)

    assert len(merged["_columns_meta"]) == 1
    assert merged["rows"][0]["values"] == [10.0]  # col_a manual 保留
    legacy = merged["rows"][0].get("_legacy_cells", {})
    assert "col_b" in legacy
    assert legacy["col_b"]["value"] == 20.0
    assert legacy["col_b"]["mode"] == "manual"


def test_new_column_added_default_auto_mode() -> None:
    """边界 2：新列加入 → cell_modes 默认 auto，值用 new."""
    old_td = {
        "_columns_meta": [{"id": "col_a", "label": "A"}],
        "rows": [
            {
                "label": "R1",
                "values": [10.0],
                "_cell_modes": {"0": "manual"},
                "_cell_meta": {
                    "0": {"manual_value": 10.0, "semantic": None, "binding_id": None}
                },
            }
        ],
    }
    new_td = {
        "_columns_meta": [
            {"id": "col_a", "label": "A"},
            {"id": "col_new", "label": "NEW"},
        ],
        "rows": [{"label": "R1", "values": [88.0, 999.0]}],
    }

    merged = merge_columns_preserving_cell_modes(old_td, new_td)

    # col_a manual 保留 → 10
    # col_new 新列 auto → 用 new = 999
    assert merged["rows"][0]["values"] == [10.0, 999.0]
    # col_new 在 _cell_modes 中应该没显式 manual（默认 auto）
    modes = merged["rows"][0].get("_cell_modes", {})
    assert modes.get("1") in (None, "auto")


def test_duplicate_column_id_in_new_raises() -> None:
    """边界 3：new._columns_meta 含重复 id → 抛 ValueError（CI-3）."""
    old_td = {"_columns_meta": [{"id": "x"}], "rows": []}
    new_td = {
        "_columns_meta": [{"id": "x"}, {"id": "x"}],
        "rows": [],
    }
    with pytest.raises(ValueError, match="duplicate column id"):
        merge_columns_preserving_cell_modes(old_td, new_td)


def test_pure_function_does_not_mutate_input() -> None:
    """边界 4：纯函数 — 入参 old / new 不被修改."""
    old_td = {
        "_columns_meta": [{"id": "col_a"}, {"id": "col_b"}],
        "rows": [
            {
                "label": "R1",
                "values": [10.0, 20.0],
                "_cell_modes": {"0": "manual"},
                "_cell_meta": {
                    "0": {"manual_value": None, "semantic": None, "binding_id": None}
                },
            }
        ],
    }
    new_td = {
        "_columns_meta": [{"id": "col_a"}, {"id": "col_c"}],  # col_b 消失，col_c 新增
        "rows": [{"label": "R1", "values": [99.0, 88.0]}],
    }
    old_snap = copy.deepcopy(old_td)
    new_snap = copy.deepcopy(new_td)

    _ = merge_columns_preserving_cell_modes(old_td, new_td)

    assert old_td == old_snap
    assert new_td == new_snap


def test_column_merge_falls_back_to_row_merge_when_no_columns_meta() -> None:
    """退化：new 缺 _columns_meta → 行级合并兼容路径."""
    old_td = {
        "rows": [
            {
                "label": "R1",
                "values": [10.0],
                "_cell_modes": {"0": "manual"},
                "_cell_meta": {
                    "0": {"manual_value": 10.0, "semantic": None, "binding_id": None}
                },
            }
        ],
    }
    new_td = {"rows": [{"label": "R1", "values": [99.0]}]}

    merged = merge_columns_preserving_cell_modes(old_td, new_td)

    # 走行级合并 → manual 保留
    assert merged["rows"][0]["values"] == [10.0]


def test_old_row_extra_marked_legacy_with_remapped_columns() -> None:
    """老行独有 → 追加 + _legacy_row=True，按 new_meta 列结构对齐."""
    old_td = {
        "_columns_meta": [{"id": "col_a"}, {"id": "col_b"}],
        "rows": [
            {
                "label": "R1",
                "values": [10.0, 20.0],
                "_cell_modes": {"0": "manual", "1": "manual"},
                "_cell_meta": {
                    "0": {"manual_value": 10.0, "semantic": None, "binding_id": None},
                    "1": {"manual_value": 20.0, "semantic": None, "binding_id": None},
                },
            },
            {
                "label": "OLD-EXTRA",
                "values": [50.0, 60.0],
                "_cell_modes": {"0": "manual", "1": "locked"},
                "_cell_meta": {
                    "0": {"manual_value": 50.0, "semantic": None, "binding_id": None},
                    "1": {"manual_value": 60.0, "semantic": None, "binding_id": None},
                },
            },
        ],
    }
    new_td = {
        "_columns_meta": [{"id": "col_a"}, {"id": "col_b"}],
        "rows": [{"label": "R1", "values": [88.0, 88.0]}],  # 缺 OLD-EXTRA
    }

    merged = merge_columns_preserving_cell_modes(old_td, new_td)

    assert len(merged["rows"]) == 2
    legacy = merged["rows"][1]
    assert legacy["label"] == "OLD-EXTRA"
    assert legacy.get("_legacy_row") is True
    # manual + locked 都保留旧值
    assert legacy["values"] == [50.0, 60.0]
