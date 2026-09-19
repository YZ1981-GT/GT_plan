"""G9 其他非流动金融资产 — 业务逻辑（公式验证 / L3调节 / 借贷平衡）."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormulaError:
    row_key: str
    field: str
    message: str
    variance: float


class G9OtherNoncurrentFinancialService:
    """G9 服务端校验与取数辅助。"""

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
    def calc_adjusted(unadjusted: float, aje: float, rje: float) -> float:
        return float(unadjusted or 0) + float(aje or 0) + float(rje or 0)

    @staticmethod
    def calc_l3_reconciliation(
        opening: float,
        purchase: float,
        disposal: float,
        transfer_in: float,
        transfer_out: float,
        fv_pl: float,
        fv_oci: float,
        interest: float,
        impairment: float,
        other: float,
    ) -> float:
        return (
            float(opening or 0)
            + float(purchase or 0)
            - float(disposal or 0)
            + float(transfer_in or 0)
            - float(transfer_out or 0)
            + float(fv_pl or 0)
            + float(fv_oci or 0)
            + float(interest or 0)
            - float(impairment or 0)
            + float(other or 0)
        )

    @staticmethod
    def is_debit_credit_balanced(debits: list[float], credits: list[float]) -> bool:
        d = sum(float(x or 0) for x in debits)
        c = sum(float(x or 0) for x in credits)
        return abs(d - c) < 0.01

    def validate_adjudication_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("row_key") or "")
            opening_unadj = self.parse_num(row.get("openingUnadjusted"))
            opening_aje = self.parse_num(row.get("openingAJE"))
            opening_rje = self.parse_num(row.get("openingRJE"))
            opening_audited = self.parse_num(row.get("openingAdjusted"))
            opening_computed = self.calc_adjusted(opening_unadj, opening_aje, opening_rje)
            opening_var = opening_computed - opening_audited
            if opening_audited and abs(opening_var) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "openingAdjusted", "期初审定数公式不平衡", opening_var)
                )

            closing_unadj = self.parse_num(row.get("closingUnadjusted"))
            closing_aje = self.parse_num(row.get("closingAJE"))
            closing_rje = self.parse_num(row.get("closingRJE"))
            closing_audited = self.parse_num(row.get("closingAdjusted"))
            closing_computed = self.calc_adjusted(closing_unadj, closing_aje, closing_rje)
            closing_var = closing_computed - closing_audited
            if closing_audited and abs(closing_var) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "closingAdjusted", "期末审定数公式不平衡", closing_var)
                )
        return errors

    def validate_l3_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("assetName") or row.get("rowId") or "")
            computed = self.calc_l3_reconciliation(
                self.parse_num(row.get("openingFairValue")),
                self.parse_num(row.get("purchaseAmount")),
                self.parse_num(row.get("disposalAmount")),
                self.parse_num(row.get("transferIn")),
                self.parse_num(row.get("transferOut")),
                self.parse_num(row.get("fvChangePL")),
                self.parse_num(row.get("fvChangeOCI")),
                self.parse_num(row.get("interestIncome")),
                self.parse_num(row.get("impairmentLoss")),
                self.parse_num(row.get("otherChanges")),
            )
            closing = self.parse_num(row.get("closingFairValue"))
            variance = computed - closing
            if closing and abs(variance) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "closingFairValue", "L3调节表期末公式不平衡", variance)
                )
            reported = self.parse_num(row.get("reportedClosing"))
            if reported and abs(computed - reported) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "variance", "L3调节表与企业报告差异", computed - reported)
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
