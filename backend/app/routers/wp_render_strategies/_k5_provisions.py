"""K5 预计负债 — 专属渲染策略.

componentType: k5-provisions

科目定位**不硬编码前缀**，走报表映射规则链路（共享件
`app/services/four_table/report_line_accounts.py` + 声明真源
`app/services/four_table/k_cycle_specs.py`）::

    报表行 BS-068（上市）/ BS-094（国企）「预计负债」
      四准则一致：TB('2801','期末余额')
          │ 标准码 → account_mapping 反解
          ▼
    客户原始码：2801 预计负债

🔴 **已修正的历史错误（DB 只读实证）：原实现把 `2701 长期应付款` 当成预计负债。**

原代码写着「科目前缀：2701预计负债(贷方/负债类)」，但 `account_chart` 实证 `2701`
在**全部项目**中一律是**长期应付款**（L5 循环科目），且带四个子科目::

    2701      长期应付款
    2701.01   长期应付款_应付融资租赁款
    2701.02   长期应付款_应付长期保证金
    2701.03   长期应付款_应付长期借款
    2701.99   长期应付款_一年内到期的长期应付款

`2801` 才是预计负债（`account_chart` 5 条 / `tb_balance` 39 行 / `trial_balance`
4 条均存在）。与已修的 K2（把 `1231 坏账准备` 当其他流动资产）同级 —— 属「取错整个
科目族」，不是「数字不准」。破坏面还包括前端 `writebackTB2701` 把预计负债审定数
**写进长期应付款**的 `trial_balance`（污染 L5 口径）。

**同时修掉的两个静默缺陷**

1. **父子双计** —— 原 `_fetch_tb_data` 用 `code == prefix or code.startswith(prefix)`
   遍历全部 `tb_balance` 行累加，父科目行与其全部子科目行**同时**被计入 ≈ 真值 2 倍；
   `trial_balance` 侧的 `LIKE '2701%'` 同理。现改叶子口径 + 最长前缀归属。
2. **缺点号边界** —— 原自造 `_is_leaf` 用 `c.startswith(code)` 判子科目，
   `1221` 会误命中 `12210`（F1/G7 已删过同款）。现用共享件 `select_leaves`。

**负债口径**：期末 = 期初 + 计提(贷方增加) − 转销/冲回(借方减少)。
`tb_balance` 存在「无符号 + 方向列」与「已带符号」两种约定并存 —— 故对**聚合结果**
取绝对值（`aggregate_leaves(absolute=True)`），不在行级翻转方向。

**或有事项三级**：很可能→确认预计负债 / 可能→披露 / 极小可能→不处理。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.1, 1.3, 2.1~2.5, 4.1 / Property 1, 2, 3, 8
"""

from __future__ import annotations

import logging

from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    parent_totals,
    select_leaves,
)
from app.services.four_table.report_line_accounts import (
    ReportLineAccounts,
    fetch_applicable_standards,
    resolve_report_line_accounts,
)
from app.services.four_table.tb_fetch import (
    fetch_tb_balance_all,
    fetch_trial_balance_amounts,
    load_project_context,
    load_responses_snapshot,
    sum_amounts,
)

from ._context import RenderContext
from app.services.four_table import resolve_semantic_accounts
from app.services.four_table.k_cycle_specs import semantic_spec_of

logger = logging.getLogger(__name__)

_LABEL = "K5 预计负债"
K5_SPEC = K_CYCLE_SPECS["K5"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测 `wb.sheetnames`）。
#: 🔴 上市侧是「前全角后半角」`（上市公司)`，国企侧是「国企」而非「国有企业」
#: （原 `K5_SHEETS` 写的是「国有企业」，与源模板不一致 → `?sheet=` 深链落空）。
K5_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司)"
K5_DISCLOSURE_SHEET_SOE = "附注披露信息（国企）"

K5_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k5-provisions"},
    {"sheet_name": "实质性程序表 K5A", "component_type": "k5-provisions"},
    {"sheet_name": "审定表 K5-1", "component_type": "k5-provisions"},
    {"sheet_name": K5_DISCLOSURE_SHEET_LISTED, "component_type": "k5-provisions"},
    {"sheet_name": K5_DISCLOSURE_SHEET_SOE, "component_type": "k5-provisions"},
    {"sheet_name": "明细表 K5-2", "component_type": "k5-provisions"},
    {"sheet_name": "调整分录汇总 K5-3", "component_type": "k5-provisions"},
    {"sheet_name": "产品质量保修检查表 K5-4", "component_type": "k5-provisions"},
    {"sheet_name": "弃置费用检查表 K5-5", "component_type": "k5-provisions"},
    {"sheet_name": "未决诉讼检查表 K5-6", "component_type": "k5-provisions"},
    {"sheet_name": "预计负债检查表 K5-7", "component_type": "k5-provisions"},
]

