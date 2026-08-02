"""K10 其他收益 — 专属渲染策略.

componentType: k10-other-income

科目定位走报表映射规则链路（共享件 `four_table/report_line_accounts.py` +
声明真源 `four_table/k_cycle_specs.py`）::

    报表行 IS-010（上市）/ IS-030（国企）「加：其他收益」
      四准则一致：TB('6117','本期发生额')

🔴 **已修正：原实现的「净发生额 = 贷方 − 借方」在全年账上恒为 0**
（收益类是反向写法，同样恒零；成因与逐行实证见
`four_table/pl_occurrence.py` 模块 docstring）。
原实现还从 `tb_ledger` 全表 SUM 取发生额 —— 序时账含年末结转损益分录，
两侧同样相等，换表不解决问题。
权威口径 = `trial_balance`，兜底取 `tb_balance.credit_amount`（贷方科目）。

🔴 **符号处理**：`trial_balance` 中 `6117` 在项目 `005a6f2d` 为 `-146,477.91`、
在 `37814426` 为 `+15,712.56`（两种存储约定并存）。裁决依据取自报表语义：
`IS-010 加：其他收益` 前置运算符是 `+` → 按 `normalize_for_report` 取绝对值，
`raw_sign` 留证。

**与 K7 递延收益的勾稽**：其他收益的主要来源是政府补助分摊
（递延收益 2401 → 其他收益 6117），由 K10-4 政府补助核对表与
K7-4 分摊测算表双向核对。

**⚠️ `responses_key` 是 `allResponses` 而非 `responses_snapshot`** ——
前端 `GtK10OtherIncome` 已在读该键，改键名会静默断链。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 3.1~3.4, 1.1, 2.1~2.3 / Property 5, 6, 7
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
from app.services.four_table.pl_render import render_pl_cycle

from ._context import RenderContext

logger = logging.getLogger(__name__)

K10_SPEC = K_CYCLE_SPECS["K10"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测）。国企侧是「国企」。
K10_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司）"
K10_DISCLOSURE_SHEET_SOE = "附注披露信息（国企）"

K10_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k10-other-income"},
    {"sheet_name": "实质性程序表K10A", "component_type": "k10-other-income"},
    {"sheet_name": "审定表K10-1", "component_type": "k10-other-income"},
    {"sheet_name": K10_DISCLOSURE_SHEET_LISTED, "component_type": "k10-other-income"},
    {"sheet_name": K10_DISCLOSURE_SHEET_SOE, "component_type": "k10-other-income"},
    {"sheet_name": "明细表K10-2", "component_type": "k10-other-income"},
    {"sheet_name": "调整分录汇总K10-3", "component_type": "k10-other-income"},
    {"sheet_name": "政府补助核对表K10-4", "component_type": "k10-other-income"},
    {"sheet_name": "应收政府补助检查表K10-5", "component_type": "k10-other-income"},
    {"sheet_name": "其他收益检查表K10-6", "component_type": "k10-other-income"},
]

K10_META = {
    "sheet_count": len(K10_SHEETS),
    "wp_code": "K10",
    "special_rules": {
        "income_statement": True,
        "account_direction": "credit",  # 贷方科目！
        "net_formula": "trial_balance 本期发生额（权威）/ tb_balance 贷方发生额（兜底）",
        "source_table": "trial_balance + tb_balance 叶子",
        "government_grant_crosscheck": "K7(2401 递延收益分摊)",
        "vs_non_operating_income": "6301(K12)",  # 与日常活动无关的计入营业外收入
    },
}


async def _load_k7_cross_check(ctx: RenderContext) -> dict:
    """K10↔K7 交叉验证：递延收益（2401）本期减少额 ≈ 其他收益中的政府补助分摊。

    从 `tb_balance` 取 `2401` 的借方发生额（递延收益减少 = 分摊进损益）。
    仅供 K10-4 政府补助核对表参考展示，不做强约束（两者可能存在时间差异）。
    fail-open：查不到返 `None`。
    """
    try:
        result = await ctx.db.execute(
            sa.text(
                """
                SELECT SUM(b.debit_amount) AS k7_amortization
                FROM tb_balance b
                JOIN ledger_datasets d ON d.id = b.dataset_id AND d.status = 'active'
                WHERE b.project_id = :pid
                  AND (b.account_code = '2401' OR b.account_code LIKE '2401.%')
                """
            ),
            {"pid": str(ctx.project_id)},
        )
        row = result.fetchone()
        if row and row.k7_amortization is not None:
            return {"k7_deferred_income_amortization": float(row.k7_amortization)}
    except Exception as e:  # noqa: BLE001
        logger.warning("K10: K7 交叉验证查询失败（fail-open）: %s", e)
    return {"k7_deferred_income_amortization": None}


async def _load_applicable_standards(ctx: RenderContext) -> dict:
    """K10 额外需要 `applicable_standard_v2`（披露变体门控用）。失败返 ``{}``。"""
    try:
        result = await ctx.db.execute(
            sa.text(
                """
                SELECT p.applicable_standard_v2 AS applicable_standards
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
                """
            ),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row is not None:
            return {"applicable_standards": row.applicable_standards or ""}
    except Exception as e:  # noqa: BLE001
        logger.warning("K10 其他收益: applicable_standard_v2 加载失败: %s", e)
    return {}


async def _load_extra_context(ctx: RenderContext) -> dict:
    """K10 额外上下文：applicable_standards + K7 交叉验证。"""
    extra: dict = {}
    extra.update(await _load_applicable_standards(ctx))
    extra.update(await _load_k7_cross_check(ctx))
    return extra


async def render(ctx: RenderContext) -> dict | None:
    """K10 其他收益渲染策略：损益类取本期发生额（贷方科目）+ 取数溯源."""
    return await render_pl_cycle(
        ctx,
        K10_SPEC,
        component_type="k10-other-income",
        sheets=K10_SHEETS,
        meta=K10_META,
        responses_key="allResponses",
        extra_project_context=_load_extra_context,
    )
