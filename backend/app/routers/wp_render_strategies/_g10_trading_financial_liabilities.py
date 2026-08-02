"""G10 交易性金融负债 — 专属渲染策略.

componentType: g10-trading-financial-liabilities

科目映射链路（report_config DB 实证，四准则一致）：
  BS-042 交易性金融负债 = TB('2101','期末余额')
  标准科目 2101 交易性金融负债（贷方/负债类）
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

G10_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-042",
    fallback_gross=("2101",),
)

_ADJUDICATED_ITEM_ID = "G10-1-adjudicated-amount"

G10_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "交易性金融负债实质性程序表G10A", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "审定表G10-1", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "明细表G10-2", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "调整分录汇总G10-3", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "分类的适当性检查表G10-4", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "公允价值测试表G10-5", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "第三层次公允价值计量的调节表G10-6", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "凭证检查表G10-7", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "衍生金融工具核查表G10-8", "component_type": "g10-trading-financial-liabilities"},
]


# ─────────────────────────────────────────────────────────────────────────────
# 四表取数
# ─────────────────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取 2101 交易性金融负债的四表数据。"""
    result: dict = {"tb_values": {}, "tb_source_codes": {}, "adjudication_prefill": {}}

    try:
        accounts = await resolve_report_line_accounts(ctx, G10_ACCOUNT_SPEC)

        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        query_prefixes = accounts.gross if accounts.gross else list(G10_ACCOUNT_SPEC.fallback_gross)
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
            "G10", accounts, all_rows
        )
        source_codes["gross"] = [r.account_code for r in filtered_leaves]
        if parent_check:
            source_codes["parent_check"] = parent_check

        # 负债类取数：closing_balance（贷方正值）
        result["tb_values"] = {
            "opening": agg["opening"],
            "closing": agg["closing"],
            "debit": agg.get("debit", 0),
            "credit": agg.get("credit", 0),
        }
        result["tb_source_codes"] = source_codes

    except Exception as e:  # noqa: BLE001
        logger.warning("G10 TB fetch failed: %s", e)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# render 主入口
# ─────────────────────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "G10-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("G10 render failed: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": "2101",
        "applicable_standards": [],
    }
    try:
        proj_result = await ctx.db.execute(
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
        logger.warning("G10 render: project context failed: %s", e)

    tb_data = await _fetch_tb_data(ctx)
    tb_values = tb_data["tb_values"]
    tb_source_codes = tb_data["tb_source_codes"]

    project_context["tb_source_codes"] = tb_source_codes
    project_context["tb_amount"] = tb_values.get("closing", 0) if tb_values else 0

    return {
        "component_type": "g10-trading-financial-liabilities",
        "account_code": "2101",
        "prefix": "G10",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        "tb_values": tb_values,
        "tb_source_codes": tb_source_codes,
        # 审定表「从四表库带入未审数」（逐叶子明细；空 dict = 四表库无该科目数据）
        "adjudication_prefill": tb_data["adjudication_prefill"],
        "sheets": G10_SHEETS,
    }
