"""G11 投资收益 — 业务逻辑（公式验证 / 审定↔明细勾稽）."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormulaError:
    row_key: str
    field: str
    message: str
    variance: float


class G11InvestmentIncomeService:
    """G11 服务端校验与取数辅助。"""

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
    def calc_adjusted(unadjusted: float, adjustment: float) -> float:
        return float(unadjusted or 0) + float(adjustment or 0)

    @staticmethod
    def calc_change_rate(prior_audited: float, current_audited: float) -> float | None:
        if prior_audited == 0:
            return None
        return (current_audited - prior_audited) / abs(prior_audited)

    @staticmethod
    def calc_average_balance(opening: float, closing: float) -> float:
        return (float(opening or 0) + float(closing or 0)) / 2

    @staticmethod
    def calc_return_rate(income: float, avg_balance: float) -> float | None:
        if avg_balance == 0:
            return None
        return float(income or 0) / avg_balance

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
            adj = self.parse_num(row.get("currentAdjustment"))
            audited = self.parse_num(row.get("currentAudited"))
            computed = self.calc_adjusted(unadj, adj)
            variance = computed - audited
            if abs(variance) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "currentAudited", "本期审定数公式不平衡", variance)
                )
            prior_unadj = self.parse_num(row.get("priorUnadjusted"))
            prior_adj = self.parse_num(row.get("priorAdjustment"))
            prior_audited = self.parse_num(row.get("priorAudited"))
            prior_computed = self.calc_adjusted(prior_unadj, prior_adj)
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
        """G11-1 按项目汇总应与 G11-2 明细按 itemName 汇总一致。"""
        errors: list[FormulaError] = []
        adj_by_item: dict[str, float] = {}
        for row in adjudication_rows:
            label = str(row.get("label") or "").strip()
            if not label:
                continue
            adj_by_item[label] = adj_by_item.get(label, 0.0) + self.parse_num(
                row.get("currentAudited")
            )

        detail_by_item: dict[str, float] = {}
        for row in detail_rows:
            name = str(row.get("itemName") or row.get("item_name") or "").strip()
            if not name:
                continue
            unadj = self.parse_num(row.get("currentUnadjusted"))
            adj = self.parse_num(row.get("currentAdjustment"))
            detail_by_item[name] = detail_by_item.get(name, 0.0) + self.calc_adjusted(unadj, adj)

        all_keys = set(adj_by_item) | set(detail_by_item)
        for key in sorted(all_keys):
            a = adj_by_item.get(key, 0.0)
            d = detail_by_item.get(key, 0.0)
            variance = a - d
            if abs(variance) > self.TOLERANCE and (a != 0 or d != 0):
                errors.append(
                    FormulaError(key, "detailReconciliation", "G11-1与G11-2明细汇总不一致", variance)
                )
        return errors

    def validate_return_rate_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("itemName") or row.get("id") or "")
            opening = self.parse_num(row.get("currentOpening"))
            closing = self.parse_num(row.get("currentClosing"))
            avg = self.parse_num(row.get("currentAvgBalance"))
            computed_avg = self.calc_average_balance(opening, closing)
            variance = computed_avg - avg
            if avg and abs(variance) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "currentAvgBalance", "平均投资余额公式不平衡", variance)
                )
        return errors
