"""G3 应收股利 — 专属渲染策略.

componentType: g3-dividend-receivable

科目映射链路：
  标准科目 1131 应收股利（借方/资产类）。
  report_config：BS-016「其中：应收股利」formula = None（不单独列报）。
  直接使用兜底码 1131。

G3-1 审定表结构较简单（无坏账准备段 — 应收股利按信用减值测试但通常不单独计提）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table import (
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

G3_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-016",            # 「其中：应收股利」— formula 通常 None
    fallback_gross=("1131",),
)

_ADJUDICATED_ITEM_ID = "G3-1-adjudicated-amount"


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数：叶子科目分类
# ─────────────────────────────────────────────────────────────────────────────


def classify_g3_leaf(name: str, code: str) -> str:
    """根据子科目名称分类。应收股利通常按被投资单位分设子科目。"""
    n = (name or "").lower()
    if any(kw in n for kw in ("子公司", "全资")):
        return "subsidiary"
    if any(kw in n for kw in ("联营", "合营")):
        return "associate"
    if any(kw in n for kw in ("基金", "理财")):
        return "fund"
    return "other"


def build_g3_adjudication_prefill(leaves: list[LeafRow]) -> dict:
    """从 1131 叶子构建预填。无叶子返回 {}。"""
    if not leaves:
        return {}
    buckets: dict[str, dict] = {}
    for leaf in leaves:
        cat = classify_g3_leaf(leaf.account_name, leaf.account_code)
        if cat not in buckets:
            buckets[cat] = {"opening": 0.0, "closing": 0.0, "codes": [], "names": []}
        buckets[cat]["opening"] += leaf.opening
        buckets[cat]["closing"] += leaf.closing
        buckets[cat]["codes"].append(leaf.account_code)
        if leaf.account_name and leaf.account_name not in buckets[cat]["names"]:
            buckets[cat]["names"].append(leaf.account_name)
    return {k: v for k, v in buckets.items() if v["opening"] != 0 or v["closing"] != 0}


# ─────────────────────────────────────────────────────────────────────────────
# 四表取数
# ─────────────────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取 1131 应收股利的四表数据。"""
    result: dict = {"tb_values": {}, "tb_source_codes": {}, "adjudication_prefill": {}}
    try:
        accounts = await resolve_report_line_accounts(ctx, G3_ACCOUNT_SPEC)

        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        query_prefixes = accounts.gross if accounts.gross else list(G3_ACCOUNT_SPEC.fallback_gross)
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

        parent = parent_totals(all_rows, query_prefixes[0] if len(query_prefixes) == 1 else "")
        parent_check = None
        if parent.get("closing", 0) != 0 or parent.get("opening", 0) != 0:
            leaf_sum = sum(r.closing for r in filtered_leaves)
            parent_check = {
                "leaf_sum": leaf_sum,
                "parent": parent.get("closing", 0),
                "diff": round(leaf_sum - parent.get("closing", 0), 2),
            }

        by_category = [
            {
                "account_code": leaf.account_code,
                "account_name": leaf.account_name,
                "category": classify_g3_leaf(leaf.account_name, leaf.account_code),
                "opening": leaf.opening,
                "closing": leaf.closing,
            }
            for leaf in filtered_leaves
        ]

        adjudication_prefill = build_g3_adjudication_prefill(filtered_leaves)

        source_codes = accounts.as_dict()
        source_codes["gross"] = [r.account_code for r in filtered_leaves]
        if parent_check:
            source_codes["parent_check"] = parent_check

        result["tb_values"] = {"opening": agg["opening"], "closing": agg["closing"], "by_category": by_category}
        result["tb_source_codes"] = source_codes
        result["adjudication_prefill"] = adjudication_prefill

    except Exception as e:  # noqa: BLE001
        logger.warning("G3 TB fetch failed: %s", e)

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
                "AND item_id LIKE 'G3-%' "
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
        logger.warning("G3 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": "1131",
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
        logger.warning("G3 render: project context 失败: %s", e)

    tb_data = await _fetch_tb_data(ctx)
    tb_values = tb_data["tb_values"]
    tb_source_codes = tb_data["tb_source_codes"]
    adjudication_prefill = tb_data["adjudication_prefill"]

    project_context["tb_source_codes"] = tb_source_codes
    project_context["tb_amount"] = tb_values.get("closing", 0) if tb_values else 0

    return {
        "component_type": "g3-dividend-receivable",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": "1131",
        "prefix": "G3",
        "tb_values": tb_values,
        "adjudication_prefill": adjudication_prefill,
        "tb_source_codes": tb_source_codes,
        "adjudicated_amount": adjudicated_amount,
    }
