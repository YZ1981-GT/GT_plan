"""F1 四表库取数守卫（纯函数 + render fail-open characterization）。

spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/
      Requirements 1.4~1.6, 2.2, 2.5, 3.1~3.3, 3.7 / Properties 1, 2, 3, 4

实证基线（DB 只读，2026-07-31）：

- 项目 ``0ec33ac9``/2025：``1123`` 期末 13,576,792.21 = 叶子 ``1123.01`` 13,576,792.21；
  ``1123.03`` 期初 302,400.23。
- 项目 ``2aa00f57``/2025：``1123`` 期末 1,301,918.43 = ``1123.01`` 2,430.64 +
  ``1123.03`` 1,299,487.79；存货净额 = ``1406.02`` 121,090,440.11 +
  ``1416.04`` −3,281,478.91 = 117,808,961.20。
- ``1231`` 下挂 ``.01 应收票据`` / ``.02 应收账款`` / ``.03 其他应收款``（**无** ``.04 预付``）
  → 备抵侧宽前缀必须叠「预付」名称过滤，否则会把 26,401,719.77 的应收账款坏账算进 F1。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._f1_prepayment import (
    F1_NATURE_ROW_KEYS,
    F1_REPORT_LINE_SPEC,
    build_impairment_prefill,
    build_nature_prefill,
    classify_f1_nature,
    filter_by_code_specs,
    render as f1_render,
    sql_prefixes_for_specs,
)
from app.services.four_table import LeafRow, select_leaves

# ═══════════════════════════════════════════════════════════════════════════════
# Property 2 — 性质归类不丢科目
# ═══════════════════════════════════════════════════════════════════════════════

#: 实证真实科目名 → 期望性质桶（`tb_balance.account_name`，项目 0ec33ac9 / 2aa00f57）
_REAL_NAMES = [
    ("预付账款_预付货款", "goods"),
    ("预付账款_长期资产款_一次购置", "equipment"),
    ("预付账款_长期资产款_分期购置", "equipment"),
    # 🔴 同时含「长期资产」与「工程」→ 工程必须优先（源模板口径归工程款）
    ("预付账款_长期资产款_工程款", "construction"),
    ("预付账款_短期待摊费用", "service"),
    ("预付账款_其他", "other"),
]


@pytest.mark.parametrize("name,expected", _REAL_NAMES)
def test_classify_real_account_names(name: str, expected: str) -> None:
    assert classify_f1_nature(name) == expected


def test_classify_construction_beats_equipment() -> None:
    """反向自检：若把工程规则挪到设备之后，上面那条断言就会失效。"""
    assert classify_f1_nature("长期资产款_工程款") == "construction"
    assert classify_f1_nature("长期资产款_一次购置") == "equipment"


@pytest.mark.parametrize("name", ["", None, "  ", "预付账款", "未知往来"])
def test_classify_unknown_falls_back_to_other(name) -> None:
    assert classify_f1_nature(name) == "other"


def test_classify_returns_only_known_row_keys() -> None:
    for name, _ in _REAL_NAMES:
        assert classify_f1_nature(name) in F1_NATURE_ROW_KEYS


def _leaf(code: str, name: str, opening: float, closing: float) -> LeafRow:
    return LeafRow(
        account_code=code,
        account_name=name,
        opening=opening,
        closing=closing,
        dataset_id="ds-1",
    )


def test_nature_prefill_matches_real_project_2aa00f57() -> None:
    leaves = [
        _leaf("1123.01", "预付账款_预付货款", 33666.58, 2430.64),
        _leaf("1123.03", "预付账款_短期待摊费用", 1297540.83, 1299487.79),
    ]
    out = build_nature_prefill(leaves, ["1123"])
    assert out == {
        "goods": {"opening": 33666.58, "closing": 2430.64},
        "service": {"opening": 1297540.83, "closing": 1299487.79},
    }
    # 五桶合计 == 父科目 1123 期末（Property 1 的业务侧体现）
    assert round(sum(v["closing"] for v in out.values()), 2) == 1301918.43


@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    st.lists(
        st.tuples(
            st.sampled_from([n for n, _ in _REAL_NAMES]),
            st.floats(min_value=-1e7, max_value=1e7, allow_nan=False, allow_infinity=False),
            st.floats(min_value=-1e7, max_value=1e7, allow_nan=False, allow_infinity=False),
        ),
        min_size=0,
        max_size=8,
    )
)
def test_nature_prefill_conserves_total(rows) -> None:
    """Property 2：五桶 opening/closing 之和 == 入参叶子之和（不丢科目）。"""
    leaves = [
        _leaf(f"1123.{i:02d}", name, op, cl) for i, (name, op, cl) in enumerate(rows, start=1)
    ]
    out = build_nature_prefill(leaves, ["1123"])
    assert set(out) <= set(F1_NATURE_ROW_KEYS)
    for field, idx in (("opening", 1), ("closing", 2)):
        want = round(sum(r[idx] for r in rows), 2)
        got = round(sum(v[field] for v in out.values()), 2)
        assert abs(got - want) < 0.05, (field, got, want)


def test_nature_prefill_empty_returns_empty_dict() -> None:
    assert build_nature_prefill([], ["1123"]) == {}
    # 有叶子但不在前缀内 → 同样为空（不误纳）
    assert build_nature_prefill([_leaf("1221.01", "其他应收款_个人往来", 1, 2)], ["1123"]) == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1 / 2.2 — 严格点号边界
# ═══════════════════════════════════════════════════════════════════════════════


def test_leaf_selection_respects_dot_boundary() -> None:
    """`1123.1` 与 `1123.10` 是**兄弟**科目，两者都是叶子。

    旧实现 `_is_leaf` 用 `other.startswith(code)` 会把 `1123.1` 误判为非叶子 → 整支丢失。
    """
    rows = [
        _leaf("1123", "预付账款", 0, 300),
        _leaf("1123.1", "预付账款_甲", 0, 100),
        _leaf("1123.10", "预付账款_乙", 0, 200),
    ]
    leaves = select_leaves(rows)
    codes = sorted(r.account_code for r in leaves)
    assert codes == ["1123.1", "1123.10"]
    out = build_nature_prefill(leaves, ["1123"])
    assert round(sum(v["closing"] for v in out.values()), 2) == 300.0


def test_prefix_filter_does_not_eat_sibling_code() -> None:
    """前缀 `2202` 不得吃掉 `22020`（不同科目）。"""
    rows = [
        _leaf("2202", "应付账款", 0, -100),
        _leaf("22020", "另一个科目", 0, -999),
    ]
    picked = filter_by_code_specs(select_leaves(rows), ["2202"])
    assert [r.account_code for r in picked] == ["2202"]


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3 — 备抵侧宽前缀必叠名称过滤
# ═══════════════════════════════════════════════════════════════════════════════


_PROVISION_LEAVES = [
    _leaf("1231.01", "坏账准备_应收票据", 0, -1162288.03),
    _leaf("1231.02", "坏账准备_应收账款", 0, -26401719.77),
    _leaf("1231.03", "坏账准备_其他应收款", 0, -900217.36),
]


def test_impairment_prefill_name_filter_excludes_other_receivables() -> None:
    """宽前缀 `1231` + 「预付」过滤 → 无命中（实证数据集无 1231.04）。"""
    out = build_impairment_prefill(_PROVISION_LEAVES, ["1231"], name_filter="预付")
    assert out is None


def test_impairment_prefill_picks_only_prepaid_provision() -> None:
    leaves = _PROVISION_LEAVES + [
        _leaf("1231.04", "坏账准备_预付账款", -1000.0, -2500.0),
    ]
    out = build_impairment_prefill(leaves, ["1231"], name_filter="预付")
    assert out == {"end": 2500.0, "prior": 1000.0}
    # 反向自检：不叠过滤时必然把应收账款坏账算进来（证明过滤确实生效）
    unfiltered = build_impairment_prefill(leaves, ["1231"], name_filter=None)
    assert unfiltered is not None
    assert unfiltered["end"] > 26_000_000


def test_impairment_prefill_takes_absolute_value() -> None:
    """`tb_balance` 两种符号约定并存（实证同科目在不同项目正负相反）→ 结果取绝对值。"""
    positive = build_impairment_prefill(
        [_leaf("1231.04", "坏账准备_预付账款", 1000.0, 2500.0)], ["1231"], name_filter="预付"
    )
    negative = build_impairment_prefill(
        [_leaf("1231.04", "坏账准备_预付账款", -1000.0, -2500.0)], ["1231"], name_filter="预付"
    )
    assert positive == negative == {"end": 2500.0, "prior": 1000.0}


def test_report_line_spec_declares_prepaid_name_filter() -> None:
    assert F1_REPORT_LINE_SPEC.row_code == "BS-008"
    assert F1_REPORT_LINE_SPEC.fallback_gross == ("1123",)
    assert F1_REPORT_LINE_SPEC.fallback_provision == ("1231-04",)
    assert F1_REPORT_LINE_SPEC.provision_name_filter == "预付"


# ═══════════════════════════════════════════════════════════════════════════════
# 2.5 — 跨循环锚点区间解析（存货 BS-010 = SUM_TB('1401~1499')）
# ═══════════════════════════════════════════════════════════════════════════════


def test_sql_prefixes_for_specs() -> None:
    assert sql_prefixes_for_specs(["1401~1499"]) == ["14"]
    assert sql_prefixes_for_specs(["2202"]) == ["2202"]
    assert sql_prefixes_for_specs(["1401~1499", "1416"]) == ["14", "1416"]
    # 两端无公共前导 → 退化为两端各自（仍属宽取，由 filter_by_code_specs 收敛）
    assert sql_prefixes_for_specs(["1401~2202"]) == ["1401", "2202"]
    assert sql_prefixes_for_specs([None, "", "  "]) == []


def test_filter_by_code_specs_range_matches_real_inventory() -> None:
    """实证 2aa00f57 存货：1406.02 121,090,440.11 + 1416.04 −3,281,478.91。"""
    rows = [
        _leaf("1406", "库存商品", 155942513.42, 121090440.11),
        _leaf("1406.02", "库存商品_外购商品", 155942513.42, 121090440.11),
        _leaf("1416", "存货跌价准备", -57777.90, -3281478.91),
        _leaf("1416.04", "存货跌价准备_库存商品", -57777.90, -3281478.91),
        _leaf("1452", "低值易耗品", 0.0, 0.0),
        # 区间外：不得纳入
        _leaf("1501", "债权投资", 0.0, 999999.0),
    ]
    leaves = select_leaves(rows)
    picked = filter_by_code_specs(leaves, ["1401~1499"])
    assert sorted(r.account_code for r in picked) == ["1406.02", "1416.04", "1452"]
    assert round(sum(r.closing for r in picked), 2) == 117808961.20


def test_filter_by_code_specs_dedupes_overlapping_specs() -> None:
    rows = [_leaf("1416.04", "存货跌价准备_库存商品", 0.0, -100.0)]
    picked = filter_by_code_specs(rows, ["1401~1499", "1416"])
    assert len(picked) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Property 4 — render fail-open characterization
# ═══════════════════════════════════════════════════════════════════════════════


class _EmptyRenderContext:
    """所有 DB 查询都返回空 —— 模拟四表未入库 / 依赖缺失。"""

    def __init__(self) -> None:
        self.project_id = "00000000-0000-0000-0000-000000000001"
        self.wp_id = "00000000-0000-0000-0000-0000000000f1"
        self.year = 2025
        result = MagicMock()
        result.fetchall.return_value = []
        result.fetchone.return_value = None
        self.db = AsyncMock()
        self.db.execute = AsyncMock(return_value=result)


@pytest.mark.asyncio
async def test_render_fail_open_when_all_dependencies_empty() -> None:
    res = await f1_render(_EmptyRenderContext())
    assert res is not None
    pc = res["project_context"]
    # 既有字段与改动前逐值等价（零回归）
    assert pc["prepaid_tb_amount"] == 0.0
    assert pc["inventory_balance_current"] == 0
    assert pc["payable_balance_current"] == 0
    assert pc["prepaid_tb_leaf_amount"] == 0
    # 宁缺勿造：无数据时不出现预填键
    assert "adjudication_prefill" not in res
    assert "impairment_prefill" not in res


@pytest.mark.asyncio
async def test_render_tb_source_codes_shape() -> None:
    """溯源输出必须是结构化 dict（旧版是 list[str] 且前端 0 消费）。"""
    res = await f1_render(_EmptyRenderContext())
    src = res["project_context"]["tb_source_codes"]
    assert isinstance(src, dict)
    for key in (
        "row_code",
        "formula",
        "gross",
        "gross_standard",
        "provision",
        "provision_standard",
        "resolved_from",
        "provision_resolved_from",
        "provision_exact",
        "use_provision_name_filter",
    ):
        assert key in src, key
    assert src["row_code"] == "BS-008"
    # 依赖缺失 → 兜底科目
    assert src["gross"] == ["1123"]
    assert src["provision_standard"] == ["1231-04"]
    assert src["resolved_from"] == "fallback"
    assert src["use_provision_name_filter"] is True

    cross = res["project_context"]["tb_cross_cycle_codes"]
    assert cross["inventory"]["row_code"] == "BS-010"
    assert cross["inventory"]["codes"] == ["1401~1499"]
    assert cross["payable"]["row_code"] == "BS-045"
    assert cross["payable"]["codes"] == ["2202"]


@pytest.mark.asyncio
async def test_render_keeps_existing_contract() -> None:
    res = await f1_render(_EmptyRenderContext())
    assert res["account_code"] == "1123"
    assert [s["code"] for s in res["sections"]][:3] == ["F1A", "F1-1", "F1-2"]
    assert set(res["disclosure_visibility"]) == {"listed", "soe"}
    assert [r["rowKey"] for r in res["adjudication_config"]["nature_rows"]] == list(
        F1_NATURE_ROW_KEYS
    )
