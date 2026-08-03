"""K8 销售费用 — 专属渲染策略.

componentType: k8-selling-expenses

科目定位走报表映射规则链路（共享件 `four_table/report_line_accounts.py` +
声明真源 `four_table/k_cycle_specs.py`）::

    报表行 IS-004（上市）/ IS-022（国企）「销售费用」
      四准则一致：TB('6601','本期发生额')
          │ 标准码 → account_mapping 反解
          ▼
    客户原始码：6601 销售费用（活体子科目树 4 级，40+ 叶子）

🔴 **已修正：原实现的「净发生额 = 借方 − 贷方」在全年账上恒为 0。**

活体逐行实证（项目 `005a6f2d`，`6601` 及其全部子科目，**每一行**都成立）::

    account_code       debit_amount        credit_amount       净额
    6601               163,042,014.46      163,042,014.46      0.00
    6601.01            37,189,411.65       37,189,411.65       0.00
    6601.11            42,997,579.18       42,997,579.18       0.00

成因是序时账必有年末「结转损益」分录（计提时借记 6601、结转时贷记同额）。
故 `debit - credit` 对损益类是**结构性恒零**，审定表「与试算平衡表核对」列
一直显示 0，有明细后还会显示整额假差异。

权威口径 = `trial_balance`（`report_config` 的 `TB('6601','本期发生额')`
读的就是它；实证 `6601 = 505,080,400.27`），兜底取 `tb_balance.debit_amount`
（借方科目）。取数逻辑收敛在 `four_table/pl_occurrence.py`。

同时修掉**父子双计**（原 `_fetch_tb_income_statement` 的
`startswith(prefix)` 把父行与全部子行一并 SUM）与**缺点号边界**的自造 `_is_leaf`。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 3.1~3.4, 1.1, 2.1~2.3 / Property 5, 6, 7
"""

from __future__ import annotations

from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
from app.services.four_table.pl_render import render_pl_cycle

from ._context import RenderContext
from app.services.four_table import resolve_semantic_accounts
from app.services.four_table.k_cycle_specs import semantic_spec_of

K8_SPEC = K_CYCLE_SPECS["K8"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测 `wb.sheetnames`）。
#: 🔴 国企侧是「国企」而非「国有企业」（原写「国有企业」→ `?sheet=` 深链落空）。
K8_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司）"
K8_DISCLOSURE_SHEET_SOE = "附注披露信息（国企）"

#: sheet 名逐字取自源 xlsx（截止性测试两张的括号是**全角开、半角闭**）
K8_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k8-selling-expenses"},
    {"sheet_name": "实质性程序表K8A", "component_type": "k8-selling-expenses"},
    {"sheet_name": "审定表K8-1", "component_type": "k8-selling-expenses"},
    {"sheet_name": K8_DISCLOSURE_SHEET_LISTED, "component_type": "k8-selling-expenses"},
    {"sheet_name": K8_DISCLOSURE_SHEET_SOE, "component_type": "k8-selling-expenses"},
    {"sheet_name": "明细表K8-2", "component_type": "k8-selling-expenses"},
    {"sheet_name": "调整分录汇总K8-3", "component_type": "k8-selling-expenses"},
    {"sheet_name": "实质性分析K8-4", "component_type": "k8-selling-expenses"},
    {"sheet_name": "合同检查表K8-5", "component_type": "k8-selling-expenses"},
    {
        "sheet_name": "截止性测试(从记账凭证至原始凭证）K8-6",
        "component_type": "k8-selling-expenses",
    },
    {
        "sheet_name": "截止性测试（从原始凭证至记账凭证）K8-7",
        "component_type": "k8-selling-expenses",
    },
    {"sheet_name": "销售费用检查表K8-8", "component_type": "k8-selling-expenses"},
]

K8_META = {
    "sheet_count": len(K8_SHEETS),
    "wp_code": "K8",
    "special_rules": {
        "income_statement": True,
        "account_direction": "debit",
        # 🔴 不是「借方发生-贷方发生」—— 那个恒为 0，见模块 docstring
        "net_formula": "trial_balance 本期发生额（权威）/ tb_balance 借方发生额（兜底）",
        "source_table": "trial_balance + tb_balance 叶子",
        "substantive_analysis": True,
        "cutoff_test_bidirectional": True,
        "contract_check": True,
    },
}


async def render(ctx: RenderContext) -> dict | None:
    """K8 销售费用渲染策略：损益类取本期发生额（借方科目）+ 取数溯源."""

    # 科目定位（语义驱动，additive）
    _sem_spec = semantic_spec_of("K8")
    try:
        _sem_accounts = await resolve_semantic_accounts(ctx, _sem_spec) if _sem_spec else None
    except Exception:  # noqa: BLE001
        _sem_accounts = None

    return await render_pl_cycle(
        ctx,
        K8_SPEC,
        component_type="k8-selling-expenses",
        sheets=K8_SHEETS,
        meta=K8_META,
    )
