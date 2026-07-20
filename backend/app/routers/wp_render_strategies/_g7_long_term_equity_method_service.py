"""G7 长期股权投资(权益法组) — 公式引擎服务（Python端纯函数 + parseNum）.

与前端 useG7EquityMethodFormulaEngine.ts / G7TabEquityMethodCalc.recalcRow 对齐。

公式链：
  P1: calcInvestmentCost(consideration, directCosts) = consideration + directCosts
  P2: calcShareOfNetAssets(netAssetFV, ratio) = netAssetFV × ratio
  P3: calcGoodwill(initialCost, shareOfNetAssets) = initialCost - shareOfNetAssets
  P4: calcAdjustedNetProfit(r, i, f, p, o) = r - i - f + p + o
  P5: calcEquityShare(value, ratio) = value × ratio
  P6: calcEquityMethodBalance(o, i, oci, eq, d) = o + i + oci + eq - d
  P7: calcUnrealizedProfit(amount, marginRate) = amount × marginRate
  P8: calcEliminationAmount(direction, profit, ratio) = 顺流:profit / 逆流:profit×ratio
  P9: calcImpairmentAmount(bv, ra) = MAX(0, bv - ra)
  P10: calcIncomeDifference(confirmed, equityShare, dividend) = ⑨−⑤＋⑧
  P11: calcLteiBookBalance(cost, pnl, oci, other) = 四段期末合计
  P12: calcNetAssetShareVariance(book, auditedNA, ratio) = R − Q
  P13: calcUnexplainedVariance(S, goodwill, fv, impairment) = S−U−V＋W

所有函数使用 round(..., 2) 保留2位小数。

Spec: .kiro/specs/g7-long-term-equity-method/
Requirements: 7.1
"""

from __future__ import annotations

import math
from typing import Any


