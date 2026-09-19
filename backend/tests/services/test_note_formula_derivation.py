"""派生纯函数单测 + PBT（Wave 1 / Task 2.2 + 2.3）.

Spec:   .kiro/specs/disclosure-note-formula-data-population/
Design: 决策 2 / 3 / 4 / 5；§V4 / V7 / V8 / V15
Props:  Property 3 / 4 / 5 / 6 / 7 / 16
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hypothesis import given, settings as hyp_settings, strategies as st

from app.services.disclosure_engine import DisclosureEngine
from app.services.note_formula_derivation import (
    MOVEMENT_QUAD,
    NON_SUMMABLE_SEMANTICS,
    SEM_CLOSING,
    SEM_DECREASE,
    SEM_INCREASE,
    SEM_OPENING,
    cell_coord,
    count_candidate_cells,
    derive_movement_identity,
    derive_note_formulas,
    derive_sum_formula,
    split_semantic,
    value_col_semantics,
)
from app.services.note_source_resolvers import _cell_value_from_table


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _manual_todo() -> dict[str, Any]:
    return {
        "source": "manual",
        "field": "value",
        "account_codes": [],
        "mode": "manual",
        "todo": "待审计师手工填",
    }


def _tb_cell() -> dict[str, Any]:
    return {
        "source": "trial_balance",
        "field": "audited_amount",
        "account_codes": ["1001"],
        "mode": "auto",
        "agg": "sum",
    }


def _movement_template(
    *, with_header_label: bool = True, dup_label: bool = False
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if with_header_label:
        rows.append({"label": "分类", "row_type": "header_label"})
    rows.append({"label": "甲", "row_type": "data"})
    rows.append({"label": "乙" if not dup_label else "甲", "row_type": "data"})
    rows.append({"label": "合计", "row_type": "total", "is_total": True})
    return {
        "name": "变动表",
        "headers": ["项目", "期初余额", "本期增加", "本期减少", "期末余额"],
        "rows": rows,
    }


def _movement_binding(*, closing: dict[str, Any] | None = None) -> dict[str, Any]:
    def _row() -> dict[str, Any]:
        return {
            "row_type": "data",
            "binding": {
                SEM_OPENING: _manual_todo(),
                SEM_INCREASE: _manual_todo(),
                SEM_DECREASE: _manual_todo(),
                SEM_CLOSING: closing if closing is not None else _manual_todo(),
            },
        }

    return {
        "table_index": 0,
        "table_name": "变动表",
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            {"text": "期初余额", "semantic": SEM_OPENING},
            {"text": "本期增加", "semantic": SEM_INCREASE},
            {"text": "本期减少", "semantic": SEM_DECREASE},
            {"text": "期末余额", "semantic": SEM_CLOSING},
        ],
        "rows": {"甲": _row(), "乙": _row(), "合计": {"row_type": "total"}},
    }


# ---------------------------------------------------------------------------
# cell_coord / 语义工具
# ---------------------------------------------------------------------------


def test_cell_coord_is_one_based():
    assert cell_coord(0, 0) == "R1C1"
    assert cell_coord(3, 2) == "R4C3"


def test_cell_coord_rejects_negative():
    with pytest.raises(ValueError):
        cell_coord(-1, 0)


def test_split_semantic_handles_col_variants():
    assert split_semantic(SEM_CLOSING) == (SEM_CLOSING, "")
    assert split_semantic("closing_balance_col3") == (SEM_CLOSING, "_col3")


def test_value_col_semantics_drops_label_column():
    sems = value_col_semantics(_movement_binding())
    assert sems == [SEM_OPENING, SEM_INCREASE, SEM_DECREASE, SEM_CLOSING]


def test_value_col_semantics_robust_to_bad_input():
    assert value_col_semantics(None) == []
    assert value_col_semantics({}) == []
    assert value_col_semantics({"header_normalize": [{"text": "项目"}]}) == []


# ---------------------------------------------------------------------------
# Property 4 —— 合计求和范围对齐 _backfill_totals
# ---------------------------------------------------------------------------


def test_sum_range_matches_backfill_totals_semantics():
    """求和范围 = 上一合计行之后的所有非合计行（含 header_label 行）—— §V8。"""
    tpl = {
        "name": "分组表",
        "headers": ["项目", "期末余额"],
        "rows": [
            {"label": "分组一", "row_type": "header_label"},
            {"label": "甲", "row_type": "data"},
            {"label": "乙", "row_type": "data"},
            {"label": "小计一", "row_type": "subtotal", "is_total": True},
            {"label": "丙", "row_type": "data"},
            {"label": "合计", "row_type": "total", "is_total": True},
        ],
    }
    tb = {
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            {"text": "期末余额", "semantic": SEM_CLOSING},
        ],
        "rows": {},
    }
    specs, _skipped = derive_sum_formula(tpl, tb, section_number="八、99", variant="soe")
    by_target = {s.target_cell: s for s in specs}

    # 小计一（R4）= 分组一(R1) + 甲(R2) + 乙(R3)
    assert [c for c, _ in by_target["R4C1"].signed_cells] == ["R1C1", "R2C1", "R3C1"]
    # 合计（R6）= 上一合计行之后的 丙(R5) —— 不含 R1..R3
    assert [c for c, _ in by_target["R6C1"].signed_cells] == ["R5C1"]
    # 全部为加项
    assert all(sign == "+" for s in specs for _c, sign in s.signed_cells)


def test_sum_range_equals_backfill_totals_on_real_numbers():
    """派生范围按数值求和的结果 ≡ `_backfill_totals` 回填结果（Property 4）。"""
    tpl = {
        "name": "t",
        "headers": ["项目", "期末余额"],
        "rows": [
            {"label": "甲", "row_type": "data"},
            {"label": "乙", "row_type": "data"},
            {"label": "小计", "row_type": "subtotal", "is_total": True},
            {"label": "丙", "row_type": "data"},
            {"label": "合计", "row_type": "total", "is_total": True},
        ],
    }
    tb = {
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            {"text": "期末余额", "semantic": SEM_CLOSING},
        ],
        "rows": {},
    }
    values = [1.0, 2.0, None, 4.0, None]
    rows = [
        {
            "label": r["label"],
            "row_type": r["row_type"],
            "is_total": bool(r.get("is_total")),
            "values": [values[i]],
        }
        for i, r in enumerate(tpl["rows"])
    ]
    DisclosureEngine._backfill_totals(rows, 1)

    specs, _ = derive_sum_formula(tpl, tb)
    for spec in specs:
        derived = sum(
            rows[int(c[1:].split("C")[0]) - 1]["values"][0] or 0.0
            for c, _sign in spec.signed_cells
        )
        assert rows[spec.row_index]["values"][0] == pytest.approx(derived)


def test_sum_skips_non_summable_semantics():
    tpl = {
        "name": "t",
        "headers": ["项目", "计提比例", "期末余额"],
        "rows": [
            {"label": "甲", "row_type": "data"},
            {"label": "合计", "row_type": "total", "is_total": True},
        ],
    }
    tb = {
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            {"text": "计提比例", "semantic": "provision_ratio"},
            {"text": "期末余额", "semantic": SEM_CLOSING},
        ],
        "rows": {},
    }
    specs, skipped = derive_sum_formula(tpl, tb)
    assert [s.col_index for s in specs] == [1]
    assert any(s.reason == "non_summable_semantic" for s in skipped)
    assert all(not s.is_candidate for s in skipped)


def test_sum_first_row_total_and_empty_range_are_skipped():
    tpl = {
        "name": "t",
        "headers": ["项目", "期末余额"],
        "rows": [
            {"label": "合计", "row_type": "total", "is_total": True},
            {"label": "小计", "row_type": "subtotal", "is_total": True},
        ],
    }
    tb = {
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            {"text": "期末余额", "semantic": SEM_CLOSING},
        ],
        "rows": {},
    }
    specs, skipped = derive_sum_formula(tpl, tb)
    assert specs == []
    reasons = {s.reason for s in skipped}
    assert reasons == {"total_at_first_row", "empty_sum_range"}


# ---------------------------------------------------------------------------
# Property 3 —— 合计不写公式 binding（派生产出中合计只在 sum_specs，不在 movement）
# ---------------------------------------------------------------------------


def test_movement_never_targets_total_rows():
    tpl = _movement_template()
    specs, _skipped, _c = derive_movement_identity(tpl, _movement_binding())
    total_row_indexes = {
        i for i, r in enumerate(tpl["rows"]) if r.get("is_total")
    }
    assert specs, "四件套齐全应产出恒等式"
    assert all(s.row_index not in total_row_indexes for s in specs)
    assert all(s.derived_by == "movement_identity" for s in specs)


# ---------------------------------------------------------------------------
# Property 5 —— 四件套齐全才产出 / 分列按组
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("drop", sorted(MOVEMENT_QUAD))
def test_movement_requires_full_quad(drop: str):
    tb = _movement_binding()
    tb["header_normalize"] = [
        h for h in tb["header_normalize"] if h.get("semantic") != drop
    ]
    tpl = _movement_template()
    tpl["headers"] = [
        h for i, h in enumerate(tpl["headers"]) if i == 0 or i - 1 < len(tb["header_normalize"]) - 1
    ]
    specs, skipped, _c = derive_movement_identity(tpl, tb)
    assert specs == []
    assert any(s.reason == "movement_quad_incomplete" for s in skipped)


def test_movement_split_column_groups_do_not_mix():
    """两组分列语义各自成套 → 各产出一条，坐标不跨组混算。"""
    tpl = {
        "name": "双组表",
        "headers": [
            "项目",
            "期初余额", "本期增加", "本期减少", "期末余额",
            "期初余额2", "本期增加2", "本期减少2", "期末余额2",
        ],
        "rows": [{"label": "甲", "row_type": "data"}],
    }
    tb = {
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            {"text": "期初余额", "semantic": SEM_OPENING},
            {"text": "本期增加", "semantic": SEM_INCREASE},
            {"text": "本期减少", "semantic": SEM_DECREASE},
            {"text": "期末余额", "semantic": SEM_CLOSING},
            {"text": "期初余额2", "semantic": f"{SEM_OPENING}_col2"},
            {"text": "本期增加2", "semantic": f"{SEM_INCREASE}_col2"},
            {"text": "本期减少2", "semantic": f"{SEM_DECREASE}_col2"},
            {"text": "期末余额2", "semantic": f"{SEM_CLOSING}_col2"},
        ],
        "rows": {
            "甲": {
                "row_type": "data",
                "binding": {
                    SEM_OPENING: _manual_todo(),
                    SEM_INCREASE: _manual_todo(),
                    SEM_DECREASE: _manual_todo(),
                    SEM_CLOSING: _manual_todo(),
                    f"{SEM_OPENING}_col2": _manual_todo(),
                    f"{SEM_INCREASE}_col2": _manual_todo(),
                    f"{SEM_DECREASE}_col2": _manual_todo(),
                    f"{SEM_CLOSING}_col2": _manual_todo(),
                },
            }
        },
    }
    specs, _skipped, _c = derive_movement_identity(tpl, tb)
    assert len(specs) == 2
    targets = sorted(s.target_cell for s in specs)
    assert targets == ["R1C4", "R1C8"]
    for spec in specs:
        cols = {int(c.split("C")[1]) for c, _ in spec.signed_cells}
        # 组内列必须与目标列同组（1..4 或 5..8）
        if spec.target_cell == "R1C4":
            assert cols == {1, 2, 3}
        else:
            assert cols == {5, 6, 7}


def test_movement_partial_split_group_not_emitted():
    """第二组缺一列 → 只产出完整的第一组。"""
    tpl = {
        "name": "t",
        "headers": ["项目", "期初余额", "本期增加", "本期减少", "期末余额", "期末余额2"],
        "rows": [{"label": "甲", "row_type": "data"}],
    }
    tb = {
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            {"text": "期初余额", "semantic": SEM_OPENING},
            {"text": "本期增加", "semantic": SEM_INCREASE},
            {"text": "本期减少", "semantic": SEM_DECREASE},
            {"text": "期末余额", "semantic": SEM_CLOSING},
            {"text": "期末余额2", "semantic": f"{SEM_CLOSING}_col2"},
        ],
        "rows": {
            "甲": {
                "row_type": "data",
                "binding": {
                    SEM_OPENING: _manual_todo(),
                    SEM_INCREASE: _manual_todo(),
                    SEM_DECREASE: _manual_todo(),
                    SEM_CLOSING: _manual_todo(),
                    f"{SEM_CLOSING}_col2": _manual_todo(),
                },
            }
        },
    }
    specs, _skipped, _c = derive_movement_identity(tpl, tb)
    assert [s.target_cell for s in specs] == ["R1C4"]


# ---------------------------------------------------------------------------
# Property 2 / 6 —— 人工优先不覆盖 + 增减列不被绑定
# ---------------------------------------------------------------------------


def test_movement_does_not_overwrite_trial_balance_target():
    specs, skipped, _c = derive_movement_identity(
        _movement_template(), _movement_binding(closing=_tb_cell())
    )
    assert specs == []
    assert any(s.reason == "target_not_manual_todo" for s in skipped)


def test_movement_only_targets_closing_balance_column():
    """Property 6：产出目标格只有期末余额列，增减列不被绑定。"""
    specs, _skipped, _c = derive_movement_identity(
        _movement_template(), _movement_binding()
    )
    assert {s.semantic for s in specs} == {SEM_CLOSING}
    assert all(s.col_index == 3 for s in specs)


def test_movement_skips_duplicate_labels():
    """§V7：同表重复 label → 跳过（binding 按 label 精确匹配只命中第一个）。"""
    specs, skipped, _c = derive_movement_identity(
        _movement_template(dup_label=True), _movement_binding()
    )
    assert specs == []
    dups = [s for s in skipped if s.reason == "duplicate_label"]
    assert len(dups) == 2
    assert all(s.is_candidate for s in dups)


# ---------------------------------------------------------------------------
# Property 16 —— 覆盖率三分类无重复计数
# ---------------------------------------------------------------------------


def test_coverage_three_way_split_sums_to_candidates():
    res = derive_note_formulas(
        "八、99",
        {"tables": [_movement_template()]},
        {"tables": [_movement_binding()]},
        "soe",
    )
    assert res.candidate_cells == 8  # 2 data 行 × 4 语义列
    assert len(res.movement_specs) == 2
    assert res.skipped_candidate_count == 0
    assert res.remaining_manual_todo == 6
    assert (
        len(res.movement_specs)
        + res.skipped_candidate_count
        + res.remaining_manual_todo
        == res.candidate_cells
    )


def test_coverage_no_double_counting_between_formulated_and_skipped():
    res = derive_note_formulas(
        "八、99",
        {"tables": [_movement_template(dup_label=True)]},
        {"tables": [_movement_binding()]},
        "soe",
    )
    formulated = {(s.row_index, s.col_index) for s in res.movement_specs}
    skipped_cand = {
        (s.row_index, s.col_index) for s in res.skipped if s.is_candidate
    }
    assert formulated & skipped_cand == set()
    assert res.remaining_manual_todo >= 0


def test_derive_note_formulas_table_count_mismatch_skipped():
    res = derive_note_formulas(
        "八、99", {"tables": [_movement_template()]}, {"tables": []}, "soe"
    )
    assert res.sum_specs == [] and res.movement_specs == []
    assert [s.reason for s in res.skipped] == ["table_count_mismatch"]


def test_derive_note_formulas_missing_tables_skipped():
    res = derive_note_formulas("八、99", {}, {}, "soe")
    assert [s.reason for s in res.skipped] == ["tables_missing"]


# ---------------------------------------------------------------------------
# expression / cells payload
# ---------------------------------------------------------------------------


def test_movement_expression_and_payload():
    specs, _s, _c = derive_movement_identity(
        _movement_template(), _movement_binding()
    )
    spec = specs[0]
    assert spec.expression() == "ROW('R2C1') + ROW('R2C2') - ROW('R2C3')"
    assert spec.cells_payload() == [
        {"cell": "R2C1", "sign": "+"},
        {"cell": "R2C2", "sign": "+"},
        {"cell": "R2C3", "sign": "-"},
    ]


# ---------------------------------------------------------------------------
# Property 7 —— 坐标口径与运行时输出一一对应（含 §V4 反例锁定）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_derived_coordinates_hit_runtime_output_cells():
    """派生坐标经 `_cell_value_from_table` 反查命中 `_build_with_binding` 输出格。"""
    db = MagicMock()
    db.execute = AsyncMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._prior_notes_cache = {}

    tpl = _movement_template()
    tb = _movement_binding()
    out = await eng._build_with_binding(uuid4(), 2025, "八、99", tpl, tb)

    # 用可辨识数值填满输出，再按派生坐标反查
    for r, row in enumerate(out["rows"]):
        row["values"] = [float(r * 100 + c) for c in range(len(row["values"]))]

    specs, _s, _c = derive_movement_identity(tpl, tb)
    for spec in specs:
        got = _cell_value_from_table(out, {"cell": spec.target_cell})
        assert got == pytest.approx(
            float(spec.row_index * 100 + spec.col_index)
        )
        for cell, _sign in spec.signed_cells:
            r = int(cell[1:].split("C")[0]) - 1
            c = int(cell.split("C")[1]) - 1
            assert _cell_value_from_table(out, {"cell": cell}) == pytest.approx(
                float(r * 100 + c)
            )


@pytest.mark.asyncio
async def test_binding_rows_dict_order_would_be_wrong_coordinate_basis():
    """§V4 反例：用 bindings rows dict 序推坐标会错位（模板含 header_label 行）。"""
    db = MagicMock()
    db.execute = AsyncMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._prior_notes_cache = {}

    tpl = _movement_template(with_header_label=True)
    tb = _movement_binding()
    out = await eng._build_with_binding(uuid4(), 2025, "八、99", tpl, tb)

    binding_order = list(tb["rows"].keys())  # ['甲','乙','合计'] —— 无 header_label
    template_order = [r["label"] for r in tpl["rows"]]
    assert binding_order != template_order

    # 「甲」在模板序是 index 1（R2），在 bindings dict 序是 index 0（R1）
    specs, _s, _c = derive_movement_identity(tpl, tb)
    jia = next(s for s in specs if s.row_label == "甲")
    assert jia.target_cell.startswith("R2")
    assert out["rows"][1]["label"] == "甲"
    assert out["rows"][0]["label"] == "分类"


# ---------------------------------------------------------------------------
# PBT
# ---------------------------------------------------------------------------

_row_types = st.sampled_from(["data", "header_label", "total", "subtotal"])
_sem_pool = sorted(MOVEMENT_QUAD | NON_SUMMABLE_SEMANTICS | {"prior_year_value"})


@hyp_settings(max_examples=5, deadline=None)
@given(
    row_types=st.lists(_row_types, min_size=1, max_size=6),
    sems=st.lists(st.sampled_from(_sem_pool), min_size=1, max_size=5),
)
def test_pbt_derivation_invariants(row_types: list[str], sems: list[str]):
    """PBT：无论表结构如何 —— 合计不被 movement 绑定、只绑期末列、三分类不越界。"""
    rows = [
        {
            "label": f"行{i}",
            "row_type": rt,
            **({"is_total": True} if rt in ("total", "subtotal") else {}),
        }
        for i, rt in enumerate(row_types)
    ]
    tpl = {"name": "t", "headers": ["项目", *[f"h{i}" for i in range(len(sems))]], "rows": rows}
    tb = {
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            *[{"text": f"h{i}", "semantic": s} for i, s in enumerate(sems)],
        ],
        "rows": {
            r["label"]: {
                "row_type": r["row_type"],
                "binding": {s: _manual_todo() for s in sems},
            }
            for r in rows
        },
    }

    res = derive_note_formulas("八、PBT", {"tables": [tpl]}, {"tables": [tb]}, "soe")

    total_idx = {i for i, r in enumerate(rows) if r.get("is_total")}
    # Property 3：movement 绝不指向合计行
    assert all(s.row_index not in total_idx for s in res.movement_specs)
    # Property 6：只绑期末余额语义
    assert all(
        split_semantic(s.semantic or "")[0] == SEM_CLOSING for s in res.movement_specs
    )
    # 坐标合法：1-based 且在范围内
    n_cols = len(tpl["headers"]) - 1
    for s in res.movement_specs + res.sum_specs:
        assert 1 <= s.row_index + 1 <= len(rows)
        assert 1 <= s.col_index + 1 <= n_cols
        for cell, sign in s.signed_cells:
            assert sign in ("+", "-")
            r = int(cell[1:].split("C")[0])
            c = int(cell.split("C")[1])
            assert 1 <= r <= len(rows) and 1 <= c <= n_cols
    # Property 16：三分类不越界、不重复
    assert res.remaining_manual_todo >= 0
    formulated = {(s.row_index, s.col_index) for s in res.movement_specs}
    skipped_cand = {(s.row_index, s.col_index) for s in res.skipped if s.is_candidate}
    assert formulated & skipped_cand == set()
    assert len(formulated) + len(skipped_cand) <= res.candidate_cells
    # 每个跳过项都有 reason
    assert all(s.reason for s in res.skipped)


@hyp_settings(max_examples=5, deadline=None)
@given(sems=st.lists(st.sampled_from(_sem_pool), min_size=1, max_size=5))
def test_pbt_sum_specs_never_include_total_rows_as_members(sems: list[str]):
    """PBT：合计求和项中不含任何合计行坐标（与 `_backfill_totals` 一致）。"""
    rows = [
        {"label": "甲", "row_type": "data"},
        {"label": "小计", "row_type": "subtotal", "is_total": True},
        {"label": "乙", "row_type": "data"},
        {"label": "合计", "row_type": "total", "is_total": True},
    ]
    tpl = {"name": "t", "headers": ["项目", *[f"h{i}" for i in range(len(sems))]], "rows": rows}
    tb = {
        "header_normalize": [
            {"text": "项目", "semantic": "manual_text"},
            *[{"text": f"h{i}", "semantic": s} for i, s in enumerate(sems)],
        ],
        "rows": {},
    }
    specs, _skipped = derive_sum_formula(tpl, tb)
    total_rows_1based = {2, 4}
    for s in specs:
        member_rows = {int(c[1:].split("C")[0]) for c, _ in s.signed_cells}
        assert member_rows & total_rows_1based == set()


@hyp_settings(max_examples=5, deadline=None)
@given(
    row_count=st.integers(min_value=1, max_value=6),
    col_count=st.integers(min_value=1, max_value=6),
)
def test_pbt_cell_coord_roundtrip(row_count: int, col_count: int):
    """PBT：cell_coord 与 `_cell_value_from_table` 坐标解析互为逆。"""
    table = {
        "rows": [
            {"label": f"r{r}", "values": [float(r * 10 + c) for c in range(col_count)]}
            for r in range(row_count)
        ]
    }
    for r in range(row_count):
        for c in range(col_count):
            coord = cell_coord(r, c)
            assert _cell_value_from_table(table, {"cell": coord}) == pytest.approx(
                float(r * 10 + c)
            )


def test_count_candidate_cells_independent_of_specs():
    tb = _movement_binding(closing=_tb_cell())
    assert count_candidate_cells(_movement_template(), tb) == 6  # 期末列已被 TB 绑定
    assert count_candidate_cells(_movement_template(), _movement_binding()) == 8
