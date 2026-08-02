"""G14 信用减值损失 — 专属渲染策略.

componentType: g14-credit-impairment-loss

科目定位：**语义驱动、逐项目**（单一真源 `four_table/g_cycle_specs.G14_SPEC`）。

`account_chart` 实证 ``6702 = 信用减值损失`` / ``6701 = 资产减值损失``；
而 `report_config` 的 ``IS-016 信用减值损失 = TB('6701')`` 与
``IS-017 资产减值损失 = TB('6702')`` **整整互换** → 不能以报表公式为定位依据，
改按科目名在本项目科目表里定位，报表公式降级为提示 + 冲突检测。

损益类科目：`tb_balance.closing_balance` 在含年末结转损益的全年账上恒为 0，
取数须看发生额（`debit` / `credit`）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table import (
    build_g_adjudication_prefill,
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    parent_totals,
    resolve_semantic_accounts,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.g_cycle_specs import G14_SPEC

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 科目定位规格
# ─────────────────────────────────────────────────────────────────────────────

#: 🔴 科目定位改走**语义驱动**（单一真源 `four_table/g_cycle_specs.G14_SPEC`）。
#:
#: 原实现用 ``ReportLineAccountSpec(row_code="IS-016", fallback_gross=("6702",))``
#: —— 兜底码是对的，但 **兜底永远用不上**：`report_config` 的 `IS-016 信用减值损失`
#: 写的是 ``TB('6701')``（= 资产减值损失，K11 的科目），解析成功后就以它为准。
#: 实证 `IS-016` 与 `IS-017 资产减值损失 = TB('6702')` **整整互换**（铁证：同库
#: `CFSS-003 = TB('6701')` / `CFSS-004 = TB('6702')` 是对的，利润表两行自相矛盾），
#: 活体差额 6701 = 3,876,759.84 vs 6702 = 126,151,230.15（虚减 1.22 亿）。
G14_ACCOUNT_SPEC = G14_SPEC

_ADJUDICATED_ITEM_ID = "G14-1-adjudicated-amount"

G14_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "g14-credit-impairment-loss"},
    {"sheet_name": "信用减值损失实质性程序表G14A", "component_type": "g14-credit-impairment-loss"},
    {"sheet_name": "审定表G14-1", "component_type": "g14-credit-impairment-loss"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "g14-credit-impairment-loss"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "g14-credit-impairment-loss"},
    {"sheet_name": "明细表G14-2", "component_type": "g14-credit-impairment-loss"},
    {"sheet_name": "调整分录汇总G14-3", "component_type": "g14-credit-impairment-loss"},
]


# ─────────────────────────────────────────────────────────────────────────────
# 四表取数
# ─────────────────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取 6702 信用减值损失的四表数据。"""
    result: dict = {"tb_values": {}, "tb_source_codes": {}, "adjudication_prefill": {}}

    try:
        accounts = await resolve_semantic_accounts(ctx, G14_ACCOUNT_SPEC)

        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        # 本项目无「信用减值损失」科目时返空（宁缺勿造，不退化为宽前缀）
        query_prefixes = accounts.codes_of("gross")
        if not query_prefixes:
            result["tb_source_codes"] = accounts.as_dict()
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
            "G14", accounts, all_rows
        )
        source_codes["gross"] = [r.account_code for r in filtered_leaves]
        if parent_check:
            source_codes["parent_check"] = parent_check

        # 损益类取数：debit_amount（发生额）
        result["tb_values"] = {
            "opening": agg["opening"],
            "closing": agg["closing"],
            "debit": agg.get("debit", 0),
            "credit": agg.get("credit", 0),
        }
        result["tb_source_codes"] = source_codes

    except Exception as e:  # noqa: BLE001
        logger.warning("G14 TB fetch failed: %s", e)

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
            {"wp_id": str(ctx.wp_id), "pfx": "G14-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("G14 render failed: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": "6702",
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
        logger.warning("G14 render: project context failed: %s", e)

    tb_data = await _fetch_tb_data(ctx)
    tb_values = tb_data["tb_values"]
    tb_source_codes = tb_data["tb_source_codes"]

    project_context["tb_source_codes"] = tb_source_codes
    project_context["tb_amount"] = tb_values.get("closing", 0) if tb_values else 0

    return {
        "component_type": "g14-credit-impairment-loss",
        "account_code": "6702",
        "prefix": "G14",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        "tb_values": tb_values,
        "tb_source_codes": tb_source_codes,
        # 审定表「从四表库带入未审数」（逐叶子明细；空 dict = 四表库无该科目数据）
        "adjudication_prefill": tb_data["adjudication_prefill"],
        "sheets": G14_SHEETS,
    }
