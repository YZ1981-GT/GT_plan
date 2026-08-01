"""G8 其他权益工具投资 — 专属渲染策略.

componentType: g8-other-equity-instruments

科目映射链路（report_config DB 实证，四准则一致）：
  BS-025 其他权益工具投资 = TB('1506','期末余额')

G8-1 审定表：动态行（从 G8-2 明细表联动），按公允价值列示各投资项目。
无备抵（以公允价值计量且变动计入其他综合收益，信用风险由 G14 管理）。

四表取数：
  1. resolve_report_line_accounts → 标准码 1506
  2. tb_balance 叶子聚合 → tb_values / tb_source_codes / adjudication_prefill
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

G8_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-025",            # 其他权益工具投资，四准则一致 TB('1506','期末余额')
    fallback_gross=("1506",),
    # 无备抵（FVOCI 权益工具不计提减值准备）
)

_ADJUDICATED_ITEM_ID = "G8-1-adjudicated-amount"

G8_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "g8-other-equity-instruments"},
    {"sheet_name": "其他权益工具投资实质性程序表G8A", "component_type": "g8-other-equity-instruments"},
    {"sheet_name": "审定表G8-1", "component_type": "g8-other-equity-instruments"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "g8-other-equity-instruments"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "g8-other-equity-instruments"},
    {"sheet_name": "明细表G8-2", "component_type": "g8-other-equity-instruments"},
    {"sheet_name": "调整分录汇总G8-3", "component_type": "g8-other-equity-instruments"},
    {"sheet_name": "公允价值测试表G8-4", "component_type": "g8-other-equity-instruments"},
    {"sheet_name": "指定的适当性检查表G8-5", "component_type": "g8-other-equity-instruments"},
    {"sheet_name": "凭证检查表G8-6", "component_type": "g8-other-equity-instruments"},
    {"sheet_name": "参考中证协《非上市公司股权估值指引》", "component_type": "g8-other-equity-instruments"},
]


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数：叶子科目分类
# ─────────────────────────────────────────────────────────────────────────────


def classify_g8_leaf(name: str, code: str) -> str:
    """根据子科目名称分类 — 其他权益工具投资通常按被投资单位分设子科目。"""
    n = (name or "").lower()
    # 「非上市」必须先于「上市」（后者是前者的子串）
    if any(kw in n for kw in ("非上市", "未上市", "私募股权", "非流通")):
        return "unlisted-equity"
    if any(kw in n for kw in ("上市", "流通股", "a股", "h股")):
        return "listed-equity"
    if any(kw in n for kw in ("股权",)):
        return "unlisted-equity"
    if any(kw in n for kw in ("基金", "信托", "理财")):
        return "fund"
    return "other"


def build_g8_adjudication_prefill(leaves: list[LeafRow]) -> dict:
    """从 1506 叶子构建审定表预填。输出按被投资单位逐行（不分类）。"""
    if not leaves:
        return {}
    items: list[dict] = []
    for leaf in leaves:
        if leaf.opening != 0 or leaf.closing != 0:
            items.append({
                "account_code": leaf.account_code,
                "account_name": leaf.account_name,
                "category": classify_g8_leaf(leaf.account_name, leaf.account_code),
                "opening": leaf.opening,
                "closing": leaf.closing,
            })
    if not items:
        return {}
    return {
        "items": items,
        "total_opening": sum(i["opening"] for i in items),
        "total_closing": sum(i["closing"] for i in items),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 四表取数
# ─────────────────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取 1506 其他权益工具投资的四表数据。"""
    result: dict = {"tb_values": {}, "tb_source_codes": {}, "adjudication_prefill": {}}

    try:
        accounts = await resolve_report_line_accounts(ctx, G8_ACCOUNT_SPEC)

        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        query_prefixes = accounts.gross if accounts.gross else list(G8_ACCOUNT_SPEC.fallback_gross)
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

        adjudication_prefill = build_g8_adjudication_prefill(filtered_leaves)

        source_codes = accounts.as_dict()
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
                    "category": classify_g8_leaf(leaf.account_name, leaf.account_code),
                    "opening": leaf.opening,
                    "closing": leaf.closing,
                }
                for leaf in filtered_leaves
            ],
        }
        result["tb_source_codes"] = source_codes
        result["adjudication_prefill"] = adjudication_prefill

    except Exception as e:  # noqa: BLE001
        logger.warning("G8 TB fetch failed: %s", e)

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
            {"wp_id": str(ctx.wp_id), "pfx": "G8-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("G8 responses fetch failed: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": "1506",
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
        logger.warning("G8 render: project context 失败: %s", e)

    # 四表取数
    tb_data = await _fetch_tb_data(ctx)
    tb_values = tb_data["tb_values"]
    tb_source_codes = tb_data["tb_source_codes"]
    adjudication_prefill = tb_data["adjudication_prefill"]

    project_context["tb_source_codes"] = tb_source_codes
    project_context["tb_amount"] = tb_values.get("closing", 0) if tb_values else 0

    return {
        "account_code": "1506",
        "component_type": "g8-other-equity-instruments",
        "prefix": "G8",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        "tb_values": tb_values,
        "adjudication_prefill": adjudication_prefill,
        "tb_source_codes": tb_source_codes,
        # 兼容既有前端读 trial_balance 键
        "trial_balance": {
            "current_amount": tb_values.get("closing", 0),
            "debit_amount": 0,
            "credit_amount": 0,
        } if tb_values else {},
        "sheets": G8_SHEETS,
    }
