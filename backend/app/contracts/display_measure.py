"""跨层度量合同（design §4.2 / §17 G1、G4）。

七类 measure kind 是后端、API、前端与 Word 导出路径的唯一语义来源：
只有 ``amount`` 允许使用金额单位除数，其余 kind 的 divisor 恒为 1。

``ratio`` 必须同时携带 ``ratio_scale``（``fraction`` 表示 0.2 = 20%，
``percent_points`` 表示 20 = 20%）；其他 kind 携带 ratio_scale 即为配置错误。
二者都不得使用金额除数（design §17 G4）。

前端对应定义在 ``audit-platform/frontend/src/types/displayMeasure.ts``，
由 ``backend/tests/test_display_measure_contract.py`` 逐值对拍。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "DisplayMeasureKind",
    "RatioScale",
    "DisplayMeasureSpec",
    "DisplayMeasureContractError",
    "DISPLAY_MEASURE_CONTRACT_INVALID",
    "AMOUNT_KINDS",
    "NON_AMOUNT_KINDS",
    "build_measure_spec",
]

# 机器码：核心列语义未登记 / 自相矛盾时统一使用
DISPLAY_MEASURE_CONTRACT_INVALID = "DISPLAY_MEASURE_CONTRACT_INVALID"


class DisplayMeasureKind(str, Enum):
    """封闭的七类度量语义。顺序即前后端对拍的规范顺序。"""

    amount = "amount"
    quantity = "quantity"
    count = "count"
    ratio = "ratio"
    exchange_rate = "exchange_rate"
    unit_price = "unit_price"
    text = "text"


class RatioScale(str, Enum):
    """比例尺度。``fraction`` 原值 0.2、``percent_points`` 原值 20 都显示 20.00%。"""

    fraction = "fraction"
    percent_points = "percent_points"


#: 只有这一类能消费金额单位除数
AMOUNT_KINDS: frozenset[DisplayMeasureKind] = frozenset({DisplayMeasureKind.amount})
#: 其余 kind 的 divisor 恒为 1
NON_AMOUNT_KINDS: frozenset[DisplayMeasureKind] = frozenset(DisplayMeasureKind) - AMOUNT_KINDS


class DisplayMeasureContractError(ValueError):
    """kind/scale 组合非法。code 固定为 DISPLAY_MEASURE_CONTRACT_INVALID。"""

    code = DISPLAY_MEASURE_CONTRACT_INVALID

    def __init__(self, message: str, *, locator: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.locator = locator


@dataclass(frozen=True, slots=True)
class DisplayMeasureSpec:
    """一列（或一个输出区域）的度量语义。

    不变量：``kind=ratio`` 时 ``ratio_scale`` 必填；其他 kind 必须为 None。

    刻意用 frozen dataclass 而不是 pydantic BaseModel：pydantic v2 会把 validator /
    ``model_post_init`` 里抛出的 ValueError 包装成 ValidationError，调用方就接不到带
    ``DISPLAY_MEASURE_CONTRACT_INVALID`` 机器码的 typed 异常，fail closed 的错误码会被吞掉。
    未知关键字由 dataclass 自身以 TypeError 拒绝（等价于 extra='forbid'）。
    """

    kind: DisplayMeasureKind
    ratio_scale: RatioScale | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DisplayMeasureKind):
            raise DisplayMeasureContractError(f"未知 measure_kind: {self.kind!r}")
        if self.ratio_scale is not None and not isinstance(self.ratio_scale, RatioScale):
            raise DisplayMeasureContractError(f"未知 ratio_scale: {self.ratio_scale!r}")
        if self.kind is DisplayMeasureKind.ratio:
            if self.ratio_scale is None:
                raise DisplayMeasureContractError(
                    "kind=ratio 必须同时声明 ratio_scale（fraction 或 percent_points）"
                )
        elif self.ratio_scale is not None:
            raise DisplayMeasureContractError(
                f"kind={self.kind.value} 不允许携带 ratio_scale"
            )

    @property
    def uses_amount_divisor(self) -> bool:
        """只有 amount 消费金额单位除数。"""
        return self.kind in AMOUNT_KINDS

    def as_wire(self) -> dict[str, Any]:
        return {
            "measure_kind": self.kind.value,
            "ratio_scale": self.ratio_scale.value if self.ratio_scale else None,
        }


def build_measure_spec(
    kind: str | DisplayMeasureKind | None,
    ratio_scale: str | RatioScale | None = None,
    *,
    locator: str | None = None,
) -> DisplayMeasureSpec | None:
    """宽入口：未登记（None/空）返回 None，非法组合抛 DisplayMeasureContractError。

    返回 None 表示「未登记」，由调用方按未登记分支处理（divisor=1、不加 %）。
    """
    if kind is None or (isinstance(kind, str) and not kind.strip()):
        if ratio_scale is not None:
            raise DisplayMeasureContractError(
                "未声明 measure_kind 时不允许携带 ratio_scale", locator=locator
            )
        return None
    try:
        parsed_kind = DisplayMeasureKind(kind)
    except ValueError as exc:
        raise DisplayMeasureContractError(
            f"未知 measure_kind: {kind!r}", locator=locator
        ) from exc
    parsed_scale: RatioScale | None = None
    if ratio_scale is not None and not (isinstance(ratio_scale, str) and not ratio_scale.strip()):
        try:
            parsed_scale = RatioScale(ratio_scale)
        except ValueError as exc:
            raise DisplayMeasureContractError(
                f"未知 ratio_scale: {ratio_scale!r}", locator=locator
            ) from exc
    try:
        return DisplayMeasureSpec(kind=parsed_kind, ratio_scale=parsed_scale)
    except DisplayMeasureContractError as exc:
        raise DisplayMeasureContractError(exc.message, locator=locator) from exc
