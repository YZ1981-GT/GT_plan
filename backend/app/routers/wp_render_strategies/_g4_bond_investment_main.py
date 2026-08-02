"""G4 债权投资(main组) — 专属渲染策略.

componentType: g4-bond-investment-main

科目映射链路（report_config DB 实证，四准则一致）：
  BS-021 债权投资 = TB('1504','期末余额')
  标准科目 1504 债权投资（借方/资产类，以摊余成本计量的金融资产 CAS22 AC 类）

覆盖 8 个 sheet（sheetName v-if dispatch 主入口 GtG4BondInvestmentMain.vue 分发）：
    G4A 实质性程序表 / G4-1 审定表 / G4-2 明细表(44列→5区段) /
    G4-3 调整分录汇总 / G4-4 利息测算表 /
    附注披露信息（上市公司）/ 附注披露信息（国企）/ 底稿目录

四表取数：
  1. resolve_report_line_accounts → 标准码 1504
  2. tb_balance 叶子聚合 → tb_values / tb_source_codes / adjudication_prefill
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table import (
    build_g_adjudication_prefill,
    LeafRow,
    ReportLineAccountSpec,
    aggregate_leaves,
    filter_by_prefixes,
    parent_totals,
    resolve_report_line_accounts,
    select_leaves,
    to_leaf_rows,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 科目定位规格
# ─────────────────────────────────────────────────────────────────────────────

G4_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-021",            # 债权投资，四准则一致 TB('1504','期末余额')
    fallback_gross=("1504",),
    # 债权投资减值准备：report_config 有 IMP-005 但实务中与 G14 信用减值共管
    # 此处不做备抵预填（减值由 G4 ECL 测试表 + G14 联动）
)

_ADJUDICATED_ITEM_ID = "G4-1-adjudicated-amount"

G4_MAIN_SHEETS = [
    {
        "code": "G4A",
        "sheetName": "债权投资实质性程序表G4A",
        "componentType": "a-program-console",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-1",
        "sheetName": "审定表G4-1",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-2",
        "sheetName": "明细表G4-2",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-3",
        "sheetName": "调整分录汇总G4-3",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-4",
        "sheetName": "利息测算表G4-4",
        "componentType": "g4-bond-investment-main",
        "group": "measurement",
        "columns": [],
        "rows": [],
    },
    {
        "code": "附注披露信息（上市公司）",
        "sheetName": "附注披露信息（上市公司）",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "附注披露信息（国企）",
        "sheetName": "附注披露信息（国企）",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "底稿目录",
        "sheetName": "底稿目录",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数：叶子科目分类
# ─────────────────────────────────────────────────────────────────────────────


def classify_g4_leaf(name: str, code: str) -> str:
    """根据子科目名称分类债权投资。"""
    n = (name or "").lower()
    if any(kw in n for kw in ("国债", "政府债", "地方债")):
        return "government-bond"
    if any(kw in n for kw in ("企业债", "公司债", "可转债")):
        return "corporate-bond"
    if any(kw in n for kw in ("银行", "金融债", "同业")):
        return "financial-bond"
    if any(kw in n for kw in ("信托", "资管", "理财")):
        return "trust-plan"
    return "other"



# ─────────────────────────────────────────────────────────────────────────────
# 四表取数
# ─────────────────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取 1504 债权投资的四表数据。"""
    result: dict = {"tb_values": {}, "tb_source_codes": {}, "adjudication_prefill": {}}

    try:
        accounts = await resolve_report_line_accounts(ctx, G4_ACCOUNT_SPEC)

        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        query_prefixes = accounts.gross if accounts.gross else list(G4_ACCOUNT_SPEC.fallback_gross)
        if not query_prefixes:
            return result

        conditions = []
        for p in query_prefixes:
            conditions.append(TbBalance.account_code == p)
            conditions.append(TbBalance.account_code.like(f"{p}.%"))

        rows = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.dataset_id,
            ).where(sa.and_(active_filter, sa.or_(*conditions)))
        )
        all_rows = to_leaf_rows(rows.fetchall())

        if not all_rows:
            result["tb_source_codes"] = accounts.as_dict()
            return result

        leaves = select_leaves(all_rows)
        filtered_leaves = filter_by_prefixes(leaves, query_prefixes)
        agg = aggregate_leaves(filtered_leaves, query_prefixes)

        # 父科目勾稽
        parent = parent_totals(all_rows, query_prefixes[0] if len(query_prefixes) == 1 else "")
        parent_check = None
        if parent.get("closing", 0) != 0 or parent.get("opening", 0) != 0:
            leaf_sum = sum(r.closing for r in filtered_leaves)
            parent_check = {
                "leaf_sum": leaf_sum,
                "parent": parent.get("closing", 0),
                "diff": round(leaf_sum - parent.get("closing", 0), 2),
            }


        source_codes = accounts.as_dict()
        # 审定表「从四表库带入未审数」统一载荷（逐叶子明细，归类在前端做）
        result["adjudication_prefill"] = build_g_adjudication_prefill(
            "G4", accounts, all_rows
        )
        source_codes["gross"] = [r.account_code for r in filtered_leaves]
        if parent_check:
            source_codes["parent_check"] = parent_check

        result["tb_values"] = {
            "opening": agg["opening"],
            "closing": agg["closing"],
            "by_category": [
                {
                    "account_code": leaf.account_code,
                    "account_name": leaf.account_name,
                    "category": classify_g4_leaf(leaf.account_name, leaf.account_code),
                    "opening": leaf.opening,
                    "closing": leaf.closing,
                }
                for leaf in filtered_leaves
            ],
        }
        result["tb_source_codes"] = source_codes

    except Exception as e:  # noqa: BLE001
        logger.warning("G4 TB fetch failed: %s", e)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# render 主入口
# ─────────────────────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'G4-%' "
                "LIMIT 800"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
        adjudicated_amount = responses_snapshot.get(_ADJUDICATED_ITEM_ID, {}).get(
            "conclusion", ""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("G4 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": "1504",
        "applicable_standards": [],
    }
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, applicable_standard_v2 "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            raw_std = proj_row.applicable_standard_v2
            if raw_std:
                if isinstance(raw_std, dict):
                    std_type = raw_std.get("type", "")
                    if std_type:
                        project_context["applicable_standards"] = [std_type]
                elif isinstance(raw_std, str):
                    project_context["applicable_standards"] = [raw_std]
    except Exception as e:  # noqa: BLE001
        logger.warning("G4 render: project context 失败: %s", e)

    # 四表取数
    tb_data = await _fetch_tb_data(ctx)
    tb_values = tb_data["tb_values"]
    tb_source_codes = tb_data["tb_source_codes"]

    project_context["tb_source_codes"] = tb_source_codes
    project_context["tb_amount"] = tb_values.get("closing", 0) if tb_values else 0

    # 同循环底稿目录（G 循环全部底稿，跨底稿跳转）
    cycle_workpapers: list = []
    try:
        from app.services.wp_cycle_directory import build_cycle_workpapers

        cycle_workpapers = await build_cycle_workpapers(
            db=db,
            project_id=ctx.project_id,
            audit_cycle="G",
            current_wp_id=wp_id,
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "component_type": "g4-bond-investment-main",
        "sheets": G4_MAIN_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": "1504",
        "prefix": "G4",
        "tb_values": tb_values,
        "adjudication_prefill": tb_data["adjudication_prefill"],
        "tb_source_codes": tb_source_codes,
        "adjudicated_amount": adjudicated_amount,
        "cycle_workpapers": cycle_workpapers,
    }
