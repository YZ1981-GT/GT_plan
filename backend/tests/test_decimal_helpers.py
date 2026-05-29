"""_decimal_helpers 单元测试 — 20+ 用例覆盖 to_decimal / quantize / amount_tolerance

验证 Req 2（金额 Decimal 化）核心转换器的正确性。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services._decimal_helpers import (
    AmountConversionError,
    amount_tolerance,
    quantize,
    to_decimal,
)


# ==========================================================================
# to_decimal 测试
# ==========================================================================


class TestToDecimal:
    """to_decimal 函数测试集。"""

    # --- None 处理 ---

    def test_none_disallowed_raises(self):
        """None + allow_none=False 应抛出 AmountConversionError。"""
        with pytest.raises(AmountConversionError, match="不能为空"):
            to_decimal(None)

    def test_none_allowed_returns_none(self):
        """None + allow_none=True 应返回 None。"""
        result = to_decimal(None, allow_none=True)
        assert result is None

    # --- NaN / Infinity ---

    def test_nan_string_raises(self):
        """字符串 'NaN' 应抛出 AmountConversionError。"""
        with pytest.raises(AmountConversionError, match="NaN 或 Infinity"):
            to_decimal("NaN")

    def test_infinity_string_raises(self):
        """字符串 'Infinity' 应抛出 AmountConversionError。"""
        with pytest.raises(AmountConversionError, match="NaN 或 Infinity"):
            to_decimal("Infinity")

    def test_negative_infinity_raises(self):
        """字符串 '-Infinity' 应抛出 AmountConversionError。"""
        with pytest.raises(AmountConversionError, match="NaN 或 Infinity"):
            to_decimal("-Infinity")

    def test_float_nan_raises(self):
        """float('nan') 应抛出 AmountConversionError。"""
        with pytest.raises(AmountConversionError, match="NaN 或 Infinity"):
            to_decimal(float("nan"))

    def test_float_inf_raises(self):
        """float('inf') 应抛出 AmountConversionError。"""
        with pytest.raises(AmountConversionError, match="NaN 或 Infinity"):
            to_decimal(float("inf"))

    # --- 科学计数法 ---

    def test_scientific_notation_string(self):
        """科学计数法字符串应正确转换。"""
        result = to_decimal("1.5e3")
        assert result == Decimal("1500")

    def test_scientific_notation_negative_exponent(self):
        """负指数科学计数法应正确转换。"""
        result = to_decimal("2.5e-4")
        assert result == Decimal("0.00025")

    # --- 各类型输入 ---

    def test_str_input(self):
        """字符串金额应正确转换。"""
        result = to_decimal("123.45")
        assert result == Decimal("123.45")

    def test_int_input(self):
        """整数应正确转换为 Decimal。"""
        result = to_decimal(100)
        assert result == Decimal("100")

    def test_float_input(self):
        """浮点数应通过 str() 转换为 Decimal。"""
        result = to_decimal(3.14)
        assert result == Decimal(str(3.14))

    def test_decimal_input_passthrough(self):
        """Decimal 输入应直接返回（不经过 str 转换）。"""
        d = Decimal("99.99")
        result = to_decimal(d)
        assert result is d

    # --- 空字符串 ---

    def test_empty_string_raises(self):
        """空字符串应抛出 AmountConversionError。"""
        with pytest.raises(AmountConversionError, match="格式非法"):
            to_decimal("")

    # --- 自定义 field 名称 ---

    def test_custom_field_name_in_error(self):
        """自定义 field 名称应出现在错误消息中。"""
        with pytest.raises(AmountConversionError, match="借方金额"):
            to_decimal(None, field="借方金额")

    # --- 零值 ---

    def test_zero_string(self):
        """字符串 '0' 应正确转换。"""
        result = to_decimal("0")
        assert result == Decimal("0")

    # --- 负数 ---

    def test_negative_value(self):
        """负数应正确转换。"""
        result = to_decimal("-500.25")
        assert result == Decimal("-500.25")


# ==========================================================================
# quantize 测试
# ==========================================================================


class TestQuantize:
    """quantize 函数测试集。"""

    def test_scale_2_default(self):
        """默认 scale=2 应保留两位小数。"""
        result = quantize(Decimal("123.456"))
        assert result == Decimal("123.46")

    def test_scale_0_integer(self):
        """scale=0 应四舍五入到整数。"""
        result = quantize(Decimal("99.5"), scale=0)
        assert result == Decimal("100")

    def test_scale_4_rate(self):
        """scale=4 应保留四位小数（汇率场景）。"""
        result = quantize(Decimal("6.12345"), scale=4)
        assert result == Decimal("6.1235")

    def test_round_half_up_boundary(self):
        """ROUND_HALF_UP: 0.005 应进位到 0.01。"""
        result = quantize(Decimal("0.005"))
        assert result == Decimal("0.01")

    def test_round_half_up_below(self):
        """ROUND_HALF_UP: 0.004 应截断到 0.00。"""
        result = quantize(Decimal("0.004"))
        assert result == Decimal("0.00")

    def test_large_amount_scale_2(self):
        """大金额 scale=2 应正确四舍五入。"""
        result = quantize(Decimal("9999999.999"))
        assert result == Decimal("10000000.00")


# ==========================================================================
# amount_tolerance 测试
# ==========================================================================


class TestAmountTolerance:
    """amount_tolerance 函数测试集。"""

    def test_none_returns_minimum(self):
        """None 输入应返回最小容差 0.01。"""
        result = amount_tolerance(None)
        assert result == Decimal("0.01")

    def test_small_amount_below_10000(self):
        """金额 < 1万应返回绝对容差 0.01。"""
        result = amount_tolerance(Decimal("5000"))
        assert result == Decimal("0.01")

    def test_zero_amount(self):
        """金额为 0 应返回绝对容差 0.01。"""
        result = amount_tolerance(Decimal("0"))
        assert result == Decimal("0.01")

    def test_medium_amount_10000(self):
        """金额 = 1万（边界）应返回 amount * 0.0001。"""
        result = amount_tolerance(Decimal("10000"))
        assert result == Decimal("1.0000")

    def test_medium_amount_500000(self):
        """金额 50万应返回 amount * 0.0001 = 50。"""
        result = amount_tolerance(Decimal("500000"))
        assert result == Decimal("50.0000")

    def test_large_amount_1000000(self):
        """金额 = 100万（边界）应返回 amount * 0.001 = 1000。"""
        result = amount_tolerance(Decimal("1000000"))
        assert result == Decimal("1000.000")

    def test_large_amount_10000000(self):
        """金额 1000万应返回 amount * 0.001 = 10000。"""
        result = amount_tolerance(Decimal("10000000"))
        assert result == Decimal("10000.000")

    def test_negative_amount_uses_abs(self):
        """负金额应取绝对值计算容差。"""
        result = amount_tolerance(Decimal("-500000"))
        assert result == Decimal("50.0000")

    def test_custom_ratio(self):
        """自定义 ratio 应在大金额场景生效。"""
        result = amount_tolerance(Decimal("2000000"), ratio=Decimal("0.005"))
        assert result == Decimal("10000.000")
