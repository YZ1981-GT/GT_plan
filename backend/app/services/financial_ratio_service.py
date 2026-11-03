"""财务比率分析服务 — 9 个核心比率（spec citar-report-analysis §2.2）。

取数：按行名定位报表关键行（``report_row_locator``），不写死编码 —— 旧实现的 ``BS-019`` /
``PL-001`` 在现行模板里分别是「其中：原材料」/ 不存在，比率全错。
``mode=audited`` 读已生成的审定报表；``mode=unadjusted`` 读按试算表未审数计算的报表。
周转率与 ROE 的分母用期初期末平均（期初缺失时用期末并写明）。
取不到的分量返回原因，不当 0 计算。

Requirements: 5.1~5.5
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.report_analysis_rows import load_report_rows
from app.services.report_row_locator import SEMANTIC_LABELS, locate

_BS_KEYS = ("current_assets", "inventory", "total_assets", "current_liabilities",
            "total_liabilities", "total_equity", "accounts_receivable")
_IS_KEYS = ("revenue", "cost_of_sales", "net_profit")


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - 非法金额按缺失处理
        return None


class _Figure:
    """一个分量：取值 + 溯源（行编码 / 行名）+ 取不到的原因。"""

    def __init__(self, label: str, amount: Decimal | None, row_code: str | None = None,
                 reason: str = ""):
        self.label = label
        self.amount = amount
        self.row_code = row_code
        self.reason = reason

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "row_code": self.row_code,
                "amount": self.amount, "reason": self.reason}


class FinancialRatioService:
    """财务比率分析"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_ratios(
        self, project_id: UUID, year: int, mode: str = "audited"
    ) -> list[dict[str, Any]]:
        bs = await load_report_rows(self.db, project_id, year, "balance_sheet", mode)
        is_ = await load_report_rows(self.db, project_id, year, "income_statement", mode)
        missing_report = "审定报表未生成" if mode == "audited" else "未审报表无数据"

        def fig(rows, key: str, *, prior: bool = False) -> _Figure:
            label = SEMANTIC_LABELS[key] + ("（期初）" if prior else "")
            if not rows:
                return _Figure(label, None, reason=missing_report)
            row = locate(rows, key)
            if row is None:
                return _Figure(label, None, reason=f"报表里找不到「{SEMANTIC_LABELS[key]}」行")
            amount = _dec(row.get("prior_period_amount" if prior else "current_period_amount"))
            if amount is None:
                return _Figure(label, None, row.get("row_code"), reason="该行没有金额")
            return _Figure(label, amount, row.get("row_code"))

        cur = {k: fig(bs, k) for k in _BS_KEYS}
        opening = {k: fig(bs, k, prior=True) for k in ("total_assets", "accounts_receivable",
                                                       "inventory", "total_equity")}
        pl = {k: fig(is_, k) for k in _IS_KEYS}

        quick = self._combine("速动资产（流动资产合计 − 存货）",
                              cur["current_assets"], cur["inventory"], sign=-1)
        gross = self._combine("毛利（营业收入 − 营业成本）",
                              pl["revenue"], pl["cost_of_sales"], sign=-1)

        return [
            self._ratio("流动比率", cur["current_assets"], cur["current_liabilities"], "倍"),
            self._ratio("速动比率", quick, cur["current_liabilities"], "倍"),
            self._ratio("资产负债率", cur["total_liabilities"], cur["total_assets"], "%", pct=True),
            self._ratio("毛利率", gross, pl["revenue"], "%", pct=True),
            self._ratio("净利率", pl["net_profit"], pl["revenue"], "%", pct=True),
            self._ratio("总资产周转率", pl["revenue"],
                        self._average(cur["total_assets"], opening["total_assets"]), "次"),
            self._ratio("应收账款周转率", pl["revenue"],
                        self._average(cur["accounts_receivable"], opening["accounts_receivable"]), "次"),
            self._ratio("存货周转率", pl["cost_of_sales"],
                        self._average(cur["inventory"], opening["inventory"]), "次"),
            self._ratio("净资产收益率(ROE)", pl["net_profit"],
                        self._average(cur["total_equity"], opening["total_equity"]), "%", pct=True),
        ]

    # ------------------------------------------------------------------
    @staticmethod
    def _combine(label: str, a: _Figure, b: _Figure, *, sign: int) -> _Figure:
        if a.amount is None:
            return _Figure(label, None, reason=f"{a.label}：{a.reason}")
        if b.amount is None:
            return _Figure(label, None, reason=f"{b.label}：{b.reason}")
        return _Figure(label, a.amount + sign * b.amount, f"{a.row_code} {'+' if sign > 0 else '−'} {b.row_code}")

    @staticmethod
    def _average(closing: _Figure, opening: _Figure) -> _Figure:
        base = closing.label
        if closing.amount is None:
            return closing
        if opening.amount is None:
            return _Figure(f"{base}（期初缺失，用期末）", closing.amount, closing.row_code)
        return _Figure(f"平均{base}（期初期末平均）", (closing.amount + opening.amount) / 2,
                       closing.row_code)

    @staticmethod
    def _ratio(name: str, numerator: _Figure | Decimal | None, denominator: _Figure | Decimal | None,
               unit: str, pct: bool = False) -> dict[str, Any]:
        num_f = numerator if isinstance(numerator, _Figure) else _Figure("分子", numerator)
        den_f = denominator if isinstance(denominator, _Figure) else _Figure("分母", denominator)
        result: dict[str, Any] = {
            "name": name, "value": None, "unit": unit, "abnormal": False, "note": "",
            "numerator": num_f.as_dict(), "denominator": den_f.as_dict(),
        }
        if num_f.amount is None:
            result["note"] = f"取不到{num_f.label}：{num_f.reason}"
            return result
        if den_f.amount is None:
            result["note"] = f"取不到{den_f.label}：{den_f.reason}"
            return result
        if den_f.amount == 0:
            result["note"] = "分母为零"
            return result
        value = num_f.amount / den_f.amount * (100 if pct else 1)
        abnormal = ("负债率" in name and value > Decimal("70")) or (
            name == "流动比率" and value < Decimal("1"))
        result.update(value=round(value, 2), abnormal=abnormal)
        return result
