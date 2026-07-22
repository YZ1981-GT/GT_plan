"""G10 交易性金融负债 — 业务逻辑（公式验证 / L3调节 / 借贷平衡）."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormulaError:
    row_key: str
    field: str
    message: str
    variance: float


class G10TradingFinancialLiabilitiesService:
    """G10 服务端校验与取数辅助。"""

    TOLERANCE = 0.01

    @staticmethod
    def parse_num(v: object) -> float:
        if v is None or v == "":
            return 0.0
        if isinstance(v, (int, float)):
            n = float(v)
            return n if n == n else 0.0  # noqa: PLR0124 — NaN check
        try:
            n = float(str(v).strip())
            return n if n == n else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def calc_credit_balance(opening: float, credit: float, debit: float) -> float:
        return float(opening or 0) + float(credit or 0) - float(debit or 0)

    @staticmethod
    def calc_adjusted(unadjusted: float, adjustment: float) -> float:
        return float(unadjusted or 0) + float(adjustment or 0)

    @staticmethod
    def calc_l3_reconciliation(
        opening: float,
        current_new: float,
        current_terminated: float,
        transfer_in: float,
        transfer_out: float,
        fv_change: float,
        interest: float,
        other: float,
    ) -> float:
        return (
            float(opening or 0)
            + float(current_new or 0)
            - float(current_terminated or 0)
            + float(transfer_in or 0)
            - float(transfer_out or 0)
            + float(fv_change or 0)
            + float(interest or 0)
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
            opening_adj = self.parse_num(row.get("openingAdjustment"))
            opening_audited = self.parse_num(row.get("openingAdjusted"))
            opening_computed = self.calc_adjusted(opening_unadj, opening_adj)
            opening_var = opening_computed - opening_audited
            if opening_audited and abs(opening_var) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "openingAdjusted", "期初审定数公式不平衡", opening_var)
                )

            period_credit = self.parse_num(row.get("periodCredit"))
            period_debit = self.parse_num(row.get("periodDebit"))
            closing_unadj = self.parse_num(row.get("closingUnadjusted"))
            if period_credit or period_debit:
                closing_computed = self.calc_credit_balance(opening_computed, period_credit, period_debit)
            else:
                closing_computed = closing_unadj
            closing_var = closing_computed - closing_unadj
            if (period_credit or period_debit) and abs(closing_var) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "closingUnadjusted", "期末未审贷方公式不平衡", closing_var)
                )

            closing_adj_field = self.parse_num(row.get("closingAdjustment"))
            closing_audited = self.parse_num(row.get("closingAdjusted"))
            closing_adj_computed = self.calc_adjusted(closing_computed, closing_adj_field)
            audited_var = closing_adj_computed - closing_audited
            if closing_audited and abs(audited_var) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "closingAdjusted", "期末审定数公式不平衡", audited_var)
                )
        return errors

    def validate_three_part_rows(self, rows: list[dict]) -> list[FormulaError]:
        """(三)账面余额 = (一)初始金额 + (二)累计公允价值变动"""
        errors: list[FormulaError] = []
        for row in rows:
            suffix = str(row.get("suffix") or "")
            for field, init_key, fv_key, book_key in (
                ("openingAdjusted", "initOpening", "fvOpening", "bookOpening"),
                ("closingAdjusted", "initClosing", "fvClosing", "bookClosing"),
            ):
                init_v = self.parse_num(row.get(init_key))
                fv_v = self.parse_num(row.get(fv_key))
                book_v = self.parse_num(row.get(book_key))
                if abs(init_v) < self.TOLERANCE and abs(fv_v) < self.TOLERANCE and abs(book_v) < self.TOLERANCE:
                    continue
                expected = init_v + fv_v
                variance = expected - book_v
                if abs(variance) > self.TOLERANCE:
                    errors.append(
                        FormulaError(
                            f"book_{suffix}",
                            field,
                            f"(三)应等于(一)+(二)（{field}）",
                            variance,
                        )
                    )
        return errors

    def validate_l3_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("liabilityName") or row.get("id") or "")
            opening = self.parse_num(row.get("openingBalance"))
            computed = self.calc_l3_reconciliation(
                opening,
                self.parse_num(row.get("currentNew")),
                self.parse_num(row.get("currentTerminated")),
                self.parse_num(row.get("transferIntoL3")),
                self.parse_num(row.get("transferOutOfL3")),
                self.parse_num(row.get("fairValueChange")),
                self.parse_num(row.get("interestExpense")),
                self.parse_num(row.get("otherChanges")),
            )
            closing = self.parse_num(row.get("closingBalance"))
            variance = computed - closing
            if closing and abs(variance) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "closingBalance", "L3调节表期末公式不平衡", variance)
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
