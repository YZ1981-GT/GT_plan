"""G12 净敞口套期收益 — 业务逻辑（公式验证 / FV勾稽 / 套期无效部分）."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class FvReconcileError:
    row_id: str
    side: str
    message: str
    variance: float


@dataclass
class HedgeRowError:
    row_id: str
    message: str
    variance: float


class G12NetHedgeGainsService:
    """G12 服务端校验与取数辅助。"""

    TOLERANCE = 0.01

    @staticmethod
    def parse_num(v: object) -> float:
        if v is None:
            return 0.0
        if isinstance(v, str) and v.strip() == "":
            return 0.0
        if isinstance(v, (int, float)):
            n = float(v)
            return 0.0 if not math.isfinite(n) else n
        try:
            n = float(v)  # type: ignore[arg-type]
            return 0.0 if not math.isfinite(n) else n
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def calc_adjusted(unadjusted: float, adjustment: float) -> float:
        return float(unadjusted or 0) + float(adjustment or 0)

    @staticmethod
    def calc_fv_change(opening: float, closing: float) -> float:
        return float(closing or 0) - float(opening or 0)

    @staticmethod
    def calc_hedge_ineffectiveness(instrument_change: float, item_change: float) -> float:
        return abs(float(instrument_change or 0) - float(item_change or 0))

    @staticmethod
    def calc_change_rate(prior: float, current: float) -> float | None:
        if float(prior or 0) == 0:
            return None
        return (float(current or 0) - float(prior or 0)) / abs(float(prior))

    @staticmethod
    def is_debit_credit_balanced(debits: list[float], credits: list[float]) -> bool:
        d = sum(float(x or 0) for x in debits)
        c = sum(float(x or 0) for x in credits)
        return abs(d - c) < 0.01

    def validate_fv_reconciliation(self, rows: list[dict]) -> list[FvReconcileError]:
        errors: list[FvReconcileError] = []
        for row in rows:
            row_id = str(row.get("rowId") or row.get("hedgeRelationId") or row.get("id") or "")

            inst_open = float(row.get("instrumentOpeningFV") or 0)
            inst_close = float(row.get("instrumentClosingFV") or 0)
            inst_stored = float(row.get("instrumentFVChange") or 0)
            inst_computed = self.calc_fv_change(inst_open, inst_close)
            inst_var = inst_computed - inst_stored
            if abs(inst_var) > self.TOLERANCE:
                errors.append(
                    FvReconcileError(
                        row_id=row_id,
                        side="instrument",
                        message="套期工具FV变动与期末-期初不一致",
                        variance=inst_var,
                    )
                )

            item_open = float(row.get("itemOpeningFV") or 0)
            item_close = float(row.get("itemClosingFV") or 0)
            item_stored = float(row.get("itemFVChange") or 0)
            item_computed = self.calc_fv_change(item_open, item_close)
            item_var = item_computed - item_stored
            if abs(item_var) > self.TOLERANCE:
                errors.append(
                    FvReconcileError(
                        row_id=row_id,
                        side="item",
                        message="被套期项目FV变动与期末-期初不一致",
                        variance=item_var,
                    )
                )
        return errors

    def validate_hedge_rows(self, rows: list[dict]) -> list[HedgeRowError]:
        errors: list[HedgeRowError] = []
        for row in rows:
            instrument = float(row.get("instrumentFVChange") or 0)
            item = float(row.get("itemFVChange") or 0)
            stored = float(row.get("ineffectiveness") or 0)
            computed = self.calc_hedge_ineffectiveness(instrument, item)
            variance = computed - stored
            if abs(variance) > self.TOLERANCE:
                errors.append(
                    HedgeRowError(
                        row_id=str(row.get("rowId") or row.get("hedgeRelationId") or row.get("id") or ""),
                        message="套期无效部分与绝对差不一致",
                        variance=variance,
                    )
                )
        return errors
