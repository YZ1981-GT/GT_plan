"""H10 资产处置损益 — 业务逻辑（公式验证 / 审定↔明细勾稽）."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormulaError:
    row_key: str
    field: str
    message: str
    variance: float


class H10AssetDisposalIncomeService:
    """H10 服务端校验与取数辅助。"""

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
    def calc_audited(unadjusted: float, aje: float, rje: float) -> float:
        return float(unadjusted or 0) + float(aje or 0) + float(rje or 0)

    @staticmethod
    def calc_income_statement_net(credit: float, debit: float) -> float:
        return float(credit or 0) - float(debit or 0)

    @staticmethod
    def calc_disposal_gain_loss(
        income: float, net_value: float, expenses: float, tax: float,
    ) -> float:
        return float(income or 0) - float(net_value or 0) - float(expenses or 0) - float(tax or 0)

    @staticmethod
    def is_debit_credit_balanced(debits: list[float], credits: list[float]) -> bool:
        d = sum(float(x or 0) for x in debits)
        c = sum(float(x or 0) for x in credits)
        return abs(d - c) < 0.01

    def validate_adjudication_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("row_key") or "")
            unadj = self.parse_num(row.get("currentUnadjusted"))
            aje = self.parse_num(row.get("currentAje"))
            rje = self.parse_num(row.get("currentRje"))
            audited = self.parse_num(row.get("currentAudited"))
            computed = self.calc_audited(unadj, aje, rje)
            variance = computed - audited
            if abs(variance) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "currentAudited", "本期审定数公式不平衡（未审+AJE+RJE）", variance)
                )
            prior_unadj = self.parse_num(row.get("priorUnadjusted"))
            prior_aje = self.parse_num(row.get("priorAje"))
            prior_rje = self.parse_num(row.get("priorRje"))
            prior_audited = self.parse_num(row.get("priorAudited"))
            prior_computed = self.calc_audited(prior_unadj, prior_aje, prior_rje)
            prior_var = prior_computed - prior_audited
            if abs(prior_var) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "priorAudited", "上期审定数公式不平衡", prior_var)
                )
        return errors

    def validate_detail_reconciliation(
        self,
        adjudication_rows: list[dict],
        detail_rows: list[dict],
    ) -> list[FormulaError]:
        errors: list[FormulaError] = []
        adj_total = sum(self.parse_num(r.get("currentAudited")) for r in adjudication_rows)
        detail_total = 0.0
        for row in detail_rows:
            if row.get("gainLoss") is not None:
                detail_total += self.parse_num(row.get("gainLoss"))
            else:
                detail_total += self.calc_disposal_gain_loss(
                    self.parse_num(row.get("disposalIncome")),
                    self.parse_num(row.get("netBookValue")),
                    self.parse_num(row.get("disposalExpense")),
                    self.parse_num(row.get("taxAmount")),
                )
        variance = adj_total - detail_total
        if adjudication_rows and detail_rows and abs(variance) > self.TOLERANCE:
            errors.append(
                FormulaError("total", "detailReconciliation", "H10-1与H10-2明细汇总不一致", variance)
            )
        return errors

    def validate_detail_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("id") or row.get("seq") or "")
            computed = self.calc_disposal_gain_loss(
                self.parse_num(row.get("disposalIncome")),
                self.parse_num(row.get("netBookValue")),
                self.parse_num(row.get("disposalExpense")),
                self.parse_num(row.get("taxAmount")),
            )
            actual = self.parse_num(row.get("gainLoss"))
            variance = computed - actual
            if actual and abs(variance) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "gainLoss", "处置损益公式不平衡", variance)
                )
        return errors
