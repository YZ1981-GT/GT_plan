"""G13 公允价值变动收益 — 业务逻辑（公式验证 / FV勾稽）."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FvReconcileError:
    row_id: str
    message: str
    variance: float


class G13FairValueChangesService:
    """G13 服务端校验与取数辅助。"""

    TOLERANCE = 0.01

    @staticmethod
    def calc_adjusted(unadjusted: float, adjustment: float) -> float:
        return float(unadjusted or 0) + float(adjustment or 0)

    @staticmethod
    def calc_fv_change(opening: float, closing: float) -> float:
        return float(closing or 0) - float(opening or 0)

    def validate_fv_reconciliation(self, rows: list[dict]) -> list[FvReconcileError]:
        errors: list[FvReconcileError] = []
        for row in rows:
            opening = float(row.get("openingFairValue") or 0)
            closing = float(row.get("closingFairValue") or 0)
            unadjusted = float(row.get("currentUnadjusted") or 0)
            adjustment = float(row.get("adjustment") or 0)
            fv_change = self.calc_fv_change(opening, closing)
            audited = self.calc_adjusted(unadjusted, adjustment)
            variance = fv_change - audited
            if abs(variance) > self.TOLERANCE:
                errors.append(
                    FvReconcileError(
                        row_id=str(row.get("rowId") or ""),
                        message="FV变动与审定数不一致",
                        variance=variance,
                    )
                )
        return errors
