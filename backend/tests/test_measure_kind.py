"""测试度量类型枚举和校验"""
import pytest
from app.schemas.measure_kind import MeasureKind, RatioScale, validate_ratio_scale


def test_measure_kind_values():
    """测试七类 MeasureKind 枚举值"""
    assert MeasureKind.AMOUNT == "amount"
    assert MeasureKind.RATIO == "ratio"
    assert MeasureKind.COUNT == "count"
    assert MeasureKind.QUANTITY == "quantity"
    assert MeasureKind.EXCHANGE_RATE == "exchange_rate"
    assert MeasureKind.UNIT_PRICE == "unit_price"
    assert MeasureKind.TEXT == "text"

    # 验证枚举成员数量
    assert len(list(MeasureKind)) == 7


def test_ratio_scale_values():
    """测试 RatioScale 枚举值"""
    assert RatioScale.FRACTION == "fraction"
    assert RatioScale.PERCENT_POINTS == "percent_points"

    # 验证枚举成员数量
    assert len(list(RatioScale)) == 2


class TestValidateRatioScale:
    """测试 validate_ratio_scale 校验函数"""

    def test_ratio_kind_requires_ratio_scale(self):
        """ratio kind 必须传递 ratio_scale"""
        with pytest.raises(ValueError, match="ratio kind 必须传递 ratio_scale"):
            validate_ratio_scale(MeasureKind.RATIO, None)

    def test_ratio_kind_with_ratio_scale_ok(self):
        """ratio kind 带 ratio_scale 应通过"""
        # 不应抛出异常
        validate_ratio_scale(MeasureKind.RATIO, RatioScale.FRACTION)
        validate_ratio_scale(MeasureKind.RATIO, RatioScale.PERCENT_POINTS)

    def test_non_ratio_kind_forbids_ratio_scale(self):
        """非 ratio kind 禁止传递 ratio_scale"""
        for kind in [
            MeasureKind.AMOUNT,
            MeasureKind.COUNT,
            MeasureKind.QUANTITY,
            MeasureKind.EXCHANGE_RATE,
            MeasureKind.UNIT_PRICE,
            MeasureKind.TEXT
        ]:
            with pytest.raises(ValueError, match=f"{kind} kind 禁止传递 ratio_scale"):
                validate_ratio_scale(kind, RatioScale.FRACTION)

    def test_non_ratio_kind_without_ratio_scale_ok(self):
        """非 ratio kind 不传 ratio_scale 应通过"""
        for kind in [
            MeasureKind.AMOUNT,
            MeasureKind.COUNT,
            MeasureKind.QUANTITY,
            MeasureKind.EXCHANGE_RATE,
            MeasureKind.UNIT_PRICE,
            MeasureKind.TEXT
        ]:
            # 不应抛出异常
            validate_ratio_scale(kind, None)

    def test_none_kind_with_none_ratio_scale_ok(self):
        """kind 为 None 且 ratio_scale 为 None 应通过"""
        # 未登记分支，不应抛出异常
        validate_ratio_scale(None, None)

    def test_none_kind_with_ratio_scale_fails(self):
        """kind 为 None 但带 ratio_scale 应失败"""
        # None 不等于 ratio，应当失败
        with pytest.raises(ValueError, match="None kind 禁止传递 ratio_scale"):
            validate_ratio_scale(None, RatioScale.FRACTION)
