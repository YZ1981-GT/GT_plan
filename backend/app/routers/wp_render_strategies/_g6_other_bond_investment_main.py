"""G6 其他债权投资(main组) — 专属渲染策略.

componentType: g6-other-bond-investment-main
科目 1505 其他债权投资（借方/资产类，FVOCI-Debt 以公允价值计量且其变动计入其他综合收益，
CAS22 分类为 FVOCI-Debt 类）。

覆盖 8 个 sheet（sheetName v-if dispatch 主入口 GtG6OtherBondInvestmentMain.vue 分发）：
    G6A 实质性程序表 / G6-1 审定表 / G6-2 明细表(33列→3区段) /
    G6-3 坏账准备明细表(20列→2区段) / G6-4 调整分录汇总 /
    附注披露信息（上市公司）/ 附注披露信息（国企）/ 底稿目录

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免多 sheet dispatch 循环把 G6 各 sheet
   误判为非白名单而重写成 onlyoffice-sheet（否则专属组件被吞掉）。
2. 返回 8 个 sheet 的配置（componentType / sheetName / columns / rows）供前端分发。
3. 为 G6-1 审定表自动取数：1505 其他债权投资 的期初/期末余额（tb_balance，
   共享件 leaf_aggregation）供前端审定表试算表列（只读）seed。
4. 回读已持久化的审定数（EventBus substantive:adjudicated 落库的独立 item_id），
   供 render 回填 seed，避免刷新后丢失。

科目映射链路（report_config 权威真源 BS-022 四准则一致）：
  report_config BS-022 = TB('1505','期末余额')
  → resolve_report_line_account_codes → ['1505']
  → select_leaves + aggregate_leaves → opening/closing
  无备抵科目（CAS22 FVOCI-Debt 减值在 OCI 确认，不冲减资产负债表账面价值）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.services.four_table.leaf_aggregation import select_leaves, aggregate_leaves
from app.services.four_table.report_line_accounts import ReportLineAccountSpec

from ._context import RenderContext

logger = logging.getLogger(__name__)

# G6-1 审定表 TB 取数科目（report_config BS-022 = TB('1505','期末余额')，四准则一致）
# 原值为 "1503"（旧准则"可供出售金融资产"已废止），2026-08-01 纠正。
_G6_ACCOUNT_PREFIX = "1505"

# G6 科目解析规格（无 provision_row_code —— CAS22 FVOCI-Debt 减值在 OCI 不冲减账面价值）
_G6_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-022",
    fallback_gross=("1505",),
)

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


async def _fetch_tb_values(ctx: RenderContext) -> tuple[dict, dict]:
    """取 1505 其他债权投资 期初/期末余额，委托共享件 resolve_report_line_accounts.

    返回 (tb_values, tb_source_codes)：
      tb_values: {"opening": float, "closing": float} 或 {}（无数据时）
      tb_source_codes: {"gross_standard": [...], "resolved_from": "report_config"|"fallback"}
    取数失败降级为空，前端允许手填。
    """
    tb: dict[str, float] = {}
    tb_source_codes: dict = {
        "gross_standard": list(_G6_ACCOUNT_SPEC.fallback_gross),
        "resolved_from": "fallback",
    }
    try:
        from app.services.four_table.report_line_accounts import (
            resolve_report_line_accounts,
        )
        result = await resolve_report_line_accounts(ctx, _G6_ACCOUNT_SPEC)

        tb_source_codes = {
            "gross_standard": result.gross_standard,
            "resolved_from": result.resolved_from,
        }

        # 叶子口径聚合
        leaves = await select_leaves(
            ctx.db, ctx.project_id, ctx.year, result.gross_standard
        )
        agg = aggregate_leaves(leaves)

        if agg.opening != 0 or agg.closing != 0:
            tb = {"opening": agg.opening, "closing": agg.closing}
    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("G6 TB fetch failed (共享件): %s", e)
    return tb, tb_source_codes


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

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": _G6_ACCOUNT_PREFIX,
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

    tb_values, tb_source_codes = await _fetch_tb_values(ctx)

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
        "account_code": _G6_ACCOUNT_PREFIX,
        "prefix": "G6",
        # G6-1 审定表试算表列只读 seed（真接线：render→html_data→FormData→组件 watch）
        "tb_values": tb_values,
        # 科目溯源信息供前端 g6AccountScope / 溯源面板消费
        "tb_source_codes": tb_source_codes,
        # 审定数回读 seed（EventBus 持久化后刷新不丢失）
        "adjudicated_amount": adjudicated_amount,
        # 同循环底稿目录（G0/G1/.../G14 跨底稿跳转）
        "cycle_workpapers": cycle_workpapers,
    }
