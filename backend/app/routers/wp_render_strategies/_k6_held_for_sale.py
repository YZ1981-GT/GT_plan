"""K6 持有待售资产和负债 — 专属渲染策略.

componentType: k6-held-for-sale

科目定位走报表映射规则链路（共享件
`app/services/four_table/report_line_accounts.py` + 声明真源
`app/services/four_table/k_cycle_specs.py`）。**行号真源在声明表，不在本文件** ——
本模块只经 `K6_SPEC.spec_for()` / `liability_spec_for()` 取，不再写 row_code 字面量。

🔴🔴 **2026-08-12 更正：本文件原 docstring 的「宁缺勿造」结论已被连库实证推翻。**

原文断言「`BS-015 / BS-024 / BS-056 / BS-079` 四行 formula 全为 None」「`1481 / 2605
/ 2331` 在 account_chart → 0 条」并据此走宁缺勿造。实证结果是：**那四个 row_code 本身
就是错的**（`BS-015` 是「流动资产合计」ROW() 派生行、`BS-024` 是**长期股权投资**
`TB('1511')`、`BS-056` soe 侧是「△向中央银行借款」、`BS-079` listed 侧是**资本公积**），
拿错行去查当然查不到公式。按 `row_name` 反查后的正确落点（两准则同号）::

    资产侧  BS-012  持有待售资产 = TB('1481','期末余额')
    负债侧  BS-051  持有待售负债 = TB('2245','期末余额')
    备抵侧  IMP-007 持有待售资产减值准备 = TB('1482')   （仅 soe_standalone 有公式）

且 `1481` / `1482` / `2245` 在 `account_chart` **client 侧确实存在**（各 1 个项目）。
故 `has_account=True`，本循环**可以**自动取数 —— 不再走宁缺勿造。

**两层「取不到数」必须可分**（Requirement 4.6）：

- `EMPTY_REASON_NO_ACCOUNT`（标准科目表里就没这科目）—— K6 **不适用**
- `EMPTY_REASON_NOT_IN_PROJECT`（科目存在但本项目没用）—— K6 多数项目走这条

前者是设计期结论，后者是运行期降级；混用会让审计师以为「平台不支持这个循环」。

**逃生通道**：项目级 `report_config` 覆盖（`applicable_standard = 'project:{id}'`）
会被解析链先命中，本模块无需改代码即生效。

**混合口径**：
- 资产侧（借方）：期末 = 期初 + 增加 − 减少 − 减值
- 负债侧（贷方）：期末 = 期初 + 增加 − 减少
**CAS42**：五条件分类 + 减值孰低法（账面价值 vs 公允价值减出售费用）。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 4.1, 4.2, 4.5, 4.6 / Property 12, 13, 15
"""

from __future__ import annotations

import logging

from app.services.four_table.k_cycle_specs import (
    EMPTY_REASON_NOT_IN_PROJECT,
    K_CYCLE_SPECS,
    liability_spec_for,
)
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    select_leaves,
)
from app.services.four_table.parent_check import build_report_line_parent_check
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
from app.services.four_table.tb_query import fetch_trial_balance_rows

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
    asset_accounts: ReportLineAccounts,
    liability_accounts: ReportLineAccounts,
    *,
    leaf_hits: int = 0,
) -> dict:
    """取数溯源结构（资产 + 负债两侧并列）。

    K6 一个循环管两侧，`tb_source_codes` 顶层给资产侧（前端共用件读顶层），
    负债侧放 `liability` 子键。

    Args:
        leaf_hits: `tb_balance` 里被两侧前缀命中的**叶子行数**。为 0 时填
            ``EMPTY_REASON_NOT_IN_PROJECT`` —— 见函数体内说明，判据不能用
            ``accounts.gross`` 非空。
    """
    out = asset_accounts.as_dict()
    out["nature"] = "balance"
    out["account_name"] = "持有待售资产"
    out["liability"] = liability_accounts.as_dict()
    out["liability"]["account_name"] = "持有待售负债"

    # 🔴 判据不能是「解析出了前缀」（Requirement 4.6）。
    #
    # `resolve_report_line_accounts` 在 `account_mapping` 无反解记录时会把**标准码
    # 本身**当原始码前缀返回 ⇒ `accounts.gross` 对所有项目恒非空（实测 8/8 项目的
    # K6 负债侧都拿到 `['2245']`）。若按 `gross` 非空判，`empty_reason` **永不触发**，
    # 用户只看到一片 0.00、无从区分「本项目没这科目」与「余额确实为 0」。
    #
    # 故判据改为「`tb_balance` 里是否真有匹配叶子」—— 由调用方把命中数传进来。
    out["empty_reason"] = None if leaf_hits else EMPTY_REASON_NOT_IN_PROJECT
    return out