#: `tb_values` 键前缀。🔴 由 `provisions_2701_*` 改为**不含科目码**的
#: `provisions_*` —— 旧键名把错误科目码写进了契约，改对科目后旧键名会持续误导。
#: 前端 `useK5FormData.loadTbData` 同步改读新键（同一 commit 内两侧一起改）。
_KEY = "provisions"


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（可单测，无 DB）
# ─────────────────────────────────────────────────────────────────────────────


def build_tb_values(
    leaves: list[LeafRow],
    accounts: ReportLineAccounts,
    tb_amounts: dict[str, dict[str, float]],
) -> dict[str, float]:
    """组装前端 `tb_values`（负债口径：对聚合结果取绝对值）。

    `tb_amounts` 由 :func:`fetch_trial_balance_amounts` 按**最长前缀**归属后给出
    （防父子双计）。
    """
    agg = aggregate_leaves(leaves, accounts.gross, absolute=True)
    unadj, audited = sum_amounts(tb_amounts, accounts.gross_standard)
    return {
        f"{_KEY}_opening": agg["opening"],
        f"{_KEY}_closing": agg["closing"],
        f"{_KEY}_debit": agg["debit"],
        f"{_KEY}_credit": agg["credit"],
        f"{_KEY}_unadjusted": abs(unadj),
        f"{_KEY}_audited": abs(audited),
    }


def build_adjudication_prefill(
    leaves: list[LeafRow], accounts: ReportLineAccounts
) -> list[dict]:
    """按**叶子科目**建 K5-1 审定表行候选（负债口径取余额绝对值）。

    返回 ``[{name, code, opening_balance, closing_balance}]``，按期末绝对值降序。

    **宁缺勿造**：科目名为空或期初期末双零的叶子跳过；无命中返 ``[]``。
    """
    rows: list[dict] = []
    for r in filter_by_prefixes(leaves, accounts.gross):
        name = (r.account_name or "").strip()
        if not name:
            continue
        if abs(r.opening) < 0.005 and abs(r.closing) < 0.005:
            continue
        rows.append(
            {
                "name": name,
                "code": r.account_code,
                "opening_balance": abs(r.opening),
                "closing_balance": abs(r.closing),
            }
        )
    rows.sort(key=lambda x: x["closing_balance"], reverse=True)
    return rows


def build_parent_check(
    all_rows: list[LeafRow], leaves: list[LeafRow], accounts: ReportLineAccounts
) -> dict:
    """自检不变量：叶子和 == 父科目行金额（Property 1）。"""
    prefix = (accounts.gross[0] if accounts.gross else "").strip()
    if not prefix:
        return {"prefix": "", "leaf_sum": 0.0, "parent": 0.0, "diff": 0.0}
    leaf_sum = aggregate_leaves(leaves, [prefix])["closing"]
    parent = parent_totals(all_rows, prefix)["closing"]
    return {
        "prefix": prefix,
        "leaf_sum": leaf_sum,
        "parent": parent,
        "diff": leaf_sum - parent,
    }


# ─────────────────────────────────────────────────────────────────────────────
# render
# ─────────────────────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    """K5 预计负债渲染策略：allResponses + projectContext + TB数据 + 取数溯源."""

    # 科目定位（语义驱动，additive）
    _sem_spec = semantic_spec_of("K5")
    try:
        _sem_accounts = await resolve_semantic_accounts(ctx, _sem_spec) if _sem_spec else None
    except Exception:  # noqa: BLE001
        _sem_accounts = None

    responses_snapshot = await load_responses_snapshot(ctx, "K5", label=_LABEL)

    standards = await fetch_applicable_standards(ctx)
    accounts = await resolve_report_line_accounts(ctx, K5_SPEC.spec_for(standards))

    all_rows = await fetch_tb_balance_all(ctx, label=_LABEL)
    leaves = select_leaves(all_rows)
    tb_amounts = await fetch_trial_balance_amounts(
        ctx, list(accounts.gross_standard), label=_LABEL
    )

    tb_values = build_tb_values(leaves, accounts, tb_amounts)
    adjudication_prefill = build_adjudication_prefill(leaves, accounts)
    project_context = await load_project_context(ctx, label=_LABEL)

    source_codes = accounts.as_dict()
    source_codes["nature"] = "balance"
    source_codes["empty_reason"] = None
    source_codes["account_name"] = K5_SPEC.account_name

    return {
        "component_type": "k5-provisions",
        "account_codes": list(accounts.gross_standard),
        "account_direction": "credit",  # 负债类！贷方增加
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": source_codes,
        "parent_check": build_parent_check(all_rows, leaves, accounts),
        "project_context": project_context,
        "adjudication_prefill": adjudication_prefill,
        "prefix": "K5",
        "sheets": K5_SHEETS,
    }
