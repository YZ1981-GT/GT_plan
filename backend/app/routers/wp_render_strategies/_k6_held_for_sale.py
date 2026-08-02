"""K6 持有待售资产和负债 — 专属渲染策略.

componentType: k6-held-for-sale

科目定位走报表映射规则链路（共享件
`app/services/four_table/report_line_accounts.py` + 声明真源
`app/services/four_table/k_cycle_specs.py`）::

    资产侧 报表行 BS-015（上市）/ BS-024（国企）「持有待售资产」
    负债侧 报表行 BS-056（上市）/ BS-079（国企）「持有待售负债」

🔴 **本循环四表侧无法自动取数 —— 宁缺勿造（DB 只读实证）**

原实现硬编码 `1481`（资产）/ `2605`（负债），公式预设里还写过 `2331`
与病态区间 `TB_SUM('1481~2331')`。实证::

    report_config  : BS-015 / BS-024 / BS-056 / BS-079 四行 formula **全为 None**
    account_chart  : 1481 / 2605 / 2331 → 0 条；按名查「持有待售」→ 0 条
    tb_balance     : 1481% / 2605% → 0 行（active 数据集）
    trial_balance  : 1481 / 2605 / 2331 → 0 条

持有待售是**列报重分类**（CAS42）：满足五条件时把原本挂在固定资产、
长期股权投资等科目下的资产**在报表上**重分类到「持有待售资产」行，
客户账上通常并不新设科目。故四表侧本就无从取数。

按平台铁律**宁缺勿造**：不回退到任何不存在的码，返回空取数结果 +
`tb_source_codes.empty_reason` 留证，K6-1 审定表走手工录入
（金额来源是 K6-4 初始确认检查表逐项判定 + K6-5/K6-6 减值测试）。

**逃生通道**：项目级 `report_config` 覆盖（`applicable_standard = 'project:{id}'`）
会被解析链先命中，本模块无需改代码即生效。

**混合口径**：
- 资产侧（借方）：期末 = 期初 + 增加 − 减少 − 减值
- 负债侧（贷方）：期末 = 期初 + 增加 − 减少
**CAS42**：五条件分类 + 减值孰低法（账面价值 vs 公允价值减出售费用）。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.4, 4.1 / Property 4
"""

from __future__ import annotations

import logging

