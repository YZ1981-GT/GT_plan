"""Property-based tests for logic_check 7 条跨表勾稽真实失败语义。

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7 | Property 7**

验证目标：
1. 每条规则至少存在一个 pass 样例和一个 fail 样例（Req 4.6）。
2. #2 比较独立毛利来源（非自减自比），#5 使用两个不同 REPORT addr_id，
   #7 直接判断 cash >= 0（Req 4.2, 4.3, 4.4）。
3. 后端与前端降级模型等价：相同输入时 pass/fail 判定一致（Req 4.7）。
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.formula_management.logic_check import (
    CrossCheckOutcome,
    CrossCheckResult,
    build_cross_check_formulas,
    build_report_row_cache,
    run_cross_checks,
    _CROSS_CHECK_SEEDS,
)


# ─────────────────────────────────────────────────────────────────────────────
# 前端降级模型 Python 等价实现（与 computeCrossCheckResults 对齐）
# ─────────────────────────────────────────────────────────────────────────────
def _frontend_degraded_check(
    row_cache: dict[str, Decimal],
) -> list[bool]:
    """模拟前端降级模型（corrected 版本）的 7 条勾稽 pass/fail 判定。

    与后端 logic_check.py 中 _CROSS_CHECK_SEEDS 的表达式语义完全等价。
    这是"后端与前端降级模型等价"的验证基准。
    """
    def d(key: str) -> float:
        return float(row_cache.get(key, Decimal("0")))

    assets = d("assets_total")
    liabilities = d("liabilities_total")
    equity = d("equity_total")
    revenue = d("IS-001")
    cost = d("IS-002")
    gross_profit = d("IS-003")
    pbt = d("IS-017")
    tax = d("IS-018")
    net_profit = d("IS-019")
    eq_ending = d("EQ-ENDING")
    cash = d("BS-001")

    results: list[bool] = []

    # #1: 资产合计 = 负债合计 + 所有者权益合计 (tolerance=1)
    results.append(abs(round(assets - (liabilities + equity), 2)) <= 1)

    # #2: 营业收入 − 营业成本 = 独立毛利行（或收入/成本完整性检查）
    # 修正：比较计算毛利与独立毛利行；若独立毛利行为 0 则降为收入>=0且成本>=0
    if gross_profit != 0:
        results.append(abs(round((revenue - cost) - gross_profit, 2)) <= 1)
    else:
        results.append(revenue >= 0 and cost >= 0)

    # #3: 利润总额 − 所得税 = 净利润 (tolerance=1)
    results.append(abs(round((pbt - tax) - net_profit, 2)) <= 1)

    # #4: 资产 − 负债 = 权益 (tolerance=1)
    results.append(abs(round((assets - liabilities) - equity, 2)) <= 1)

    # #5: 所有者权益变动表期末合计 = 资产负债表权益合计 (两个独立 REPORT addr_id)
    results.append(abs(round(eq_ending - equity, 2)) <= 1)

    # #6: 有效税率 ≈ 25%
    if pbt > 0:
        results.append(abs(round(tax - pbt * 0.25, 2)) <= pbt * 0.05)
    else:
        results.append(abs(round(tax, 2)) < 0.01)

    # #7: 货币资金 >= 0 (真实谓词，非自适应容差)
    results.append(cash >= 0)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：执行后端 7 条勾稽（同步包装 async run_cross_checks）
# ─────────────────────────────────────────────────────────────────────────────
import asyncio


def _run_backend_checks(row_cache: dict[str, Decimal]) -> list[bool]:
    """同步执行后端 run_cross_checks 并返回 7 条 passed 列表。"""

    async def _inner():
        return await run_cross_checks(row_cache, resolve_refs=False)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(asyncio.run, _inner()).result()
    else:
        result = asyncio.run(_inner())
    return [o.passed for o in result.outcomes]


# ─────────────────────────────────────────────────────────────────────────────
# 固定 pass + fail 样例（Req 4.6）
# ─────────────────────────────────────────────────────────────────────────────
class TestLogicCheckPassFailExamples:
    """每条规则的固定 pass + fail 样例，验证真实可失败语义。"""

    # ── #1 资产合计 = 负债 + 权益 ──────────────────────────────────────────
    def test_rule1_pass(self):
        """#1 pass: 资产 = 负债 + 权益"""
        cache = {
            "assets_total": Decimal("1000"),
            "liabilities_total": Decimal("600"),
            "equity_total": Decimal("400"),
        }
        results = _run_backend_checks(cache)
        assert results[0] is True

    def test_rule1_fail(self):
        """#1 fail: 资产 ≠ 负债 + 权益（差异 > 1）"""
        cache = {
            "assets_total": Decimal("1000"),
            "liabilities_total": Decimal("600"),
            "equity_total": Decimal("100"),  # 差 300
        }
        results = _run_backend_checks(cache)
        assert results[0] is False

    # ── #2 营业收入 − 营业成本 = 独立毛利行 ──────────────────────────────────
    def test_rule2_pass_with_gross_profit(self):
        """#2 pass: 收入 - 成本 = 独立毛利行"""
        cache = {
            "IS-001": Decimal("5000"),
            "IS-002": Decimal("3000"),
            "IS-003": Decimal("2000"),  # 独立毛利 = 5000-3000
        }
        results = _run_backend_checks(cache)
        assert results[1] is True

    def test_rule2_fail_with_gross_profit(self):
        """#2 fail: 收入 - 成本 ≠ 独立毛利行（差异 > 1）"""
        cache = {
            "IS-001": Decimal("5000"),
            "IS-002": Decimal("3000"),
            "IS-003": Decimal("1500"),  # 独立毛利 ≠ 2000
        }
        results = _run_backend_checks(cache)
        assert results[1] is False

    def test_rule2_pass_fallback_revenue_cost_positive(self):
        """#2 pass (fallback): 无独立毛利行时，收入 >= 0 且 成本 >= 0"""
        cache = {
            "IS-001": Decimal("5000"),
            "IS-002": Decimal("3000"),
            "IS-003": Decimal("0"),  # 无独立毛利行
        }
        results = _run_backend_checks(cache)
        assert results[1] is True

    def test_rule2_fail_fallback_negative_revenue(self):
        """#2 fail (fallback): 无独立毛利行时，收入 < 0"""
        cache = {
            "IS-001": Decimal("-100"),
            "IS-002": Decimal("3000"),
            "IS-003": Decimal("0"),  # 无独立毛利行
        }
        results = _run_backend_checks(cache)
        assert results[1] is False

    # ── #3 利润总额 − 所得税 = 净利润 ──────────────────────────────────────
    def test_rule3_pass(self):
        """#3 pass: 利润总额 - 所得税 = 净利润"""
        cache = {
            "IS-017": Decimal("1000"),
            "IS-018": Decimal("250"),
            "IS-019": Decimal("750"),
        }
        results = _run_backend_checks(cache)
        assert results[2] is True

    def test_rule3_fail(self):
        """#3 fail: 利润总额 - 所得税 ≠ 净利润（差异 > 1）"""
        cache = {
            "IS-017": Decimal("1000"),
            "IS-018": Decimal("250"),
            "IS-019": Decimal("500"),  # 差 250
        }
        results = _run_backend_checks(cache)
        assert results[2] is False

    # ── #4 资产 − 负债 = 权益 ──────────────────────────────────────────────
    def test_rule4_pass(self):
        """#4 pass: 资产 - 负债 = 权益"""
        cache = {
            "assets_total": Decimal("1000"),
            "liabilities_total": Decimal("400"),
            "equity_total": Decimal("600"),
        }
        results = _run_backend_checks(cache)
        assert results[3] is True

    def test_rule4_fail(self):
        """#4 fail: 资产 - 负债 ≠ 权益（差异 > 1）"""
        cache = {
            "assets_total": Decimal("1000"),
            "liabilities_total": Decimal("400"),
            "equity_total": Decimal("200"),  # 差 400
        }
        results = _run_backend_checks(cache)
        assert results[3] is False

    # ── #5 所有者权益变动表期末 = 资产负债表权益 ──────────────────────────────
    def test_rule5_pass(self):
        """#5 pass: 权益变动表期末 = BS 权益合计（两个独立来源）"""
        cache = {
            "EQ-ENDING": Decimal("800"),
            "equity_total": Decimal("800"),
        }
        results = _run_backend_checks(cache)
        assert results[4] is True

    def test_rule5_fail(self):
        """#5 fail: 权益变动表期末 ≠ BS 权益合计（差异 > 1）"""
        cache = {
            "EQ-ENDING": Decimal("800"),
            "equity_total": Decimal("500"),  # 差 300
        }
        results = _run_backend_checks(cache)
        assert results[4] is False

    # ── #6 有效税率 ≈ 25% ──────────────────────────────────────────────────
    def test_rule6_pass(self):
        """#6 pass: 所得税 ≈ 利润总额 * 25%"""
        cache = {
            "IS-017": Decimal("1000"),
            "IS-018": Decimal("250"),  # 精确 25%
        }
        results = _run_backend_checks(cache)
        assert results[5] is True

    def test_rule6_fail(self):
        """#6 fail: 所得税偏离 25% 超过容差"""
        cache = {
            "IS-017": Decimal("1000"),
            "IS-018": Decimal("400"),  # 40%, 差 150 > 1000*0.05=50
        }
        results = _run_backend_checks(cache)
        assert results[5] is False

    # ── #7 货币资金 >= 0 ──────────────────────────────────────────────────
    def test_rule7_pass(self):
        """#7 pass: 货币资金 >= 0"""
        cache = {"BS-001": Decimal("100")}
        results = _run_backend_checks(cache)
        assert results[6] is True

    def test_rule7_pass_zero(self):
        """#7 pass: 货币资金 = 0"""
        cache = {"BS-001": Decimal("0")}
        results = _run_backend_checks(cache)
        assert results[6] is True

    def test_rule7_fail(self):
        """#7 fail: 货币资金 < 0（负值异常）"""
        cache = {"BS-001": Decimal("-50")}
        results = _run_backend_checks(cache)
        assert results[6] is False


