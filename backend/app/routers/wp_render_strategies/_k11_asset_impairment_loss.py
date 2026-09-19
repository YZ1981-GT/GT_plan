"""K11 资产减值损失 — 专属渲染策略.

componentType: k11-asset-impairment-loss

科目定位走报表映射规则链路（共享件 `four_table/report_line_accounts.py` +
声明真源 `four_table/k_cycle_specs.py`）::

    报表行 IS-017（上市）/ IS-038（国企）「资产减值损失（损失以"−"号填列）」

🔴 **两版 `formula` 均为 `None`**（DB 实证）→ `resolved_from` 恒为 `fallback`，
兜底码 `6701`。兜底依据是 `account_chart` 实证::

    6701  资产减值损失   ← K11
    6702  信用减值损失   ← **G14**，不是 K11

即 `6701` / `6702` 是两个不同科目、属两个不同循环。历史公式预设里 K12 块写
`6701`、K13 块写 `6702`（整块贴错标签，本 spec 的 Wave 5 修）。

🔴 **已修正：原实现的「净发生额 = 借方 − 贷方」在全年账上恒为 0**
（成因与逐行实证见 `four_table/pl_occurrence.py` 模块 docstring）。
权威口径 = `trial_balance`，兜底取 `tb_balance.debit_amount`（借方科目）。

**资产减值损失的取数特点**：它是各资产循环减值测试结果的汇总
（F2 存货跌价 / H1 固定资产减值 / I1 无形资产减值 / I3 商誉减值），
K11-2 明细表的行按来源循环列示；商誉减值**不得转回**（CAS8）。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 3.1~3.4, 1.1, 1.2, 2.1~2.3 / Property 5, 6, 7
"""

from __future__ import annotations

from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
from app.services.four_table.pl_render import render_pl_cycle

from ._context import RenderContext

K11_SPEC = K_CYCLE_SPECS["K11"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测）。国企侧是「国企」。
K11_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司）"
K11_DISCLOSURE_SHEET_SOE = "附注披露信息（国企）"

K11_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k11-asset-impairment-loss"},
    {"sheet_name": "实质性程序表 K11A", "component_type": "k11-asset-impairment-loss"},
    {"sheet_name": "审定表K11-1", "component_type": "k11-asset-impairment-loss"},
    {
        "sheet_name": K11_DISCLOSURE_SHEET_LISTED,
        "component_type": "k11-asset-impairment-loss",
    },
    {
        "sheet_name": K11_DISCLOSURE_SHEET_SOE,
        "component_type": "k11-asset-impairment-loss",
    },
    {"sheet_name": "明细表K11-2", "component_type": "k11-asset-impairment-loss"},
    {"sheet_name": "调整分录汇总K11-3", "component_type": "k11-asset-impairment-loss"},
]

K11_META = {
    "sheet_count": len(K11_SHEETS),
    "wp_code": "K11",
    "special_rules": {
        "income_statement": True,
        "account_direction": "debit",
        "net_formula": "trial_balance 本期发生额（权威）/ tb_balance 借方发生额（兜底）",
        "source_table": "trial_balance + tb_balance 叶子",
        "impairment_summary": True,
        "source_wps": ["F2", "H1", "I1", "I3"],
        "goodwill_no_reversal": True,
        # 🔴 与 G14 信用减值损失（6702）是两个科目，不要混
        "vs_credit_impairment": "6702(G14)",
    },
}


async def render(ctx: RenderContext) -> dict | None:
    """K11 资产减值损失渲染策略：损益类取本期发生额（借方科目）+ 取数溯源."""
    return await render_pl_cycle(
        ctx,
        K11_SPEC,
        component_type="k11-asset-impairment-loss",
        sheets=K11_SHEETS,
        meta=K11_META,
    )