class G7LongTermEquityMethodService:
    """G7权益法组公式引擎（纯函数集合，无DB依赖）。"""

    @staticmethod
    def parse_num(v: object) -> float:
        """安全数值转换：None/''/NaN/非数值→0；有效数字→原值。"""
        if v is None:
            return 0.0
        if isinstance(v, str):
            v = v.strip()
            if v == '':
                return 0.0
            try:
                n = float(v)
                return n if math.isfinite(n) else 0.0
            except (ValueError, TypeError):
                return 0.0
        if isinstance(v, (int, float)):
            if isinstance(v, float) and not math.isfinite(v):
                return 0.0
            return float(v)
        try:
            n = float(v)  # type: ignore[arg-type]
            return n if math.isfinite(n) else 0.0
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def calc_investment_cost(consideration: float, direct_costs: float) -> float:
        """P1: 初始投资成本 = 支付对价 + 直接相关费用。"""
        return round(consideration + direct_costs, 2)

    @staticmethod
    def calc_share_of_net_assets(net_asset_fv: float, ratio: float) -> float:
        """P2: 享有可辨认净资产公允价值份额 = 净资产FV × 持股比例。"""
        return round(net_asset_fv * ratio, 2)

    @staticmethod
    def calc_goodwill(initial_cost: float, share_of_net_assets: float) -> float:
        """P3: 商誉/营业外 = 初始投资成本 - 享有份额。"""
        return round(initial_cost - share_of_net_assets, 2)

    @staticmethod
    def calc_adjusted_net_profit(
        reported: float,
        internal_trans: float,
        fv_depreciation: float,
        policy_adj: float,
        other: float,
    ) -> float:
        """P4: 调整后净利润 = 报告净利润 - 内部交易 - FV折旧 + 政策调整 + 其他。"""
        return round(reported - internal_trans - fv_depreciation + policy_adj + other, 2)

    @staticmethod
    def calc_equity_share(value: float, ratio: float) -> float:
        """P5: 持股比例份额 = 值 × 持股比例（通用乘法）。"""
        return round(value * ratio, 2)

    @staticmethod
    def calc_equity_method_balance(
        opening: float,
        income: float,
        oci: float,
        equity_change: float,
        dividend: float,
    ) -> float:
        """P6: 期末权益法余额 = 期初 + 投资收益 + OCI + 其他权益 - 股利。"""
        return round(opening + income + oci + equity_change - dividend, 2)

    @staticmethod
    def calc_unrealized_profit(transaction_amount: float, gross_margin: float) -> float:
        """P7: 未实现利润 = 交易金额 × 毛利率。"""
        return round(transaction_amount * gross_margin, 2)

    @staticmethod
    def calc_elimination_amount(direction: str, unrealized_profit: float, ratio: float) -> float:
        """P8: 应抵销金额 — 顺流(downstream):全额 / 逆流(upstream):×比例。"""
        if direction == 'downstream':
            return round(unrealized_profit, 2)
        return round(unrealized_profit * ratio, 2)

    @staticmethod
    def calc_impairment_amount(book_value: float, recoverable_amount: float) -> float:
        """P9: 减值金额 = MAX(0, 账面价值 - 可收回金额)。"""
        return round(max(0.0, book_value - recoverable_amount), 2)

    @staticmethod
    def calc_income_difference(
        confirmed_income: float,
        equity_share: float,
        dividend: float,
    ) -> float:
        """P10: 投资收益差异⑩ = 账面确认⑨ − 测算⑤ ＋ 已宣告股利⑧。"""
        return round(confirmed_income - equity_share + dividend, 2)

    @staticmethod
    def calc_ltei_book_balance(
        cost_closing: float,
        pnl_adj_closing: float,
        oci_closing: float,
        other_equity_closing: float,
    ) -> float:
        """P11: 长投账面余额 R = 成本期末 + 损益调整期末 + OCI期末 + 其他权益期末。"""
        return round(cost_closing + pnl_adj_closing + oci_closing + other_equity_closing, 2)

    @staticmethod
    def calc_net_asset_share_variance(
        book_balance: float,
        audited_net_assets: float,
        ratio: float,
    ) -> float:
        """P12: 与应享净资产差额 S = R − 经审计净资产×持股比例。"""
        share = round(audited_net_assets * ratio, 2)
        return round(book_balance - share, 2)

    @staticmethod
    def calc_unexplained_variance(
        net_asset_share_variance: float,
        goodwill: float,
        cumulative_fv_adj: float,
        impairment: float,
    ) -> float:
        """P13: 未解释差额⑮ = S − 商誉 − 累计FV调整 ＋ 减值准备。"""
        return round(
            net_asset_share_variance - goodwill - cumulative_fv_adj + impairment,
            2,
        )

    @staticmethod
    def calc_opening_recon_variance(
        cost_opening: float,
        pnl_adj_opening: float,
        oci_bal_opening: float,
        other_eq_bal_opening: float,
        g72_opening_total: float,
    ) -> float:
        """期初勾稽差异P = 四段期初合计 − G7-2审定期初总额。"""
        return round(
            cost_opening + pnl_adj_opening + oci_bal_opening + other_eq_bal_opening - g72_opening_total,
            2,
        )

    @staticmethod
    def calc_closing_recon_variance(
        ltei_book_balance: float,
        g72_closing_total: float,
    ) -> float:
        """期末勾稽差异S = 长投账面余额 − G7-2审定期末总额。"""
        return round(ltei_book_balance - g72_closing_total, 2)

    @classmethod
    def recalculate_g7_14_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        """覆盖 G7-14 公式列（对齐前端 recalcRow）；不信任导入/客户端公式值。"""
        p = cls.parse_num
        reported = p(row.get("reportedNetProfit", row.get("reported_net_profit")))
        internal = p(row.get("internalTransactionAdj", row.get("internal_transaction_adj")))
        fv_dep = p(row.get("fvDepreciationAdj", row.get("fv_depreciation_adj")))
        policy = p(row.get("accountingPolicyAdj", row.get("accounting_policy_adj")))
        other = p(row.get("otherAdj", row.get("other_adj")))
        ratio = p(row.get("investmentRatio", row.get("investment_ratio")))
        oci_change = p(row.get("ociChange", row.get("oci_change")))
        other_eq_change = p(row.get("otherEquityChange", row.get("other_equity_change")))
        confirmed = p(row.get("confirmedIncome", row.get("confirmed_income")))
        confirmed_oci = p(row.get("confirmedOci", row.get("confirmed_oci")))
        confirmed_other = p(row.get("confirmedOtherEquity", row.get("confirmed_other_equity")))
        dividend = p(row.get("dividendDistributed", row.get("dividend_distributed")))
        cost_open = p(row.get("costOpening", row.get("cost_opening")))
        cost_chg = p(row.get("costChange", row.get("cost_change")))
        pnl_open = p(row.get("pnlAdjOpening", row.get("pnl_adj_opening")))
        pnl_chg = p(row.get("pnlAdjChange", row.get("pnl_adj_change")))
        oci_bal_open = p(row.get("ociBalOpening", row.get("oci_bal_opening")))
        other_eq_bal_open = p(row.get("otherEqBalOpening", row.get("other_eq_bal_opening")))
        audited_na = p(row.get("auditedNetAssets", row.get("audited_net_assets")))
        goodwill = p(row.get("goodwill"))
        cum_fv = p(row.get("cumulativeFvAdj", row.get("cumulative_fv_adj")))
        impairment = p(row.get("impairment"))
        opening = p(row.get("openingBalance", row.get("opening_balance")))
        g72_open = p(row.get("g72OpeningTotal", row.get("g72_opening_total")))
        g72_close = p(row.get("g72ClosingTotal", row.get("g72_closing_total")))

        adjusted = cls.calc_adjusted_net_profit(reported, internal, fv_dep, policy, other)
        equity_share = cls.calc_equity_share(adjusted, ratio)
        oci_share = cls.calc_equity_share(oci_change, ratio)
        other_eq_share = cls.calc_equity_share(other_eq_change, ratio)
        income_diff = cls.calc_income_difference(confirmed, equity_share, dividend)
        oci_diff = round(confirmed_oci - oci_share, 2)
        other_eq_diff = round(confirmed_other - other_eq_share, 2)

        cost_closing = round(cost_open + cost_chg, 2)
        pnl_closing = round(pnl_open + pnl_chg, 2)
        oci_bal_change = oci_share
        other_eq_bal_change = other_eq_share
        oci_bal_closing = round(oci_bal_open + oci_bal_change, 2)
        other_eq_bal_closing = round(other_eq_bal_open + other_eq_bal_change, 2)

        ltei = cls.calc_ltei_book_balance(
            cost_closing, pnl_closing, oci_bal_closing, other_eq_bal_closing,
        )
        share_of_na = cls.calc_equity_share(audited_na, ratio)
        na_var = cls.calc_net_asset_share_variance(ltei, audited_na, ratio)
        unexplained = cls.calc_unexplained_variance(na_var, goodwill, cum_fv, impairment)
        opening_recon = cls.calc_opening_recon_variance(
            cost_open, pnl_open, oci_bal_open, other_eq_bal_open, g72_open,
        )
        closing_recon = cls.calc_closing_recon_variance(ltei, g72_close)
        closing = cls.calc_equity_method_balance(
            opening, equity_share, oci_share, other_eq_share, dividend,
        )

        row["adjustedNetProfit"] = adjusted
        row["equityShare"] = equity_share
        row["ociShare"] = oci_share
        row["otherEquityShare"] = other_eq_share
        row["incomeDifference"] = income_diff
        row["ociDifference"] = oci_diff
        row["otherEquityDifference"] = other_eq_diff
        row["costClosing"] = cost_closing
        row["pnlAdjClosing"] = pnl_closing
        row["ociBalChange"] = oci_bal_change
        row["otherEqBalChange"] = other_eq_bal_change
        row["ociBalClosing"] = oci_bal_closing
        row["otherEqBalClosing"] = other_eq_bal_closing
        row["lteiBookBalance"] = ltei
        row["shareOfAuditedNetAssets"] = share_of_na
        row["netAssetShareVariance"] = na_var
        row["unexplainedVariance"] = unexplained
        row["openingReconVariance"] = opening_recon
        row["closingReconVariance"] = closing_recon
        row["closingBalance"] = closing
        return row
