"""G14 信用减值损失 — 业务逻辑（公式验证 / TB / 滚动校验）."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RollForwardError:
    row_key: str
    message: str
    variance: float


class G14CreditImpairmentLossService:
    """G14 服务端校验与取数辅助。"""

    TOLERANCE = 0.01

    @staticmethod
    def calc_adjusted(unadjusted: float, adjustment: float) -> float:
        return float(unadjusted or 0) + float(adjustment or 0)

    @staticmethod
    def calc_profit_loss(provision: float, reversal: float) -> float:
        return float(provision or 0) - float(reversal or 0)

    @staticmethod
    def calc_roll_forward(
        opening: float, provision: float, reversal_signed: float, writeoff: float
    ) -> float:
        """转回按带符号录入（负数表示转回减少准备）。"""
        return (
            float(opening or 0)
            + float(provision or 0)
            + float(reversal_signed or 0)
            - float(writeoff or 0)
        )

    def validate_roll_forward_rows(self, rows: list[dict]) -> list[RollForwardError]:
        errors: list[RollForwardError] = []
        for row in rows:
            opening = float(row.get("openingProvision") or 0)
            provision = float(row.get("currentProvision") or 0)
            reversal = float(row.get("currentReversal") or 0)
            writeoff = float(row.get("currentWriteoff") or 0)
            closing = float(row.get("closingProvision") or 0)
            computed = self.calc_roll_forward(opening, provision, reversal, writeoff)
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