# ─────────────────────────────────────────────────────────────────────────────
# PBT：后端与前端降级模型等价（Property 7）
# ─────────────────────────────────────────────────────────────────────────────
# Hypothesis 策略：生成报表金额（Decimal，保持有限范围）
_amount = st.decimals(
    min_value=Decimal("-1000000"),
    max_value=Decimal("1000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def _row_cache_strategy(draw: st.DrawFn) -> dict[str, Decimal]:
    """生成完整 row_cache（覆盖 7 条规则所需的全部引用键）。"""
    return {
        "assets_total": draw(_amount),
        "liabilities_total": draw(_amount),
        "equity_total": draw(_amount),
        "IS-001": draw(_amount),
        "IS-002": draw(_amount),
        "IS-003": draw(_amount),
        "IS-017": draw(_amount),
        "IS-018": draw(_amount),
        "IS-019": draw(_amount),
        "EQ-ENDING": draw(_amount),
        "BS-001": draw(_amount),
    }


class TestLogicCheckBackendFrontendEquivalence:
    """PBT: 后端与前端降级模型处理相同输入时 pass/fail 一致。

    **Validates: Requirements 4.7**
    """

    @given(row_cache=_row_cache_strategy())
    def test_backend_frontend_equivalence(self, row_cache: dict[str, Decimal]):
        """Property 7: 对任意输入，后端 7 条 logic_check 与前端降级模型
        的 pass/fail 判定逐条一致。"""
        backend_results = _run_backend_checks(row_cache)
        frontend_results = _frontend_degraded_check(row_cache)
        assert len(backend_results) == 7
        assert len(frontend_results) == 7
        for i in range(7):
            assert backend_results[i] == frontend_results[i], (
                f"Rule #{i+1} mismatch: backend={backend_results[i]}, "
                f"frontend={frontend_results[i]}, row_cache={row_cache}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# PBT：每条规则存在可失败输入（Property 7 补充）
# ─────────────────────────────────────────────────────────────────────────────
class TestLogicCheckFailability:
    """PBT: 验证每条规则至少存在使其失败的输入（不是恒真）。

    **Validates: Requirements 4.1, 4.5**
    """

    @given(data=st.data())
    def test_rule1_can_fail(self, data: st.DataObject):
        """#1 存在可失败输入"""
        assets = data.draw(_amount)
        liabilities = data.draw(_amount)
        # 构造使 #1 失败的权益值
        equity = assets - liabilities - Decimal("100")  # 差 100 > 1
        cache = {
            "assets_total": assets,
            "liabilities_total": liabilities,
            "equity_total": equity,
        }
        results = _run_backend_checks(cache)
        assert results[0] is False

    @given(data=st.data())
    def test_rule2_can_fail(self, data: st.DataObject):
        """#2 存在可失败输入（独立毛利行与计算毛利不等）"""
        revenue = data.draw(st.decimals(
            min_value=Decimal("100"), max_value=Decimal("1000000"),
            places=2, allow_nan=False, allow_infinity=False,
        ))
        cost = data.draw(st.decimals(
            min_value=Decimal("0"), max_value=revenue,
            places=2, allow_nan=False, allow_infinity=False,
        ))
        # 独立毛利行故意偏离计算毛利 > 1
        gross_profit = revenue - cost + Decimal("500")
        assume(gross_profit != Decimal("0"))
        cache = {
            "IS-001": revenue,
            "IS-002": cost,
            "IS-003": gross_profit,
        }
        results = _run_backend_checks(cache)
        assert results[1] is False

    @given(data=st.data())
    def test_rule5_can_fail(self, data: st.DataObject):
        """#5 存在可失败输入（两个独立来源不等）"""
        eq_ending = data.draw(_amount)
        equity = eq_ending + Decimal("100")  # 差 100 > 1
        cache = {
            "EQ-ENDING": eq_ending,
            "equity_total": equity,
        }
        results = _run_backend_checks(cache)
        assert results[4] is False

    @given(data=st.data())
    def test_rule7_can_fail(self, data: st.DataObject):
        """#7 存在可失败输入（负值货币资金）"""
        cash = data.draw(st.decimals(
            min_value=Decimal("-1000000"), max_value=Decimal("-0.01"),
            places=2, allow_nan=False, allow_infinity=False,
        ))
        cache = {"BS-001": cash}
        results = _run_backend_checks(cache)
        assert results[6] is False


# ─────────────────────────────────────────────────────────────────────────────
# 结构性验证
# ─────────────────────────────────────────────────────────────────────────────
class TestLogicCheckStructure:
    """验证 logic_check 结构正确性。"""

    def test_seven_seeds_exist(self):
        """7 条勾稽种子完整存在。"""
        assert len(_CROSS_CHECK_SEEDS) == 7

    def test_build_formulas_returns_seven(self):
        """build_cross_check_formulas 返回 7 条 FormulaRecord。"""
        formulas = build_cross_check_formulas()
        assert len(formulas) == 7
        for f in formulas:
            assert f.formula_type == "logic_check"
            assert f.expression
            assert f.issue_description

    def test_rule2_uses_independent_source(self):
        """#2 表达式引用 IS-003（独立毛利行），不再自减自比。"""
        seed = _CROSS_CHECK_SEEDS[1]
        assert "IS-003" in seed["refs"]
        assert "IS-001" in seed["refs"]
        assert "IS-002" in seed["refs"]
        # 表达式必须包含独立比较逻辑
        assert "IS-003" in seed["expression"]

    def test_rule5_uses_two_independent_addr_ids(self):
        """#5 使用两个不同 REPORT addr_id（EQ-ENDING vs equity_total）。"""
        seed = _CROSS_CHECK_SEEDS[4]
        assert "EQ-ENDING" in seed["refs"]
        assert "equity_total" in seed["refs"]
        # 不再自比
        assert seed["refs"][0] != seed["refs"][1]

    def test_rule7_direct_predicate(self):
        """#7 直接判断 >= 0，表达式不含 ABS 自适应容差。"""
        seed = _CROSS_CHECK_SEEDS[6]
        assert ">= 0" in seed["expression"] or ">=0" in seed["expression"]
        # 不得使用 ABS(cash) 作为容差
        assert "ABS" not in seed["expression"]

    def test_issue_generated_on_failure(self):
        """勾稽不通过时必须生成 Issue（Req 4.5）。"""
        # 构造一个一定会失败的 cache（#7 负货币资金）
        cache = {"BS-001": Decimal("-999")}
        results = asyncio.run(
            run_cross_checks(cache, resolve_refs=False)
        )
        # #7 必须失败并产 Issue
        rule7_outcome = results.outcomes[6]
        assert rule7_outcome.passed is False
        # Issue 列表必须非空
        rule7_issues = [i for i in results.issues if i.formula_id == "report-cross-check-7"]
        assert len(rule7_issues) > 0
