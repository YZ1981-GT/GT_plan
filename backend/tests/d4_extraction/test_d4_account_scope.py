"""D4 account_scope 守卫（PBT + 反向自检）。

测试内容：
- pair_revenue_cost_leaves（后缀优先 + 名称非否决 + 配对覆盖全输入叶子）
- code_in_specs（区间展开 + 单码前缀）
- split_leaf_head_suffix（点号边界）
- strip_segment_name_prefix（各种前缀剥离）
- converge_to_d4_semantics（语义收敛剔除非 D4 码）

**Validates: Requirements 9.2, 9.3, 9.4**
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.d4_extraction.account_scope import (
    D4_ROOT_PAIRS,
    code_in_specs,
    converge_to_d4_semantics,
    pair_revenue_cost_leaves,
    split_leaf_head_suffix,
    strip_segment_name_prefix,
)
from app.services.four_table.leaf_aggregation import LeafRow


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _leaf(code: str, name: str = "", credit: float = 0.0, debit: float = 0.0) -> LeafRow:
    return LeafRow(account_code=code, account_name=name, credit=credit, debit=debit)


# ─────────────────────────────────────────────────────────────────────────────
# split_leaf_head_suffix
# ─────────────────────────────────────────────────────────────────────────────


class TestSplitLeafHeadSuffix:
    """点号边界：根码 + '.' 开头才算命中。"""

    def test_exact_match_root(self):
        assert split_leaf_head_suffix("6001", ["6001", "6401"]) == ("6001", "")

    def test_dot_boundary(self):
        assert split_leaf_head_suffix("6001.11", ["6001"]) == ("6001", "11")

    def test_no_dot_no_match(self):
        """'60010' 不应命中根 '6001'（无点号边界）。"""
        assert split_leaf_head_suffix("60010", ["6001"]) is None

    def test_longest_match(self):
        """多个根时取最长。"""
        assert split_leaf_head_suffix("6001.11.02", ["6001", "6001.11"]) == ("6001.11", "02")

    def test_empty_input(self):
        assert split_leaf_head_suffix("", ["6001"]) is None
        assert split_leaf_head_suffix("6001", []) is None
        assert split_leaf_head_suffix("6001", None) is None


# ─────────────────────────────────────────────────────────────────────────────
# strip_segment_name_prefix
# ─────────────────────────────────────────────────────────────────────────────


class TestStripSegmentNamePrefix:
    """剥掉科目名前缀得到分部名。"""

    def test_revenue_prefix(self):
        assert strip_segment_name_prefix("营业收入_批发") == "批发"

    def test_cost_prefix(self):
        assert strip_segment_name_prefix("营业成本_医疗支出") == "医疗支出"

    def test_main_business_revenue(self):
        assert strip_segment_name_prefix("主营业务收入_零售") == "零售"

    def test_no_prefix(self):
        assert strip_segment_name_prefix("批发") == "批发"

    def test_empty(self):
        assert strip_segment_name_prefix("") == ""
        assert strip_segment_name_prefix(None) == ""

    def test_separator_variants(self):
        """各种分隔符。"""
        assert strip_segment_name_prefix("收入-批发") == "批发"
        assert strip_segment_name_prefix("成本：物流") == "物流"


# ─────────────────────────────────────────────────────────────────────────────
# code_in_specs（区间展开）
# ─────────────────────────────────────────────────────────────────────────────


class TestCodeInSpecs:
    """标准码落在科目规格集内（单码前缀 or 区间）。"""

    def test_interval_covers_middle(self):
        """6050 在 '6001~6099' 区间内。"""
        assert code_in_specs("6050", ("6001~6099",)) is True

    def test_interval_covers_boundary(self):
        assert code_in_specs("6001", ("6001~6099",)) is True
        assert code_in_specs("6099", ("6001~6099",)) is True

    def test_interval_excludes_outside(self):
        assert code_in_specs("6100", ("6001~6099",)) is False
        assert code_in_specs("5999", ("6001~6099",)) is False

    def test_single_code_exact(self):
        assert code_in_specs("6001", ("6001",)) is True

    def test_single_code_prefix(self):
        assert code_in_specs("6001.11", ("6001",)) is True

    def test_single_code_no_dot_mismatch(self):
        """'60012' 不应命中 '6001'。"""
        assert code_in_specs("60012", ("6001",)) is False

    def test_subcode_in_interval(self):
        """子科目 6001.11 的一级段 6001 在 '6001~6099' 内。"""
        assert code_in_specs("6001.11", ("6001~6099",)) is True

    def test_empty(self):
        assert code_in_specs("", ("6001~6099",)) is False
        assert code_in_specs("6001", ()) is False


# ─────────────────────────────────────────────────────────────────────────────
# converge_to_d4_semantics
# ─────────────────────────────────────────────────────────────────────────────


class TestConvergeToD4Semantics:
    """按科目名语义收敛：剔除非 D4 根科目的标准码。"""

    def test_keeps_declared_root(self):
        """6001 在 D4_ROOT_PAIRS 声明列表中，直接保留。"""
        kept, dropped = converge_to_d4_semantics(
            [("6001", "主营业务收入"), ("6403", "税金及附加")],
            want="revenue",
        )
        assert "6001" in kept
        assert ("6403", "税金及附加") in dropped

    def test_keeps_by_name_hint(self):
        """名称含「营业收入」关键字也保留（变体根科目如 6002）。"""
        kept, _ = converge_to_d4_semantics(
            [("6002", "主营业务收入-工程")],
            want="revenue",
        )
        assert "6002" in kept

    def test_drops_tax(self):
        """6403 税金及附加不含「成本」→ 剔除。"""
        kept, dropped = converge_to_d4_semantics(
            [("6401", "主营业务成本"), ("6403", "税金及附加")],
            want="cost",
        )
        assert "6401" in kept
        assert ("6403", "税金及附加") in dropped

    def test_invalid_want_raises(self):
        with pytest.raises(ValueError):
            converge_to_d4_semantics([], want="invalid")


# ─────────────────────────────────────────────────────────────────────────────
# pair_revenue_cost_leaves — PBT
# ─────────────────────────────────────────────────────────────────────────────

# Strategy: generate revenue and cost leaves with random suffixes
_suffix_st = st.text(
    alphabet=st.sampled_from("0123456789."),
    min_size=1,
    max_size=5,
).filter(lambda s: not s.startswith(".") and not s.endswith(".") and ".." not in s)


@st.composite
def _leaf_lists(draw):
    """Generate revenue and cost leaf lists for pair_revenue_cost_leaves."""
    n_rev = draw(st.integers(min_value=0, max_value=5))
    n_cost = draw(st.integers(min_value=0, max_value=5))
    rev_leaves = []
    cost_leaves = []
    for _ in range(n_rev):
        sfx = draw(_suffix_st)
        rev_leaves.append(_leaf(f"6001.{sfx}", f"营业收入_{sfx}", credit=100.0))
    for _ in range(n_cost):
        sfx = draw(_suffix_st)
        cost_leaves.append(_leaf(f"6401.{sfx}", f"营业成本_{sfx}", debit=80.0))
    return rev_leaves, cost_leaves


class TestPairRevenueProperty:
    """PBT：pair_revenue_cost_leaves 的配对不变量。

    **Validates: Requirements 9.2**
    """

    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    @given(data=_leaf_lists())
    def test_every_leaf_appears_exactly_once(self, data):
        """Property 7：每个输入叶子恰好出现在一个 SegmentPair 中。"""
        rev_leaves, cost_leaves = data
        pairs = pair_revenue_cost_leaves(rev_leaves, cost_leaves)

        # Collect all revenue/cost codes from output
        out_rev_codes = [p.revenue_code for p in pairs if p.revenue_code is not None]
        out_cost_codes = [p.cost_code for p in pairs if p.cost_code is not None]

        in_rev_codes = [r.account_code for r in rev_leaves]
        in_cost_codes = [c.account_code for c in cost_leaves]

        # Each input revenue leaf appears at most once in output
        assert len(out_rev_codes) == len(set(out_rev_codes)), "Revenue leaf duplicated"
        # Each input cost leaf appears at most once in output
        assert len(out_cost_codes) == len(set(out_cost_codes)), "Cost leaf duplicated"

        # Output covers all input leaves (as set — duplicates in input share a slot)
        assert set(out_rev_codes) == set(in_rev_codes)
        assert set(out_cost_codes) == set(in_cost_codes)

    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    @given(data=_leaf_lists())
    def test_paired_revenue_cost_no_overlap(self, data):
        """配对后收入侧与成本侧无交叉。"""
        rev_leaves, cost_leaves = data
        pairs = pair_revenue_cost_leaves(rev_leaves, cost_leaves)

        out_rev_codes = {p.revenue_code for p in pairs if p.revenue_code}
        out_cost_codes = {p.cost_code for p in pairs if p.cost_code}
        # Revenue codes and cost codes never overlap
        assert out_rev_codes.isdisjoint(out_cost_codes)


# ─────────────────────────────────────────────────────────────────────────────
# pair_revenue_cost_leaves — 反向自检
# ─────────────────────────────────────────────────────────────────────────────


class TestPairRevenueReverseCheck:
    """反向自检：打乱配对优先级须失败。"""

    def test_scrambled_priority_fails(self):
        """如果我们把根配对表的顺序打乱（成本根用收入根的码），
        则 6001.11 不再与 6401.11 配对成功。
        """
        rev = [_leaf("6001.11", "营业收入_批发", credit=100.0)]
        cost = [_leaf("6401.11", "营业成本_批发", debit=80.0)]

        # 正确配对
        correct = pair_revenue_cost_leaves(rev, cost)
        assert any(
            p.revenue_code == "6001.11" and p.cost_code == "6401.11" for p in correct
        ), "Correct pairing should succeed"

        # 打乱：把根配对表的收入根和成本根互换（使 6001.11 在成本侧查找）
        bad_root_pairs = (("6401", "6001", "主营业务"),)
        broken = pair_revenue_cost_leaves(rev, cost, root_pairs=bad_root_pairs)
        # 在打乱的根配对下，6001.11 不被识别为成本根 6001 下的叶子
        # 且 6401.11 不被识别为收入根 6401 下的叶子
        # 因此它们应该各自落入 orphan 而非配对
        paired = [
            p
            for p in broken
            if p.revenue_code == "6001.11" and p.cost_code == "6401.11"
        ]
        assert len(paired) == 0, (
            "Scrambled root pairs should NOT produce correct pairing"
        )

    def test_name_mismatch_does_not_break_pairing(self):
        """Property 8：名称不等不解除配对（如 医疗收入/医疗支出）。"""
        rev = [_leaf("6001.16", "营业收入_医疗收入", credit=500.0)]
        cost = [_leaf("6401.16", "营业成本_医疗支出", debit=400.0)]

        pairs = pair_revenue_cost_leaves(rev, cost)
        matched = [
            p for p in pairs if p.revenue_code == "6001.16" and p.cost_code == "6401.16"
        ]
        assert len(matched) == 1
        assert matched[0].name_mismatch is True

    def test_cost_missing_when_no_mirror(self):
        """镜像有缺口时成本列留空。"""
        rev = [_leaf("6001.15", "营业收入_物业与租赁", credit=3614997.94)]
        cost: list[LeafRow] = []

        pairs = pair_revenue_cost_leaves(rev, cost)
        assert len(pairs) == 1
        assert pairs[0].revenue_code == "6001.15"
        assert pairs[0].cost_code is None
        assert pairs[0].cost_missing is True
