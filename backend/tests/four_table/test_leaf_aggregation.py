"""四表库叶子聚合单测（Property 1）。

fixture 取**真实实测值**（项目 `0ec33ac9`/2025 的 `1221 其他应收款` 科目树），
因为本模块修的正是「只取最深层级」导致 `1221.11` / `1221.12` 整段丢失的缺陷 ——
用真数据才能钉住回归。

spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
      Requirements 2.1~2.4 / Property 1
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.four_table.leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    parent_totals,
    select_leaves,
    to_leaf_rows,
)

# ── 实测 fixture：项目 0ec33ac9 / 2025 / dataset c050bfbe 的 1221 树 ────────────
# 父科目 1221 期末 = 269,885,933.03；叶子和须逐分相等（Property 1）。
_P_1221_CLOSING = 269885933.03
_P_1221_OPENING = 150302795.09
_LEAF_1221_11 = 3597359.45      # 个人往来（一级叶子 —— 旧「最深层级」实现整段丢掉）
_LEAF_1221_12 = 55035942.52     # 保证金及押金（同上，K1 性质分布最核心的桶）


def _real_1221_tree() -> list[LeafRow]:
    def r(code, name, opening, closing, direction="debit"):
        return LeafRow(
            account_code=code,
            account_name=name,
            opening=opening,
            closing=closing,
            direction=direction,
            dataset_id="c050bfbe",
        )

    return [
        r("1221", "其他应收款", _P_1221_OPENING, _P_1221_CLOSING),
        # 一级叶子（无子科目）
        r("1221.11", "其他应收款_个人往来", 1022267.86, _LEAF_1221_11),
        r("1221.12", "其他应收款_保证金及押金", 52568902.81, _LEAF_1221_12),
        # 1221.13 有子科目 → 非叶子
        r("1221.13", "其他应收款_代收代付款项", 93264.30, 93264.30),
        r("1221.13.01", "其他应收款_代收代付款项_代垫职工款项", 93264.30, 93264.30),
        r("1221.13.02", "其他应收款_代收代付款项_代垫货款", 0.0, 0.0),
        # 1221.15 有子科目 → 非叶子
        r("1221.15", "其他应收款_资金往来", 87626505.29, 207815404.88),
        r("1221.15.02", "其他应收款_资金往来_短期借款", 48200000.00, 84800000.00),
        r("1221.15.04", "其他应收款_资金往来_应收利息", 30444.33, 37808.48),
        r("1221.15.06", "其他应收款_资金往来_应收上存", 1317639.94, 86373080.62),
        r("1221.15.08", "其他应收款_资金往来_应收利润", 38078421.02, 36604515.78),
        # 1221.98 有子科目 → 非叶子
        r("1221.98", "其他应收款_其他", 8991854.83, 3343961.88),
        r("1221.98.03", "其他应收款_其他_经营类往来款", 218269.57, 379612.31),
        r("1221.98.08", "其他应收款_其他_仓储配送费", 58240.00, -10500.00, "credit"),
        r("1221.98.91", "其他应收款_其他_保理追加收购款", 7027572.00, 2802009.32),
        r("1221.98.99", "其他应收款_其他_其他", 1687773.26, 172840.25),
    ]


def _real_1231_tree() -> list[LeafRow]:
    """坏账准备树：K1 只该取 1231.03，旧实现把 1231.02（应收账款）也算进去。"""

    def r(code, name, opening, closing):
        return LeafRow(
            account_code=code,
            account_name=name,
            opening=opening,
            closing=closing,
            direction="credit",
            dataset_id="c050bfbe",
        )

    return [
        r("1231", "坏账准备", 15728468.72, 28464225.16),
        r("1231.01", "坏账准备_应收票据", 3037132.25, 1162288.03),
        r("1231.02", "坏账准备_应收账款", 12052106.46, 26401719.77),
        r("1231.03", "坏账准备_其他应收款", 639230.01, 900217.36),
        r("1231.05", "坏账准备_长期应收款", 0.0, 0.0),
    ]


# ── Property 1：叶子互不为前缀 + 叶子和 == 父额 ──────────────────────────────


def test_leaves_are_pairwise_non_prefix():
    leaves = select_leaves(_real_1221_tree())
    codes = [r.account_code for r in leaves]
    for a in codes:
        for b in codes:
            if a == b:
                continue
            assert not b.startswith(a + "."), f"{a} 是 {b} 的前缀，二者不该同时是叶子"


def test_leaf_sum_equals_parent_total():
    """Property 1 核心勾稽：1221 叶子期末之和 == 父科目 1221 期末余额。"""
    rows = _real_1221_tree()
    leaves = select_leaves(rows)
    # 父科目行本身也是「1221」，被 select_leaves 判为非叶子（有 1221.11 等子科目）
    assert all(r.account_code != "1221" for r in leaves)
    agg = aggregate_leaves(leaves, ["1221"])
    parent = parent_totals(rows, "1221")
    assert round(agg["closing"], 2) == round(parent["closing"], 2) == _P_1221_CLOSING
    assert round(agg["opening"], 2) == round(parent["opening"], 2) == _P_1221_OPENING


def test_first_level_leaves_not_dropped():
    """回归钉子：旧 `_aggregate_prefix_deepest` 只取 depth==2，丢掉 1221.11 / 1221.12。"""
    leaves = select_leaves(_real_1221_tree())
    codes = {r.account_code for r in leaves}
    assert "1221.11" in codes
    assert "1221.12" in codes

    agg = aggregate_leaves(leaves, ["1221"])
    deepest_only = sum(
        r.closing for r in leaves if r.account_code.count(".") == 2
    )
    assert round(agg["closing"] - deepest_only, 2) == round(
        _LEAF_1221_11 + _LEAF_1221_12, 2
    )
    # 旧口径实测值（211,252,631.06）必须 ≠ 新口径
    assert round(deepest_only, 2) == 211252631.06
    assert round(agg["closing"], 2) != round(deepest_only, 2)


# ── 备抵科目范围（配合 Property 2 的聚合侧证据） ──────────────────────────────


def test_provision_scoped_to_other_receivable_subaccount():
    """1231.03 口径 = 900,217.36；整个 1231 口径 = 28,464,225.16（含应收账款）。"""
    leaves = select_leaves(_real_1231_tree())
    only_k1 = aggregate_leaves(leaves, ["1231.03"], absolute=True)
    whole = aggregate_leaves(leaves, ["1231"], absolute=True)
    assert round(only_k1["closing"], 2) == 900217.36
    assert round(only_k1["opening"], 2) == 639230.01
    assert round(whole["closing"], 2) == 28464225.16
    # 反向自检：两者确实不同（否则本测试空转）
    assert round(only_k1["closing"], 2) != round(whole["closing"], 2)


def test_absolute_only_applies_to_aggregate():
    """`absolute=True` 只对聚合结果取绝对值，不在行级翻转方向。"""
    rows = [
        LeafRow(account_code="1231.03", closing=-100.0, direction="credit"),
        LeafRow(account_code="1231.03.01", closing=-40.0, direction="credit"),
    ]
    leaves = select_leaves(rows)
    assert [r.account_code for r in leaves] == ["1231.03.01"]
    assert aggregate_leaves(leaves, ["1231.03"], absolute=True)["closing"] == 40.0
    assert aggregate_leaves(leaves, ["1231.03"])["closing"] == -40.0


def test_negative_debit_leaf_not_flipped():
    """实测存在 direction='debit' 且余额为负的合法叶子 → 不得 `+ABS()` 翻正。"""
    rows = [
        LeafRow(account_code="1221", closing=-227132.40, direction="debit"),
        LeafRow(account_code="1221.98.07", closing=-227132.40, direction="debit"),
    ]
    leaves = select_leaves(rows)
    agg = aggregate_leaves(leaves, ["1221"])
    assert agg["closing"] == -227132.40


# ── 前缀过滤的点号边界 ───────────────────────────────────────────────────────


def test_prefix_match_requires_dot_boundary():
    rows = [
        LeafRow(account_code="1221", closing=1.0),
        LeafRow(account_code="12210", closing=99.0),
        LeafRow(account_code="1221.01", closing=2.0),
    ]
    picked = {r.account_code for r in filter_by_prefixes(rows, ["1221"])}
    assert picked == {"1221", "1221.01"}
    assert "12210" not in picked


def test_dataset_scoped_leaf_detection():
    """子科目须与父级同数据集才算其子科目。"""
    rows = [
        LeafRow(account_code="1221", closing=10.0, dataset_id="A"),
        LeafRow(account_code="1221.01", closing=10.0, dataset_id="B"),
    ]
    leaves = {(r.account_code, r.dataset_id) for r in select_leaves(rows)}
    assert leaves == {("1221", "A"), ("1221.01", "B")}


def test_empty_inputs_are_safe():
    assert select_leaves([]) == []
    assert filter_by_prefixes([], ["1221"]) == []
    assert aggregate_leaves([], ["1221"]) == {
        "opening": 0.0,
        "closing": 0.0,
        "debit": 0.0,
        "credit": 0.0,
    }
    assert aggregate_leaves(_real_1221_tree(), []) == {
        "opening": 0.0,
        "closing": 0.0,
        "debit": 0.0,
        "credit": 0.0,
    }
    assert parent_totals([], "1221")["closing"] == 0.0


def test_to_leaf_rows_accepts_dict_and_object():
    from types import SimpleNamespace

    rows = to_leaf_rows(
        [
            {
                "account_code": " 1221.01 ",
                "account_name": "子科目",
                "opening_balance": "1.5",
                "closing_balance": None,
                "debit_amount": 2,
                "credit_amount": "x",
                "closing_direction": "debit",
                "dataset_id": None,
            },
            SimpleNamespace(
                account_code="1221.02",
                account_name=None,
                opening_balance=None,
                closing_balance=3.25,
                debit_amount=None,
                credit_amount=None,
                closing_direction=None,
                dataset_id="d1",
            ),
            {"account_code": "   "},  # 空码丢弃
        ]
    )
    assert [r.account_code for r in rows] == ["1221.01", "1221.02"]
    assert rows[0].opening == 1.5
    assert rows[0].closing == 0.0
    assert rows[0].credit == 0.0  # 非数字降级为 0
    assert rows[1].dataset_id == "d1"


# ── PBT：任意参差树的叶子性质 ─────────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.sampled_from(["1221", "1221.01", "1221.01.01", "1221.02", "1221.02.03"]),
            st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=8,
    )
)
def test_pbt_leaves_pairwise_non_prefix(pairs):
    seen: dict[str, float] = {}
    for code, amt in pairs:
        seen[code] = amt
    rows = [LeafRow(account_code=c, closing=v, dataset_id="X") for c, v in seen.items()]
    leaves = select_leaves(rows)
    codes = [r.account_code for r in leaves]
    assert len(codes) == len(set(codes))
    for a in codes:
        for b in codes:
            if a != b:
                assert not b.startswith(a + ".")
    # 叶子是原行集的子集，且非空（任何非空行集至少有一个叶子）
    assert leaves
    assert set(codes) <= set(seen)