def build_adjudication_prefill(
    leaves: list[LeafRow],
    asset_accounts: ReportLineAccounts,
    liability_accounts: ReportLineAccounts,
) -> list[dict]:
    """按叶子科目建 K6-1 审定表行候选（镜像 K4 的同名函数）。

    K6 一个循环管资产与负债**两侧且方向相反**，故行里带 ``side`` 供前端分区展示：

    - 资产侧（``1481`` debit）**保留符号** —— 与 `build_tb_values` 的资产侧同口径
    - 负债侧（``2245`` credit）取 ``abs()`` —— 负债在审定表按正数列示

    宁缺勿造：科目名为空、或期初期末双零的叶子跳过；解析不出任何科目返 ``[]``
    （不造「其他」兜底行）。排序按期末绝对值降序，资产侧在前。
    """
    rows: list[dict] = []
    for side, accounts, absolute in (
        ("asset", asset_accounts, False),
        ("liability", liability_accounts, True),
    ):
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
                    "side": side,
                    "opening_balance": abs(r.opening) if absolute else r.opening,
                    "closing_balance": abs(r.closing) if absolute else r.closing,
                }
            )
    # 资产侧优先（side 升序：asset < liability），同侧按期末绝对值降序
    rows.sort(key=lambda x: (x["side"], -abs(x["closing_balance"])))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# render
# ─────────────────────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    """K6 持有待售渲染策略：allResponses + projectContext + 取数溯源（通常为空）."""

    responses_snapshot = await load_responses_snapshot(ctx, "K6", label=_LABEL)

    standards = await fetch_applicable_standards(ctx)
    asset_accounts = await resolve_report_line_accounts(ctx, K6_SPEC.spec_for(standards))
    # 🔴 负债侧规格取自**声明真源** `k_cycle_specs.liability_spec_for`（它带
    #    `is_liability=True` / `gross_direction='credit'` / 兜底码 `2245`）。
    #    本模块此前自写了一份 `_liability_spec()`：row_code 虽经常量取得正确，但
    #    **三项声明全缺** —— 当前 `BS-051` 是单码公式 `TB('2245')` 故解析结果偶然
    #    相同（已连库逐项目核对，8/8 逐字一致），可一旦该行公式将来引入备抵码，
    #    缺 `is_liability` 就会让 `split_gross_provision` 把原值判成备抵、gross 变空。
    #    双真源本身就是缺陷，故删本地版、改用声明真源（`liability_spec_for` 原为
    #    生产零消费方 = 死代码，本次接线后才真正生效）。
    liability_accounts = await resolve_report_line_accounts(
        ctx, liability_spec_for(standards)
    )

    all_standard = list(asset_accounts.gross_standard) + list(
        liability_accounts.gross_standard
    )
    all_prefixes = list(asset_accounts.gross) + list(liability_accounts.gross)

    # 取**全量**行：`parent_check` 的 `parent` 口径要读父科目行本身，
    # 预先筛叶子会让该口径恒 0 并被共享件静默跳过（三口径退化成两口径，不打红）。
    all_rows: list[LeafRow] = []
    if all_prefixes:
        all_rows = await fetch_tb_balance_all(ctx, label=_LABEL)
        leaves = select_leaves(all_rows)
        tb_amounts = await fetch_trial_balance_amounts(ctx, all_standard, label=_LABEL)
    else:
        logger.info("%s: 报表映射未解析出科目，返回空取数结果", _LABEL)
        leaves = []
        tb_amounts = {}

    # `empty_reason` 的判据（见 `build_source_codes` 说明）：解析出前缀 ≠ 本项目有该科目
    leaf_hits = len(filter_by_prefixes(leaves, all_prefixes)) if all_prefixes else 0

    tb_values = build_tb_values(leaves, asset_accounts, liability_accounts, tb_amounts)
    adjudication_prefill = build_adjudication_prefill(
        leaves, asset_accounts, liability_accounts
    )
    project_context = await load_project_context(ctx, label=_LABEL)

    # 三口径自检 —— 资产侧与负债侧分别走共享件（方向相反，不能合成一个规格）
    parent_check: dict = {}
    if all_prefixes:
        try:
            trial_rows = await fetch_trial_balance_rows(
                ctx.db, ctx.project_id, ctx.year, all_standard
            )
            parent_check = {
                f"asset_{k}": v
                for k, v in build_report_line_parent_check(
                    asset_accounts, all_rows, trial_rows
                ).items()
            }
            parent_check.update(
                {
                    f"liability_{k}": v
                    for k, v in build_report_line_parent_check(
                        liability_accounts, all_rows, trial_rows
                    ).items()
                }
            )
        except Exception as e:  # noqa: BLE001 — fail-open，不影响其余输出
            logger.warning("%s: parent_check 构造失败: %s", _LABEL, e)

    return {
        "component_type": "k6-held-for-sale",
        "account_codes": all_standard,
        "account_directions": {
            **{c: "debit" for c in asset_accounts.gross_standard},
            **{c: "credit" for c in liability_accounts.gross_standard},
        },
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": build_source_codes(
            asset_accounts, liability_accounts, leaf_hits=leaf_hits
        ),
        "adjudication_prefill": adjudication_prefill,
        "parent_check": parent_check,
        "project_context": project_context,
        "prefix": "K6",
        "sheets": K6_SHEETS,
    }
