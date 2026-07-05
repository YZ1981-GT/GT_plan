"""G8 其他权益工具投资 — 业务逻辑（公式验证 / 借贷平衡）."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormulaError:
    row_key: str
    field: str
    message: str
    variance: float


class G8OtherEquityInstrumentsService:
    """G8 服务端校验与取数辅助。"""

    TOLERANCE = 0.01

    @staticmethod
    def parse_num(v: object) -> float:
        if v is None or v == "":
            return 0.0
        if isinstance(v, (int, float)):
            n = float(v)
            return n if n == n else 0.0
        try:
            n = float(str(v).strip())
            return n if n == n else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def calc_adjusted(unadjusted: float, adjustment: float) -> float:
        return float(unadjusted or 0) + float(adjustment or 0)

    @staticmethod
    def calc_debit_balance(opening: float, debit: float, credit: float) -> float:
        return float(opening or 0) + float(debit or 0) - float(credit or 0)

    @staticmethod
    def calc_ending_balance(
        opening_adjusted: float,
        increase: float,
        decrease: float,
        fv_change: float,
    ) -> float:
        return (
            float(opening_adjusted or 0)
            + float(increase or 0)
            - float(decrease or 0)
            + float(fv_change or 0)
        )

    @staticmethod
    def calc_fair_value_diff(audited: float, unadjusted: float) -> float:
        return float(audited or 0) - float(unadjusted or 0)

    @staticmethod
    def is_debit_credit_balanced(debits: list[float], credits: list[float]) -> bool:
        d = sum(float(x or 0) for x in debits)
        c = sum(float(x or 0) for x in credits)
        return abs(d - c) < 0.01

    def validate_adjudication_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("row_key") or row.get("id") or "")
            opening_unadj = self.parse_num(row.get("openingUnadjusted"))
            opening_adj = self.parse_num(row.get("openingAdjustment"))
            opening_audited = self.parse_num(row.get("openingAdjusted"))
            opening_computed = self.calc_adjusted(opening_unadj, opening_adj)
            opening_var = opening_computed - opening_audited
            if opening_audited and abs(opening_var) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "openingAdjusted", "期初审定数公式不平衡", opening_var)
                )

            closing_unadj = self.parse_num(row.get("closingUnadjusted"))
            closing_adj = self.parse_num(row.get("closingAdjustment"))
            closing_audited = self.parse_num(row.get("closingAdjusted"))
            closing_computed = self.calc_adjusted(closing_unadj, closing_adj)
            closing_var = closing_computed - closing_audited
            if closing_audited and abs(closing_var) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "closingAdjusted", "期末审定数公式不平衡", closing_var)
                )
        return errors

    def validate_detail_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("investeeName") or row.get("id") or "")
            opening_bal = self.parse_num(row.get("openingBalance"))
            opening_adj = self.parse_num(row.get("openingAdjustment"))
            opening_audited = self.parse_num(row.get("openingAdjusted"))
            opening_computed = self.calc_adjusted(opening_bal, opening_adj)
            if opening_audited and abs(opening_computed - opening_audited) > self.TOLERANCE:
                errors.append(
                    FormulaError(
                        key,
                        "openingAdjusted",
                        "明细表期初审定数公式不平衡",
                        opening_computed - opening_audited,
                    )
                )

            closing_bal = self.parse_num(row.get("closingBalance"))
            closing_computed = self.calc_ending_balance(
                opening_computed,
                self.parse_num(row.get("increaseAmount")),
                self.parse_num(row.get("decreaseAmount")),
                self.parse_num(row.get("fvChangeAmount")),
            )
            if closing_bal and abs(closing_computed - closing_bal) > self.TOLERANCE:
                errors.append(
                    FormulaError(
                        key,
                        "closingBalance",
                        "明细表期末余额公式不平衡",
                        closing_computed - closing_bal,
                    )
                )

            closing_adj = self.parse_num(row.get("closingAdjustment"))
            closing_audited = self.parse_num(row.get("closingAdjusted"))
            closing_adj_computed = self.calc_adjusted(closing_bal, closing_adj)
            if closing_audited and abs(closing_adj_computed - closing_audited) > self.TOLERANCE:
                errors.append(
                    FormulaError(
                        key,
                        "closingAdjusted",
                        "明细表期末审定数公式不平衡",
                        closing_adj_computed - closing_audited,
                    )
                )
        return errors

    def validate_fair_value_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("investeeName") or row.get("id") or "")
            audited = self.parse_num(row.get("closingAuditedFV"))
            unadjusted = self.parse_num(row.get("closingUnadjustedFV"))
            diff = self.parse_num(row.get("fairValueDiff"))
            computed = self.calc_fair_value_diff(audited, unadjusted)
            if diff and abs(computed - diff) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "fairValueDiff", "公允价值差异公式不平衡", computed - diff)
                )
        return errors

    def validate_adjustment_balance(
        self,
        debits: list[float],
        credits: list[float],
    ) -> list[FormulaError]:
        if self.is_debit_credit_balanced(debits, credits):
            return []
        d = sum(float(x or 0) for x in debits)
        c = sum(float(x or 0) for x in credits)
        return [
            FormulaError("adjustment", "balance", "调整分录借贷不平衡", d - c),
        ]
