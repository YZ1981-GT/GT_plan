"""G6 其他债权投资(main组) — 专属渲染策略.

componentType: g6-other-bond-investment-main
科目「其他债权投资」（借方/资产类，CAS22 分类为 FVOCI-Debt：以公允价值计量且其变动计入
其他综合收益）。**科目码逐项目解析、不写死** —— 见下方「科目映射链路」。

覆盖 8 个 sheet（sheetName v-if dispatch 主入口 GtG6OtherBondInvestmentMain.vue 分发）：
    G6A 实质性程序表 / G6-1 审定表 / G6-2 明细表(33列→3区段) /
    G6-3 坏账准备明细表(20列→2区段) / G6-4 调整分录汇总 /
    附注披露信息（上市公司）/ 附注披露信息（国企）/ 底稿目录

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免多 sheet dispatch 循环把 G6 各 sheet
   误判为非白名单而重写成 onlyoffice-sheet（否则专属组件被吞掉）。
2. 返回 8 个 sheet 的配置（componentType / sheetName / columns / rows）供前端分发。
3. 为 G6-1 审定表自动取数：「其他债权投资」的期初/期末余额（tb_balance 叶子口径，
   共享件 leaf_aggregation）供前端审定表试算表列（只读）seed。
4. 回读已持久化的审定数（EventBus substantive:adjudicated 落库的独立 item_id），
   供 render 回填 seed，避免刷新后丢失。

科目映射链路（**语义驱动、逐项目**，单一真源 `four_table/g_cycle_specs.G6_SPEC`）::

    槽「其他债权投资」（按科目名，否决词排除各类备抵）
      → 本项目 account_chart（client 优先 / standard 兜底）→ 实际科目码
      → account_mapping 换算 → tb_balance 原始码前缀 / trial_balance 标准码
      → select_leaves + aggregate_leaves → opening / closing

🔴 **为什么不写死码**（2026-08-01 实证，两次踩坑）：

- 原写 ``1503``（旧准则「可供出售金融资产」，已废止）→ 取数恒空。
- 后按 `report_config` 的 ``BS-022 = TB('1505')`` "纠正"为 ``1505``，但
  `account_chart` + `trial_balance.account_name` 双证 **``1505`` 实为「债权投资减值准备」**
  —— 该报表行本身错码（BS-022→1505 / BS-025→1506 / BS-026→1507 连续偏移一位，
  真值应为 1506 / 1507 / 1519）。其他债权投资的真实科目是 **1506**。
- 且标准码在项目间并不一致（`account_mapping` 同一原始码在不同项目映射到不同标准码；
  标准科目表本身各项目也不同）→ 只能按科目名在该项目自己的科目表里定位。

无备抵槽（CAS22 FVOCI-Debt 减值在 OCI 确认，不冲减资产负债表账面价值）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.g_cycle_adjudication_prefill import (
    build_g_adjudication_prefill,
)
from app.services.four_table.g_cycle_specs import G6_SPEC
from app.services.four_table.leaf_aggregation import (
    aggregate_leaves,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.semantic_account_resolver import (
    resolve_primary_code,
    resolve_semantic_accounts,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 🔴 科目一律由 `four_table/g_cycle_specs.G6_SPEC` 按**科目名**逐项目解析，此处不再留常量。
#
# 历史：原写 "1503"（旧准则「可供出售金融资产」，已废止）→ 2026-08-01 曾"纠正"为 "1505"，
# 但 `account_chart` + `trial_balance.account_name` 双证 **1505 实为「债权投资减值准备」**
# —— 那次纠正抄的是 `report_config` 的 `BS-022`，而该行本身错码（连续偏移一位：
# BS-022→1505 / BS-025→1506 / BS-026→1507，真值应为 1506 / 1507 / 1519）。
# 其他债权投资的真实科目是 **1506**，且标准码在项目间并不一致（详见
# `four_table/semantic_account_resolver` 模块 docstring），故不写死任何码。

# EventBus 审定值持久化的独立 item_id（render 回读 seed）
_ADJUDICATED_ITEM_ID = "G6-1-adjudicated-amount"

# 8 个 sheet 配置：sheetName（与源 xlsx tab 名一致）/ code（前端正则提取分发键）/
# componentType（G6A 复用 a-program-console，其余走主入口子组件）。
# columns / rows 的具体列定义由前端 composable 提供，此处返回轻量占位供主入口分发。
G6_MAIN_SHEETS = [
    {
        "code": "G6A",
        "sheetName": "其他债权投资实质性程序表G6A",
        "componentType": "a-program-console",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-1",
        "sheetName": "审定表G6-1",
        "componentType": "g6-other-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-2",
        "sheetName": "明细表G6-2",
        "componentType": "g6-other-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-3",
        "sheetName": "坏账准备明细表G6-3",
        "componentType": "g6-other-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-4",
        "sheetName": "调整分录汇总G6-4",
        "componentType": "g6-other-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "附注披露信息（上市公司）",
        "sheetName": "附注披露信息（上市公司）",
        "componentType": "g6-other-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "附注披露信息（国企）",
        "sheetName": "附注披露信息（国企）",
        "componentType": "g6-other-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "底稿目录",
        "sheetName": "底稿目录",
        "componentType": "g6-other-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
]


async def _fetch_tb_values(ctx: RenderContext) -> tuple[dict, dict, dict]:
    """取「其他债权投资」期初/期末余额，科目由 `G6_SPEC` 按科目名逐项目解析。

    返回 ``(tb_values, tb_source_codes, adjudication_prefill)``：
      tb_values: ``{"opening": float, "closing": float}`` 或 ``{}``（无数据时）
      tb_source_codes: 语义解析结果（含扁平投影 + slots + conflicts）
      adjudication_prefill: 审定表「从四表库带入未审数」载荷（逐叶子明细）或 ``{}``

    🔴 `adjudication_prefill` 此前**从未产出**（本文件全文无该键），而
    `G6TabAdjudication.vue` 的「从四表库带入未审数」按钮读的正是它
    → `hasTbPrefill` 恒 false、按钮永久禁用。本次补齐。

    取数失败降级为空，前端允许手填。
    """
    tb: dict[str, float] = {}
    prefill: dict = {}
    accounts = await resolve_semantic_accounts(ctx, G6_SPEC)
    tb_source_codes = accounts.as_dict()
    slot = accounts.slots.get("gross")
    if slot is None or not slot.found:
        # 本项目无「其他债权投资」科目 → 空 seed（前端手填），不退化为宽前缀取错数
        return tb, tb_source_codes, prefill

    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.dataset_id,
            ).where(active_filter)
        )
        # 🔴 叶子口径 + 点号边界（共享件），防父子双算与 `1506` 误命中 `15060`
        all_rows = to_leaf_rows(result.fetchall())
        leaves = select_leaves(all_rows)
        agg = aggregate_leaves(leaves, slot.codes)
        if agg["opening"] != 0 or agg["closing"] != 0:
            tb = {"opening": agg["opening"], "closing": agg["closing"]}
        # 审定表「从四表库带入未审数」统一载荷（逐叶子明细，归类在前端做）
        prefill = build_g_adjudication_prefill("G6", accounts, all_rows)
    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("G6 TB fetch failed: %s", e)
    return tb, tb_source_codes, prefill


async def render(ctx: RenderContext) -> dict | None:
    """G6 其他债权投资(main组) 渲染策略：返回 8 sheet 配置 + TB seed + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'G6-%' "
                "LIMIT 800"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
        # 审定值回读：EventBus substantive:adjudicated 落库的独立 item_id
        adjudicated_amount = responses_snapshot.get(_ADJUDICATED_ITEM_ID, {}).get(
            "conclusion", ""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("G6 render: checklist_responses 失败: %s", e)

    # 科目码逐项目解析（无该科目时为空串 —— 宁缺勿造，不展示别循环的码）
    account_code = await resolve_primary_code(ctx, G6_SPEC)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": account_code,
    }
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("G6 render: project context 失败: %s", e)

    tb_values, tb_source_codes, adjudication_prefill = await _fetch_tb_values(ctx)

    # ─── 同循环底稿目录（G 循环全部底稿，跨底稿跳转） ──────────────────
    from app.services.wp_cycle_directory import build_cycle_workpapers

    cycle_workpapers = await build_cycle_workpapers(
        db=ctx.db,
        project_id=ctx.project_id,
        audit_cycle="G",
        current_wp_id=ctx.wp_id,
    )

    return {
        "component_type": "g6-other-bond-investment-main",
        # 8 个 sheet 配置（componentType / sheetName / columns / rows）
        "sheets": G6_MAIN_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": account_code,
        "prefix": "G6",
        # G6-1 审定表试算表列只读 seed（真接线：render→html_data→FormData→组件 watch）
        "tb_values": tb_values,
        # 科目溯源信息供前端 g6AccountScope / 溯源面板消费
        "tb_source_codes": tb_source_codes,
        # 审定表「从四表库带入未审数」（逐叶子明细；空 dict = 四表库无该科目数据）
        "adjudication_prefill": adjudication_prefill,
        # 审定数回读 seed（EventBus 持久化后刷新不丢失）
        "adjudicated_amount": adjudicated_amount,
        # 同循环底稿目录（G0/G1/.../G14 跨底稿跳转）
        "cycle_workpapers": cycle_workpapers,
    }
