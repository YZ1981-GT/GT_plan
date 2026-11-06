"""跨层度量合同单测 + 前后端逐值对拍（spec platform-global-display-settings-closure 任务 6A）。

Validates: Requirements R6
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.contracts.display_measure import (
    AMOUNT_KINDS,
    DISPLAY_MEASURE_CONTRACT_INVALID,
    NON_AMOUNT_KINDS,
    DisplayMeasureContractError,
    DisplayMeasureKind,
    DisplayMeasureSpec,
    RatioScale,
    build_measure_spec,
)

_FRONTEND_TYPES = (
    Path(__file__).resolve().parents[2]
    / "audit-platform"
    / "frontend"
    / "src"
    / "types"
    / "displayMeasure.ts"
)


def _ts_string_array(source: str, const_name: str) -> list[str]:
    """从 `export const NAME = [ 'a', 'b' ] as const` 里取有序字符串字面量。"""
    m = re.search(
        rf"export const {re.escape(const_name)}(?:\s*:[^=]+)?\s*=\s*\[([^\]]*)\]\s*as const",
        source,
        re.S,
    )
    assert m, f"前端未找到常量 {const_name}"
    values = re.findall(r"'([^']+)'", m.group(1))
    assert values, f"前端常量 {const_name} 解析出空集合（分母为 0 即假绿）"
    return values


class TestSevenKindEnum:
    def test_kinds_are_exactly_seven_and_ordered(self):
        assert [k.value for k in DisplayMeasureKind] == [
            "amount",
            "quantity",
            "count",
            "ratio",
            "exchange_rate",
            "unit_price",
            "text",
        ]

    def test_only_amount_uses_divisor(self):
        assert {k.value for k in AMOUNT_KINDS} == {"amount"}
        assert {k.value for k in NON_AMOUNT_KINDS} == {
            "quantity",
            "count",
            "ratio",
            "exchange_rate",
            "unit_price",
            "text",
        }
        for kind in NON_AMOUNT_KINDS:
            scale = RatioScale.fraction if kind is DisplayMeasureKind.ratio else None
            spec = DisplayMeasureSpec(kind=kind, ratio_scale=scale)
            assert spec.uses_amount_divisor is False

    def test_ratio_scales_are_exactly_two(self):
        assert [s.value for s in RatioScale] == ["fraction", "percent_points"]


class TestRatioScaleInvariant:
    def test_ratio_requires_scale(self):
        with pytest.raises(DisplayMeasureContractError) as exc:
            DisplayMeasureSpec(kind=DisplayMeasureKind.ratio)
        assert exc.value.code == DISPLAY_MEASURE_CONTRACT_INVALID

    @pytest.mark.parametrize(
        "kind",
        [k for k in DisplayMeasureKind if k is not DisplayMeasureKind.ratio],
    )
    def test_non_ratio_forbids_scale(self, kind: DisplayMeasureKind):
        with pytest.raises(DisplayMeasureContractError):
            DisplayMeasureSpec(kind=kind, ratio_scale=RatioScale.fraction)

    @pytest.mark.parametrize("scale", list(RatioScale))
    def test_ratio_with_scale_is_valid(self, scale: RatioScale):
        spec = DisplayMeasureSpec(kind=DisplayMeasureKind.ratio, ratio_scale=scale)
        assert spec.as_wire() == {"measure_kind": "ratio", "ratio_scale": scale.value}

    def test_extra_field_forbidden(self):
        with pytest.raises(Exception):
            DisplayMeasureSpec(kind=DisplayMeasureKind.amount, divisor=1)  # type: ignore[call-arg]


class TestBuildMeasureSpec:
    def test_unregistered_returns_none(self):
        assert build_measure_spec(None) is None
        assert build_measure_spec("") is None
        assert build_measure_spec("   ") is None

    def test_unregistered_with_scale_is_error(self):
        with pytest.raises(DisplayMeasureContractError):
            build_measure_spec(None, "fraction")

    def test_unknown_kind_is_error(self):
        with pytest.raises(DisplayMeasureContractError) as exc:
            build_measure_spec("money", locator="X.yaml/sheet/t1/col")
        assert exc.value.locator == "X.yaml/sheet/t1/col"

    def test_unknown_scale_is_error(self):
        with pytest.raises(DisplayMeasureContractError):
            build_measure_spec("ratio", "percent")

    def test_ratio_missing_scale_is_error(self):
        with pytest.raises(DisplayMeasureContractError):
            build_measure_spec("ratio")

    def test_amount_builds(self):
        spec = build_measure_spec("amount")
        assert spec is not None and spec.uses_amount_divisor is True


class TestFrontendParity:
    """同一份枚举在 TS 侧必须逐值、同序存在。"""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        assert _FRONTEND_TYPES.is_file(), f"缺少前端合同文件 {_FRONTEND_TYPES}"
        return _FRONTEND_TYPES.read_text(encoding="utf-8")

    def test_kinds_match(self, source: str):
        assert _ts_string_array(source, "DISPLAY_MEASURE_KINDS") == [
            k.value for k in DisplayMeasureKind
        ]

    def test_scales_match(self, source: str):
        assert _ts_string_array(source, "RATIO_SCALES") == [s.value for s in RatioScale]

    def test_amount_kinds_match(self, source: str):
        assert _ts_string_array(source, "AMOUNT_KINDS") == [k.value for k in AMOUNT_KINDS]

    def test_error_code_match(self, source: str):
        assert f"'{DISPLAY_MEASURE_CONTRACT_INVALID}'" in source
