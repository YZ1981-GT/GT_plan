"""G7 长期股权投资(权益法组) — 公式引擎服务（Python端 9纯函数 + parseNum）.

与前端 useG7EquityMethodFormulaEngine.ts 完全对应，用于后端PBT验证。

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

所有函数使用 round(..., 2) 保留2位小数。

Spec: .kiro/specs/g7-long-term-equity-method/
Requirements: 7.1
"""

from __future__ import annotations

import math


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