from app.services.four_table.k_cycle_specs import (
    EMPTY_REASON_NO_ACCOUNT,
    K6_LIABILITY_ROW_CODE_LISTED,
    K6_LIABILITY_ROW_CODE_SOE,
    K_CYCLE_SPECS,
)
from app.services.four_table.leaf_aggregation import LeafRow, aggregate_leaves
from app.services.four_table.report_line_accounts import (
    ReportLineAccounts,
    ReportLineAccountSpec,
    fetch_applicable_standards,
    resolve_report_line_accounts,
)
from app.services.four_table.tb_fetch import (
    fetch_tb_balance_leaves,
    fetch_trial_balance_amounts,
    load_project_context,
    load_responses_snapshot,
    sum_amounts,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

_LABEL = "K6 持有待售"
K6_SPEC = K_CYCLE_SPECS["K6"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测 `wb.sheetnames`）。
#: 🔴 国企侧是「前半角后全角」`(国企）`，且是「国企」而非「国有企业」。
K6_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司）"
K6_DISCLOSURE_SHEET_SOE = "附注披露信息(国企）"

K6_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k6-held-for-sale"},
    {"sheet_name": "实质性程序表 K6A", "component_type": "k6-held-for-sale"},
    {"sheet_name": "审定表 K6-1", "component_type": "k6-held-for-sale"},
    {"sheet_name": K6_DISCLOSURE_SHEET_LISTED, "component_type": "k6-held-for-sale"},
    {"sheet_name": K6_DISCLOSURE_SHEET_SOE, "component_type": "k6-held-for-sale"},
    {"sheet_name": "明细表K6-2", "component_type": "k6-held-for-sale"},
    {"sheet_name": "调整分录汇总 K6-3", "component_type": "k6-held-for-sale"},
    {"sheet_name": "初始确认检查表K6-4", "component_type": "k6-held-for-sale"},
    {"sheet_name": "减值准备测试表（后续计量） K6-5", "component_type": "k6-held-for-sale"},
    {"sheet_name": "处置组减值测试表（后续计量） K6-6", "component_type": "k6-held-for-sale"},
    {"sheet_name": "检查表（不再满足持有待售）K6-7", "component_type": "k6-held-for-sale"},
]

#: `tb_values` 键前缀（**保持不变** —— 前端在读 `hfs_asset_1481_*` / `hfs_liability_2605_*`。
#: 这两个键名里的码是错的，但改键名属前端联动改造，放在 Wave 4 与
#: `k6AccountScope.ts` 一起做；本波先保证**值**正确（恒 0 而非取到别的科目）。
_ASSET_KEY = "hfs_asset_1481"
_LIAB_KEY = "hfs_liability_2605"


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（可单测，无 DB）
# ─────────────────────────────────────────────────────────────────────────────


def build_tb_values(
    leaves: list[LeafRow],
    asset_accounts: ReportLineAccounts,
    liability_accounts: ReportLineAccounts,
    tb_amounts: dict[str, dict[str, float]],
) -> dict[str, float]:
    """组装前端 `tb_values`（资产侧保留符号 / 负债侧取绝对值）。

    无科目时全部返 0 —— 宁缺勿造的可观测形态。
    """
    asset_agg = aggregate_leaves(leaves, asset_accounts.gross)
    liab_agg = aggregate_leaves(leaves, liability_accounts.gross, absolute=True)
    asset_unadj, asset_audited = sum_amounts(tb_amounts, asset_accounts.gross_standard)
    liab_unadj, liab_audited = sum_amounts(tb_amounts, liability_accounts.gross_standard)
    return {
        f"{_ASSET_KEY}_opening": asset_agg["opening"],
        f"{_ASSET_KEY}_closing": asset_agg["closing"],
        f"{_ASSET_KEY}_debit": asset_agg["debit"],
        f"{_ASSET_KEY}_credit": asset_agg["credit"],
        f"{_ASSET_KEY}_unadjusted": asset_unadj,
        f"{_ASSET_KEY}_audited": asset_audited,
        f"{_LIAB_KEY}_opening": liab_agg["opening"],
        f"{_LIAB_KEY}_closing": liab_agg["closing"],
        f"{_LIAB_KEY}_debit": liab_agg["debit"],
        f"{_LIAB_KEY}_credit": liab_agg["credit"],
        f"{_LIAB_KEY}_unadjusted": abs(liab_unadj),
        f"{_LIAB_KEY}_audited": abs(liab_audited),
    }


def build_source_codes(
    asset_accounts: ReportLineAccounts, liability_accounts: ReportLineAccounts
) -> dict:
    """取数溯源结构（资产 + 负债两侧并列）。

    K6 一个循环管两侧，`tb_source_codes` 顶层给资产侧（前端共用件读顶层），
    负债侧放 `liability` 子键。任一侧解析不出即填 `empty_reason`。
    """
    out = asset_accounts.as_dict()
    out["nature"] = "balance"
    out["account_name"] = "持有待售资产"
    out["liability"] = liability_accounts.as_dict()
    out["liability"]["account_name"] = "持有待售负债"
    has_any = bool(asset_accounts.gross or liability_accounts.gross)
    out["empty_reason"] = None if has_any else EMPTY_REASON_NO_ACCOUNT
    return out


def _liability_spec(applicable_standards) -> ReportLineAccountSpec:
    """负债侧报表行（BS-056 上市 / BS-079 国企），无兜底码（宁缺勿造）。"""
    stds = [str(s or "") for s in (applicable_standards or [])]
    is_listed = any("listed" in s for s in stds)
    return ReportLineAccountSpec(
        row_code=K6_LIABILITY_ROW_CODE_LISTED if is_listed else K6_LIABILITY_ROW_CODE_SOE,
        fallback_gross=(),
        fallback_provision=(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# render
# ─────────────────────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    """K6 持有待售渲染策略：allResponses + projectContext + 取数溯源（通常为空）."""
    responses_snapshot = await load_responses_snapshot(ctx, "K6", label=_LABEL)

    standards = await fetch_applicable_standards(ctx)
    asset_accounts = await resolve_report_line_accounts(ctx, K6_SPEC.spec_for(standards))
    liability_accounts = await resolve_report_line_accounts(ctx, _liability_spec(standards))

    all_standard = list(asset_accounts.gross_standard) + list(
        liability_accounts.gross_standard
    )
    if asset_accounts.gross or liability_accounts.gross:
        leaves = await fetch_tb_balance_leaves(ctx, label=_LABEL)
        tb_amounts = await fetch_trial_balance_amounts(ctx, all_standard, label=_LABEL)
    else:
        logger.info("%s: 报表映射未解析出科目，按宁缺勿造返回空取数结果", _LABEL)
        leaves = []
        tb_amounts = {}

    tb_values = build_tb_values(leaves, asset_accounts, liability_accounts, tb_amounts)
    project_context = await load_project_context(ctx, label=_LABEL)

    return {
        "component_type": "k6-held-for-sale",
        "account_codes": all_standard,
        "account_directions": {
            **{c: "debit" for c in asset_accounts.gross_standard},
            **{c: "credit" for c in liability_accounts.gross_standard},
        },
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": build_source_codes(asset_accounts, liability_accounts),
        "project_context": project_context,
        "prefix": "K6",
        "sheets": K6_SHEETS,
    }
