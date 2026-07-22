"""G14 信用减值损失 — 业务逻辑（公式验证 / TB / 滚动校验）."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RollForwardError:
    row_key: str
    message: str
    variance: float


class G14CreditImpairmentLossService:
    """G14 服务端校验与取数辅助。

    对齐致同 xlsx 明细表G14-2：
    - 计入损益 = 计提 − 转回（转回正数）
    - 期末 = 期初 + 计提 − 转回 − 转销 + 其他变动
    """

    TOLERANCE = 0.01

    @staticmethod
    def calc_adjusted(unadjusted: float, adjustment: float) -> float:
        return float(unadjusted or 0) + float(adjustment or 0)

    @staticmethod
    def calc_profit_loss(provision: float, reversal: float) -> float:
        """计入损益 = 计提 − 转回（转回按正数录入）。"""
        return float(provision or 0) - float(reversal or 0)

    @staticmethod
    def calc_roll_forward(
        opening: float,
        provision: float,
        reversal: float,
        writeoff: float,
        other_movement: float = 0,
    ) -> float:
        """期末 = 期初 + 计提 − 转回 − 转销 + 其他变动。"""
        return (
            float(opening or 0)
            + float(provision or 0)
            - float(reversal or 0)
            - float(writeoff or 0)
            + float(other_movement or 0)
        )

    @staticmethod
    def migrate_reversal_to_positive(reversal: float) -> float:
        """旧版带符号负数转回 → 正数口径。"""
        n = float(reversal or 0)
        return abs(n) if n < 0 else n

    def validate_roll_forward_rows(self, rows: list[dict]) -> list[RollForwardError]:
        errors: list[RollForwardError] = []
        for row in rows:
            opening = float(row.get("openingProvision") or 0)
            provision = float(row.get("currentProvision") or 0)
            reversal = self.migrate_reversal_to_positive(row.get("currentReversal") or 0)
            writeoff = float(row.get("currentWriteoff") or 0)
            other = float(row.get("otherMovement") or 0)
            closing = float(row.get("closingProvision") or 0)
            computed = self.calc_roll_forward(opening, provision, reversal, writeoff, other)
            variance = computed - closing
            if abs(variance) > self.TOLERANCE:
                errors.append(
                    RollForwardError(
                        row_key=str(row.get("rowKey") or ""),
                        message="坏账准备滚动不平衡",
                        variance=variance,
                    )
                )
        return errors
