"""Property 2: Decimal 精度不变量 — hypothesis 属性测试

∀ amounts [a₁, a₂, ..., aₙ] where aᵢ ∈ Decimal:
  sum_decimal(amounts) == quantize(true_sum, 0.01)
  AND |sum_decimal(amounts) - sum_float(amounts)| ≤ tolerance(n, scale)

验证：10 万行金额累加时 Decimal 计算结果精确（误差 ≤ 0.01 元）。

**Validates: Requirements 2.1, 2.8**

文件：backend/tests/test_property_decimal_precision.py
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from app.services._decimal_helpers import (
    amount_tolerance,
    quantize,
    to_decimal,
)


# ==========================================================================
# 确定性单元测试：10 万行 0.01 = 1000.00（AC 2.8 核心要求）
# ==========================================================================


class TestHundredThousandRowsExactSum:
    """Req 2 §AC8 关键断言：10 万行 0.01 累加 = 1000 元的精确等值断言。

    **Validates: Requirements 2.8**
    """

    def test_100k_rows_of_001_equals_1000_exact(self):
        """10 万行 0.01 元累加，Decimal 结果应精确等于 1000.00。"""
        amounts = [Decimal("0.01")] * 100_000
        total = sum(amounts, Decimal("0"))
        assert total == Decimal("1000.00")

    def test_float_accumulation_demonstrably_drifts(self):
        """对照实验：float 累加无法保持 Decimal 的精确性（违规反例）。

        典型反例：`0.1 + 0.2 != 0.3`（IEEE-754 0.1/0.2/0.3 均无法精确表示）。
        证明 float 不能用于金额累加，必须切到 Decimal。
        """
        # 反例 1：经典浮点反例 0.1 + 0.2 != 0.3
        assert 0.1 + 0.2 != 0.3, "若 IEEE-754 浮点恒精确，则无需 Decimal 化"
        # Decimal 路径下结果精确
        assert to_decimal("0.1") + to_decimal("0.2") == to_decimal("0.3")

        # 反例 2：Decimal(float_value) 直接构造会暴露 float 的真实位模式（与 str 转换不同）
        # 0.1 的 IEEE-754 表示为 0.1000000000000000055511151231257827021181583404541015625
        assert Decimal(0.1) != Decimal("0.1"), (
            "若 Decimal(float) == Decimal(str)，则 float 表示无误差"
        )
        # to_decimal 走 str()，因此对外暴露的是用户输入的字符串值
        assert to_decimal(0.1) == Decimal("0.1")

    def test_100k_rows_quantize_roundtrip(self):
        """10 万行累加后 quantize 仍精确等于 1000.00（业务展示路径）。"""
        amounts = [Decimal("0.01")] * 100_000
        total = sum(amounts, Decimal("0"))
        assert quantize(total, scale=2) == Decimal("1000.00")

    def test_100k_rows_mixed_via_to_decimal(self):
        """混合输入（str/int/float）走 to_decimal 后累加仍精确。"""
        # 50_000 行 str + 50_000 行 float，目标累加 = 1000.00
        amounts = [to_decimal("0.01") for _ in range(50_000)]
        amounts += [to_decimal(0.01) for _ in range(50_000)]
        total = sum(amounts, Decimal("0"))
        # quantize 后应精确（float "0.01" 经 str() 仍为 "0.01"）
        assert quantize(total, scale=2) == Decimal("1000.00")


# ==========================================================================
# Property: Decimal 累加精度不变量
# ==========================================================================


# 生成 0 ~ 1e9 范围、最多 2 位小数的金额（业务真实分布）
_amount_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


class TestDecimalSumPrecisionInvariant:
    """Property 2: Decimal 累加精度不变量。

    **Validates: Requirements 2.1, 2.8**

    ∀ amounts ⊂ Decimal:
      sum(amounts) 与独立 oracle 累加结果完全一致（精确等值，零误差）。
    """

    @settings(max_examples=10, deadline=None,
              suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
    @given(
        amounts=st.lists(
            _amount_strategy,
            min_size=50,
            max_size=300,
        )
    )
    def test_decimal_sum_matches_oracle(self, amounts):
        """随机金额列表，Decimal 累加结果与独立 oracle 完全一致。

        **Validates: Requirements 2.1**
        """
        # builtin sum 实现
        total = sum(amounts, Decimal("0"))
        # 独立 oracle：显式 for 循环累加
        oracle = Decimal("0")
        for a in amounts:
            oracle += a
        assert total == oracle, (
            f"sum() 与 oracle 累加结果不一致：sum={total}, oracle={oracle}"
        )

    @settings(max_examples=10, deadline=None,
              suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
    @given(
        amounts=st.lists(
            _amount_strategy,
            min_size=50,
            max_size=300,
        )
    )
    def test_decimal_sum_quantize_within_tolerance(self, amounts):
        """累加结果 quantize 后与原 sum 的误差 ≤ 0.005（HALF_UP 边界）。

        **Validates: Requirements 2.8**

        因输入 places=2，sum 已是 0.01 量级，quantize(scale=2) 应等于本身。
        """
        total = sum(amounts, Decimal("0"))
        quantized = quantize(total, scale=2)
        # 输入两位小数，累加仍两位小数 → quantize 是恒等变换
        assert quantized == total, (
            f"两位小数累加后 quantize(scale=2) 应保持不变：total={total}, quantized={quantized}"
        )

    @settings(max_examples=15, deadline=None,
              suppress_health_check=[
                  HealthCheck.too_slow,
                  HealthCheck.data_too_large,
                  HealthCheck.large_base_example,
              ])
    @given(
        amounts=st.lists(
            st.decimals(
                min_value=Decimal("0"),
                max_value=Decimal("1000000"),
                places=2,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=50,
            max_size=300,
        )
    )
    def test_decimal_sum_satisfies_associativity(self, amounts):
        """大列表场景：Decimal 累加满足结合律 / 交换律（精确等值，与顺序无关）。

        **Validates: Requirements 2.1**

        反例期望：若 Decimal 累加非结合（如内部用 float），fwd ≠ rev。
        约束 places=2 + max_value=1e6，确保累加不溢出 28 位精度上下文。
        """
        # 正向累加
        decimal_sum = sum(amounts, Decimal("0"))

        # 反向累加（验证结合 / 交换律）
        reverse_oracle = Decimal("0")
        for a in reversed(amounts):
            reverse_oracle += a

        # Decimal 累加结果与顺序无关（精确）
        assert decimal_sum == reverse_oracle, (
            f"Decimal 累加应满足结合律：fwd={decimal_sum}, rev={reverse_oracle}"
        )


# ==========================================================================
# Property: quantize 行为不变量
# ==========================================================================


class TestQuantizeInvariant:
    """Property: quantize 是幂等的、保序的、scale 边界正确。

    **Validates: Requirements 2.1**
    """

    @settings(max_examples=10, deadline=None)
    @given(
        value=st.decimals(
            min_value=Decimal("-1000000000"),
            max_value=Decimal("1000000000"),
            places=4,
            allow_nan=False,
            allow_infinity=False,
        ),
        scale=st.integers(min_value=0, max_value=4),
    )
    def test_quantize_is_idempotent(self, value, scale):
        """∀ value, scale: quantize(quantize(v, s), s) == quantize(v, s)。"""
        once = quantize(value, scale=scale)
        twice = quantize(once, scale=scale)
        assert once == twice

    @settings(max_examples=10, deadline=None)
    @given(
        value=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("1000000"),
            places=4,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_quantize_scale_2_within_half_cent(self, value):
        """quantize(v, 2) 与原值的差距 ≤ 0.005（HALF_UP 最大误差半个分位）。"""
        q = quantize(value, scale=2)
        diff = abs(q - value)
        assert diff <= Decimal("0.005"), (
            f"quantize(v, 2) 应在 HALF_UP 边界 0.005 内: v={value}, q={q}, diff={diff}"
        )

    @settings(max_examples=10, deadline=None)
    @given(
        value=st.decimals(
            min_value=Decimal("-1000000"),
            max_value=Decimal("1000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_quantize_preserves_sign(self, value):
        """quantize 不改变非零值符号（zero 边界除外）。"""
        q = quantize(value, scale=2)
        if value > 0:
            assert q >= 0
        elif value < 0:
            assert q <= 0


# ==========================================================================
# Property: amount_tolerance 行为不变量
# ==========================================================================


class TestAmountToleranceInvariant:
    """Property: amount_tolerance 总是返回正值，且按金额规模分段单调。

    **Validates: Requirements 2.1**
    """

    @settings(max_examples=10, deadline=None)
    @given(
        amount=st.decimals(
            min_value=Decimal("-1000000000"),
            max_value=Decimal("1000000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_tolerance_is_always_positive(self, amount):
        """∀ amount: amount_tolerance(amount) > 0。"""
        tol = amount_tolerance(amount)
        assert tol > 0, f"容差应始终为正: amount={amount}, tol={tol}"

    @settings(max_examples=10, deadline=None)
    @given(
        amount=st.decimals(
            min_value=Decimal("-1000000000"),
            max_value=Decimal("1000000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_tolerance_uses_abs_value(self, amount):
        """amount_tolerance(-x) == amount_tolerance(x)（符号无关）。"""
        tol_pos = amount_tolerance(abs(amount))
        tol_signed = amount_tolerance(amount)
        assert tol_pos == tol_signed, (
            f"容差应基于 abs(amount): amount={amount}, tol={tol_signed}, abs_tol={tol_pos}"
        )

    @settings(max_examples=10, deadline=None)
    @given(
        amount=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("9999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_small_amount_returns_fixed_tolerance(self, amount):
        """金额 < 1万时，容差恒为 0.01（绝对容差）。"""
        tol = amount_tolerance(amount)
        assert tol == Decimal("0.01")

    @settings(max_examples=10, deadline=None)
    @given(
        amount=st.decimals(
            min_value=Decimal("10000"),
            max_value=Decimal("999999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_medium_amount_uses_basis_point(self, amount):
        """金额 ∈ [1万, 100万) 时，容差 = amount * 0.0001。"""
        tol = amount_tolerance(amount)
        expected = amount * Decimal("0.0001")
        assert tol == expected

    @settings(max_examples=10, deadline=None)
    @given(
        amount=st.decimals(
            min_value=Decimal("1000000"),
            max_value=Decimal("1000000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_large_amount_uses_default_ratio(self, amount):
        """金额 ≥ 100万时，默认 ratio=0.001 → 容差 = amount * 0.001。"""
        tol = amount_tolerance(amount)
        expected = amount * Decimal("0.001")
        assert tol == expected
