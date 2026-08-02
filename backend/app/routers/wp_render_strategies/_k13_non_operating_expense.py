"""K13 营业外支出 — 专属渲染策略.

componentType: k13-non-operating-expense

科目定位走报表映射规则链路（共享件 `four_table/report_line_accounts.py` +
声明真源 `four_table/k_cycle_specs.py`）::

    报表行 IS-021（上市）/ IS-043（国企）「减：营业外支出」
      四准则一致：TB('6711','本期发生额')

🔴 **已修正：原实现的「净发生额 = 借方 − 贷方」在全年账上恒为 0**
（成因与逐行实证见 `four_table/pl_occurrence.py` 模块 docstring）。
权威口径 = `trial_balance`，兜底取 `tb_balance.debit_amount`（借方科目）。

**分类边界**：与日常活动**无关**的损失计入营业外支出（6711）——
非流动资产毁损报废损失、公益性捐赠支出、非常损失、罚款滞纳金等；
与日常活动相关的损失计入相应费用科目。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 3.1~3.4, 1.1, 2.1~2.3 / Property 5, 6, 7
"""

from __future__ import annotations

from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
from app.services.four_table.pl_render import render_pl_cycle

from ._context import RenderContext

K13_SPEC = K_CYCLE_SPECS["K13"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测）。国企侧是「国企」。
K13_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司）"
K13_DISCLOSURE_SHEET_SOE = "附注披露信息（国企）"

K13_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k13-non-operating-expense"},
    {"sheet_name": "实质性程序表K13A", "component_type": "k13-non-operating-expense"},
    {"sheet_name": "审定表K13-1", "component_type": "k13-non-operating-expense"},
    {
        "sheet_name": K13_DISCLOSURE_SHEET_LISTED,
        "component_type": "k13-non-operating-expense",
    },
    {
        "sheet_name": K13_DISCLOSURE_SHEET_SOE,
        "component_type": "k13-non-operating-expense",
    },
    {"sheet_name": "明细表K13-2", "component_type": "k13-non-operating-expense"},
    {"sheet_name": "调整分录汇总K13-3", "component_type": "k13-non-operating-expense"},
    {
        "sheet_name": "营业外支出检查表K13-4",
        "component_type": "k13-non-operating-expense",
    },
]

K13_META = {
    "sheet_count": len(K13_SHEETS),
    "wp_code": "K13",
    "special_rules": {
        "income_statement": True,
        "account_direction": "debit",  # 借方科目！（vs K12 贷方）
        "net_formula": "trial_balance 本期发生额（权威）/ tb_balance 借方发生额（兜底）",
        "source_table": "trial_balance + tb_balance 叶子",
        "non_operating_classification": True,
        "vs_non_operating_income": "6301(K12)",
    },
}


async def render(ctx: RenderContext) -> dict | None:
    """K13 营业外支出渲染策略：损益类取本期发生额（借方科目）+ 取数溯源."""
    return await render_pl_cycle(
        ctx,
        K13_SPEC,
        component_type="k13-non-operating-expense",
        sheets=K13_SHEETS,
        meta=K13_META,
    )
