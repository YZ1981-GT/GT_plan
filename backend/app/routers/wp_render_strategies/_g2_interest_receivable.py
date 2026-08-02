"""G2 应收利息 — 专属渲染策略.

componentType: g2-interest-receivable

科目映射链路：
  标准科目 1132 应收利息（借方/资产类）。
  report_config 中无独立报表行（新准则下应收利息不单独列报，
  合并进其他应收款或债权投资的利息调整），故直接使用兜底码 1132。

G2-1 审定表三部分：
  一、应收利息原值（单项计提 + 按组合计提）
  二、应收利息坏账准备（镜像）
  三、应收利息净值（= 原值 - 坏账准备）

四表取数逻辑：
  1. 原值：tb_balance 1132 前缀叶子聚合
  2. 坏账准备：无独立标准码（1231 族没有单独的「应收利息坏账」映射），
     故从 tb_balance 查看 1132 子科目中是否有贷方性质（坏账准备）行，
     或者审定表由 G2-7 坏账测算表联动取数（源模板 E8 引用 G2-7!I16）
  3. 输出 tb_source_codes 供溯源面板
  4. 输出 adjudication_prefill 供审定表 seed
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

#: G2 应收利息无独立报表行（新准则下不单列），直接用 fallback
#: 选一个不存在的 row_code 让 resolve 必然 fallback（fail-open 设计）
G2_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-015",            # 「其中：应收利息」—— formula 通常为 None
    fallback_gross=("1132",),
    # 应收利息坏账准备：实务中可能挂在 1231 族，但无独立标准码映射
    # 底稿从 G2-7 坏账测算表联动取数，这里不做备抵预填
)

_ADJUDICATED_ITEM_ID = "G2-1-adjudicated-amount"

G2_INVEST_TYPES = [
    {"rowKey": "bond-interest", "label": "债权投资利息"},
    {"rowKey": "other-bond-interest", "label": "其他债权投资利息"},
    {"rowKey": "deposit-interest", "label": "定期存款利息"},
    {"rowKey": "other", "label": "其他"},
]


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数：叶子科目分类
# ─────────────────────────────────────────────────────────────────────────────


def classify_g2_leaf(name: str, code: str) -> str:
    """根据科目名称将应收利息子科目映射到利息来源分类。"""
    n = (name or "").lower()
    if any(kw in n for kw in ("债权投资", "持有至到期", "债券")):
        return "bond-interest"
    if any(kw in n for kw in ("其他债权", "可供出售")):
        return "other-bond-interest"
    if any(kw in n for kw in ("定期存款", "存款", "银行")):
        return "deposit-interest"
    return "other"



# ─────────────────────────────────────────────────────────────────────────────
# 四表取数
# ─────────────────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取 1132 应收利息的四表数据。"""
    result: dict = {"tb_values": {}, "tb_source_codes": {}, "adjudication_prefill": {}}

    try:
        accounts = await resolve_report_line_accounts(ctx, G2_ACCOUNT_SPEC)

        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        query_prefixes = accounts.gross if accounts.gross else list(G2_ACCOUNT_SPEC.fallback_gross)
        if not query_prefixes:
            return result

        # 构建查询条件（点号边界）
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
            leaf_sum_closing = sum(r.closing for r in filtered_leaves)
            parent_check = {
                "leaf_sum": leaf_sum_closing,
                "parent": parent.get("closing", 0),
                "diff": round(leaf_sum_closing - parent.get("closing", 0), 2),
            }

        # 分类
        by_category: list[dict] = []
        for leaf in filtered_leaves:
            category = classify_g2_leaf(leaf.account_name, leaf.account_code)
            by_category.append({
                "account_code": leaf.account_code,
                "account_name": leaf.account_name,
                "category": category,
                "opening": leaf.opening,
                "closing": leaf.closing,
            })


        source_codes = accounts.as_dict()
        # 审定表「从四表库带入未审数」统一载荷（逐叶子明细，归类在前端做）
        result["adjudication_prefill"] = build_g_adjudication_prefill(
            "G2", accounts, all_rows
        )
        source_codes["gross"] = [r.account_code for r in filtered_leaves]
        if parent_check:
            source_codes["parent_check"] = parent_check

        result["tb_values"] = {
            "opening": agg["opening"],
            "closing": agg["closing"],
            "by_category": by_category,
        }
        result["tb_source_codes"] = source_codes

    except Exception as e:  # noqa: BLE001
        logger.warning("G2 TB fetch failed: %s", e)

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
                "AND item_id LIKE 'G2-%' "
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
        logger.warning("G2 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": "1132",
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
        logger.warning("G2 render: project context 失败: %s", e)

    # 四表取数
    tb_data = await _fetch_tb_data(ctx)
    tb_values = tb_data["tb_values"]
    tb_source_codes = tb_data["tb_source_codes"]

    project_context["tb_source_codes"] = tb_source_codes
    project_context["tb_amount"] = tb_values.get("closing", 0) if tb_values else 0

    # sheet 列表（供目录使用）
    sheets_payload: list[dict] = []
    for cls in getattr(ctx, "classifications", None) or []:
        sn = getattr(cls, "sheet_name", None) or ""
        if not sn or "GT_Custom" in sn:
            continue
        sheets_payload.append({"sheet_name": sn})

    return {
        "component_type": "g2-interest-receivable",
        "invest_types": G2_INVEST_TYPES,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": "1132",
        "prefix": "G2",
        "tb_values": tb_values,
        "adjudication_prefill": tb_data["adjudication_prefill"],
        "tb_source_codes": tb_source_codes,
        "adjudicated_amount": adjudicated_amount,
        "sheets": sheets_payload,
    }
