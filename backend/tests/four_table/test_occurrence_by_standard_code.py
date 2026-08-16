"""发生额按标准码归集的纯函数守卫（Task 4）。

覆盖三条口径约定（`occurrence_by_standard_code` 模块 docstring）：

1. **只汇总叶子** —— `tb_balance` 父子并存，直接 SUM 会双算
2. **发生额不做方向归一** —— `debit_amount`/`credit_amount` 本身是分侧金额
3. **未映射叶子按最长前缀继承祖先映射** —— `account_mapping` 常只登记父科目

外加两条零回归约束：

- 合并只**新增**发生额键，既有余额键逐字不动
- 借贷双方均为 0 的标准码**不产出键**（让「列无数据」如实生效，
  区分「余额为 0」与「本项目无此科目」）

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 2.2, 2.4 / Property 6~8
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.four_table.leaf_aggregation import LeafRow, select_leaves  # noqa: E402
from app.services.four_table.occurrence_by_standard_code import (  # noqa: E402
    CREDIT_KEY,
    DEBIT_KEY,
    _longest_prefix_standard,
    _top_segment,
    aggregate_occurrence,
    merge_occurrence_into_tb_data,
)


def _leaf(code: str, debit: float = 0.0, credit: float = 0.0, name: str = "") -> LeafRow:
    return LeafRow(
        account_code=code,
        account_name=name or code,
        opening=0.0,
        closing=0.0,
        debit=debit,
        credit=credit,
        direction="",
        opening_direction="",
        dataset_id=None,
    )


class TestTopSegment:
    def test_dotted_and_flat_and_dashed(self):
        assert _top_segment("1601") == "1601"
        assert _top_segment("1601.02") == "1601"
        assert _top_segment("160102") == "1601"
        assert _top_segment("1231-02") == "1231"

    def test_non_numeric_returns_as_is(self):
        assert _top_segment("ABC") == "ABC"
        assert _top_segment("") == ""


class TestLongestPrefixInheritance:
    def test_exact_match_wins(self):
        mapping = {"1601": "1601", "1601.02": "1602"}
        assert _longest_prefix_standard("1601.02", mapping) == "1602"

    def test_inherits_from_ancestor(self):
        """`account_mapping` 只登记父科目时，叶子必须继承父映射。"""
        mapping = {"1601": "1601"}
        assert _longest_prefix_standard("1601.02.03", mapping) == "1601"

    def test_longest_prefix_beats_shorter(self):
        mapping = {"1601": "1601", "1601.02": "1699"}
        assert _longest_prefix_standard("1601.02.03", mapping) == "1699"

    def test_digit_boundary_not_crossed(self):
        """🔴 `1221` 不得命中 `12210`（严格分级边界，同 `filter_by_prefixes` 口径）。"""
        mapping = {"1221": "1221"}
        # 12210 的下一位是数字 → 不算 1221 的子级
        assert _longest_prefix_standard("12210", mapping) == "1221"  # 退化到一级段
        # 但退化结果恰好也是 1221，故再用一个不同的一级段验证边界确实生效
        mapping2 = {"1221": "9999"}
        assert _longest_prefix_standard("12210", mapping2) == "1221", (
            "12210 被误判为 1221 的子级 → 会继承到 9999，边界失效"
        )
        # 点号分级则应命中
        assert _longest_prefix_standard("1221.0", mapping2) == "9999"

    def test_no_mapping_falls_back_to_top_segment(self):
        assert _longest_prefix_standard("1601.02", {}) == "1601"


class TestAggregateOccurrence:
    def test_sums_by_side_without_direction_normalization(self):
        """发生额按侧原样求和，不套 direction（套了会把贷方翻负）。"""
        leaves = [_leaf("1601.01", debit=100, credit=30), _leaf("1601.02", debit=200, credit=70)]
        out = aggregate_occurrence(leaves, {"1601": "1601"})
        assert out["1601"][DEBIT_KEY] == Decimal("300")
        assert out["1601"][CREDIT_KEY] == Decimal("100")

    def test_leaf_only_no_parent_double_count(self):
        """父行必须先经 `select_leaves` 剔除，否则父子双算。"""
        rows = [
            _leaf("1601", debit=300, credit=100),      # 父行（金额 = 子行之和）
            _leaf("1601.01", debit=100, credit=30),
            _leaf("1601.02", debit=200, credit=70),
        ]
        leaves = select_leaves(rows)
        assert {l.account_code for l in leaves} == {"1601.01", "1601.02"}
        out = aggregate_occurrence(leaves, {"1601": "1601"})
        assert out["1601"][DEBIT_KEY] == Decimal("300"), "父子双算"

    def test_naive_sum_would_double_count(self):
        """反向自检：不筛叶子直接聚合确实会双算（证明上一条断言非空转）。"""
        rows = [
            _leaf("1601", debit=300),
            _leaf("1601.01", debit=100),
            _leaf("1601.02", debit=200),
        ]
        naive = aggregate_occurrence(rows, {"1601": "1601"})
        assert naive["1601"][DEBIT_KEY] == Decimal("600"), (
            "若此断言失败说明 aggregate_occurrence 内部已自行筛叶子，"
            "上一条测试的 select_leaves 变成空操作"
        )

    def test_maps_different_leaves_to_different_standard_codes(self):
        """同一父科目下的叶子可映射到不同标准码（实证 1525 → 1521 或 1525）。"""
        leaves = [_leaf("1521.01", debit=10), _leaf("1521.02", debit=20)]
        mapping = {"1521.01": "1521", "1521.02": "1525"}
        out = aggregate_occurrence(leaves, mapping)
        assert out["1521"][DEBIT_KEY] == Decimal("10")
        assert out["1525"][DEBIT_KEY] == Decimal("20")

    def test_zero_rows_produce_no_key(self):
        """借贷均为 0 的标准码不产出键 —— 让「列无数据」如实生效。"""
        leaves = [_leaf("1601.01", debit=0, credit=0)]
        assert aggregate_occurrence(leaves, {"1601": "1601"}) == {}

    def test_blank_code_skipped(self):
        leaves = [_leaf("", debit=99), _leaf("1601", debit=1)]
        out = aggregate_occurrence(leaves, {})
        assert out == {"1601": {DEBIT_KEY: Decimal("1"), CREDIT_KEY: Decimal("0")}}


class TestMergeIntoTbData:
    def test_existing_balance_keys_untouched(self):
        """零回归核心：既有余额键逐字不动。"""
        tb = {"1601": {"期末余额": 1000.0, "期初余额": 800.0, "审定数": 1000.0}}
        before = dict(tb["1601"])
        merge_occurrence_into_tb_data(
            tb, {"1601": {DEBIT_KEY: Decimal("300"), CREDIT_KEY: Decimal("100")}},
            as_float=True,
        )
        for k, v in before.items():
            assert tb["1601"][k] == v, f"既有键 {k} 被改动"
        assert tb["1601"][DEBIT_KEY] == 300.0
        assert tb["1601"][CREDIT_KEY] == 100.0

    def test_creates_entry_for_occurrence_only_code(self):
        """只有发生额没有余额的科目（损益类年末结转后余额为 0）也要建条目。"""
        tb: dict[str, dict] = {}
        merge_occurrence_into_tb_data(
            tb, {"6115": {DEBIT_KEY: Decimal("5"), CREDIT_KEY: Decimal("0")}}
        )
        assert tb["6115"][DEBIT_KEY] == Decimal("5")

    def test_decimal_by_default_float_on_demand(self):
        tb1: dict[str, dict] = {}
        merge_occurrence_into_tb_data(tb1, {"1601": {DEBIT_KEY: Decimal("1")}})
        assert isinstance(tb1["1601"][DEBIT_KEY], Decimal)

        tb2: dict[str, dict] = {}
        merge_occurrence_into_tb_data(
            tb2, {"1601": {DEBIT_KEY: Decimal("1")}}, as_float=True
        )
        assert isinstance(tb2["1601"][DEBIT_KEY], float)

    def test_empty_occurrence_is_noop(self):
        tb = {"1601": {"期末余额": 1.0}}
        snapshot = {k: dict(v) for k, v in tb.items()}
        merge_occurrence_into_tb_data(tb, {})
        assert tb == snapshot


class TestEngineIntegration:
    """端到端：合并后 `TB(code,'本期借方')` 必须取到真实发生额。"""

    def test_formula_reads_merged_occurrence(self):
        from app.services.formula_engine import FormulaContext, execute

        tb_data: dict[str, dict] = {
            "1601": {"期末余额": Decimal("1000"), "年初余额": Decimal("800")}
        }
        merge_occurrence_into_tb_data(
            tb_data,
            {"1601": {DEBIT_KEY: Decimal("300"), CREDIT_KEY: Decimal("100")}},
        )
        ctx = FormulaContext(tb_data=tb_data)

        for formula, expect in (
            ("=TB('1601','本期借方')", Decimal("300")),
            ("=TB('1601','借方发生额')", Decimal("300")),
            ("=TB('1601','本期贷方')", Decimal("100")),
            ("=TB('1601','贷方发生额')", Decimal("100")),
            # 零回归：既有列名不变
            ("=TB('1601','期末余额')", Decimal("1000")),
            ("=TB('1601','期初余额')", Decimal("800")),
        ):
            res = execute(formula, ctx)
            assert res.errors == [], f"{formula} → {res.errors}"
            assert res.value == expect, f"{formula} = {res.value}, 期望 {expect}"

    def test_occurrence_not_silently_replaced_by_closing_balance(self):
        """🔴 改造前的核心缺陷：没有发生额数据时**不得**回退期末余额。"""
        from app.services.formula_engine import FormulaContext, execute

        ctx = FormulaContext(tb_data={"1601": {"期末余额": Decimal("1000")}})
        res = execute("=TB('1601','本期借方')", ctx)
        assert res.value == Decimal("0"), (
            f"发生额缺失时返回了 {res.value}（应为 0）—— 静默回退期末余额复活"
        )
