"""K9 管理费用 — 专属渲染策略.

componentType: k9-admin-expenses

科目定位走报表映射规则链路（共享件 `four_table/report_line_accounts.py` +
声明真源 `four_table/k_cycle_specs.py`）::

    报表行 IS-005（上市）/ IS-023（国企）「管理费用」
      四准则一致：TB('6602','本期发生额')

🔴 **已修正：原实现的「净发生额 = 借方 − 贷方」在全年账上恒为 0**
（成因与逐行实证见 `_k8_selling_expenses.py` 与
`four_table/pl_occurrence.py` 的模块 docstring）。
权威口径 = `trial_balance`（实证 `6602 = 72,957,201.11`），
兜底取 `tb_balance.debit_amount`（借方科目）。

同时修掉父子双计与缺点号边界的自造 `_is_leaf`。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 3.1~3.4, 1.1, 2.1~2.3 / Property 5, 6, 7
"""

from __future__ import annotations

from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
from app.services.four_table.pl_render import render_pl_cycle

from ._context import RenderContext

K9_SPEC = K_CYCLE_SPECS["K9"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测）。国企侧是「国企」。
K9_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司）"
K9_DISCLOSURE_SHEET_SOE = "附注披露信息（国企）"

K9_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k9-admin-expenses"},
    {"sheet_name": "实质性程序表K9A", "component_type": "k9-admin-expenses"},
    {"sheet_name": "审定表K9-1", "component_type": "k9-admin-expenses"},
    {"sheet_name": K9_DISCLOSURE_SHEET_LISTED, "component_type": "k9-admin-expenses"},
    {"sheet_name": K9_DISCLOSURE_SHEET_SOE, "component_type": "k9-admin-expenses"},
    {"sheet_name": "明细表K9-2", "component_type": "k9-admin-expenses"},
    {"sheet_name": "调整分录汇总K9-3", "component_type": "k9-admin-expenses"},
    {"sheet_name": "实质性分析K9-4", "component_type": "k9-admin-expenses"},
    {"sheet_name": "合同检查表K9-5", "component_type": "k9-admin-expenses"},
    {
        "sheet_name": "截止性测试(从记账凭证至原始凭证）K9-6",
        "component_type": "k9-admin-expenses",
    },
    {
        "sheet_name": "截止性测试（从原始凭证至记账凭证）K9-7",
        "component_type": "k9-admin-expenses",
    },
    {"sheet_name": "管理费用检查表K9-8", "component_type": "k9-admin-expenses"},
]

K9_META = {
    "sheet_count": len(K9_SHEETS),
    "wp_code": "K9",
    "special_rules": {
        "income_statement": True,
        "account_direction": "debit",
        "net_formula": "trial_balance 本期发生额（权威）/ tb_balance 借方发生额（兜底）",
        "source_table": "trial_balance + tb_balance 叶子",
        "substantive_analysis": True,
        "cutoff_test_bidirectional": True,
        "contract_check": True,
    },
}


async def render(ctx: RenderContext) -> dict | None:
    """K9 管理费用渲染策略：损益类取本期发生额（借方科目）+ 取数溯源."""
    return await render_pl_cycle(
        ctx,
        K9_SPEC,
        component_type="k9-admin-expenses",
        sheets=K9_SHEETS,
        meta=K9_META,
    )
