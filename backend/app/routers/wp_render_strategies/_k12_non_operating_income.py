"""K12 营业外收入 — 专属渲染策略.

componentType: k12-non-operating-income

科目定位走报表映射规则链路（共享件 `four_table/report_line_accounts.py` +
声明真源 `four_table/k_cycle_specs.py`）::

    报表行 IS-020（上市）/ IS-041（国企）「加：营业外收入」
      四准则一致：TB('6301','本期发生额')

🔴 **已修正：原实现的「净发生额 = 贷方 − 借方」在全年账上恒为 0**
（收益类是反向写法，同样恒零；成因与逐行实证见
`four_table/pl_occurrence.py` 模块 docstring）。
权威口径 = `trial_balance`，兜底取 `tb_balance.credit_amount`（贷方科目）。

🔴 **符号处理**：`trial_balance` 中收益类符号在项目间不统一 —— 实证 `6301`
在项目 `005a6f2d` 为 `-305,414.30`、在 `37814426` 为 `+0.01`
（「借正贷负」与「正数口径」两种约定并存）。裁决依据取自报表语义：
`IS-020 加：营业外收入` 前置运算符是 `+`，即报表期望正数贡献
→ 按 `normalize_for_report` 取绝对值，`raw_sign` 留证。

**分类边界**：与日常活动**无关**的利得计入营业外收入（6301）；
与日常活动**相关**的政府补助等计入其他收益（6117，K10 循环）。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 3.1~3.4, 1.1, 2.1~2.3 / Property 5, 6, 7
"""

from __future__ import annotations

from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
from app.services.four_table.pl_render import render_pl_cycle

from ._context import RenderContext

K12_SPEC = K_CYCLE_SPECS["K12"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测）。国企侧是「国企」。
K12_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司）"
K12_DISCLOSURE_SHEET_SOE = "附注披露信息（国企）"

K12_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k12-non-operating-income"},
    {"sheet_name": "实质性程序表K12A", "component_type": "k12-non-operating-income"},
    {"sheet_name": "审定表K12-1", "component_type": "k12-non-operating-income"},
    {
        "sheet_name": K12_DISCLOSURE_SHEET_LISTED,
        "component_type": "k12-non-operating-income",
    },
    {
        "sheet_name": K12_DISCLOSURE_SHEET_SOE,
        "component_type": "k12-non-operating-income",
    },
    {"sheet_name": "明细表K12-2", "component_type": "k12-non-operating-income"},
    {"sheet_name": "调整分录汇总K12-3", "component_type": "k12-non-operating-income"},
    {"sheet_name": "营业外收入检查表K12-4", "component_type": "k12-non-operating-income"},
]

K12_META = {
    "sheet_count": len(K12_SHEETS),
    "wp_code": "K12",
    "special_rules": {
        "income_statement": True,
        "account_direction": "credit",  # 贷方科目！（vs K11/K13 借方）
        "net_formula": "trial_balance 本期发生额（权威）/ tb_balance 贷方发生额（兜底）",
        "source_table": "trial_balance + tb_balance 叶子",
        "non_operating_classification": True,
        "vs_other_gains": "6117(K10)",  # 与日常活动相关的计入其他收益
    },
}


async def render(ctx: RenderContext) -> dict | None:
    """K12 营业外收入渲染策略：损益类取本期发生额（贷方科目）+ 取数溯源."""
    return await render_pl_cycle(
        ctx,
        K12_SPEC,
        component_type="k12-non-operating-income",
        sheets=K12_SHEETS,
        meta=K12_META,
    )
