"""G9 其他非流动金融资产 — 专属渲染策略.

componentType: g9-other-noncurrent-financial

科目映射链路（**语义驱动、逐项目**，单一真源 `four_table/g_cycle_specs.G9_SPEC`）：
  槽「其他非流动金融资产」→ 真值标准码 **1519**

🔴 `report_config` 的 ``BS-026 = TB('1507')`` **是错码**（1507 实为「其他权益工具投资」，
连续偏移一位）。且 `1519` 只在 4 个项目的标准科目表里 —— 另 6 个项目解析为空，
届时 `adjudication_prefill` 返 ``{}``，前端显示「四表库暂无该科目数据」（正确行为）。

G9-1 审定表：动态行（从 G9-2 明细表联动），按公允价值列示各投资项目。
无备抵（以公允价值计量，不计提减值准备；信用减值由 G14 管理）。
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
from app.services.four_table.g_cycle_specs import G9_SPEC

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 科目定位规格
# ─────────────────────────────────────────────────────────────────────────────

#: 🔴 科目定位改走**语义驱动**（单一真源 `four_table/g_cycle_specs.G9_SPEC`）。
#:
#: 原用 ``fallback_gross=("1507",)`` + `report_config` 的 ``BS-026 = TB('1507')`` ——
#: 两者都错：`account_chart` + `trial_balance.account_name` 双证 **``1507`` 实为
#: 「其他权益工具投资」（G8 的科目）**，其他非流动金融资产的真实科目是 **``1519``**。
#: 且 ``1519`` 只在 4 个项目的标准科目表里 → 另 6 个项目解析为空是**正确行为**
#: （写死任何码都会在这些项目里静默产出 0）。
#: 无备抵槽（FVTPL / FVOCI 计量，不单独计提减值）。
G9_ACCOUNT_SPEC = G9_SPEC

_ADJUDICATED_ITEM_ID = "G9-1-adjudicated-amount"

G9_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "其他非流动金融资产实质性程序表G9A", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "审定表G9-1", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "明细表G9-2", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "调整分录汇总G9-3", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "公允价值测试表G9-4", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "第三层次公允价值计量的调节表G9-5", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "凭证检查表G9-6", "component_type": "g9-other-noncurrent-financial"},
]


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数：叶子科目分类
# ─────────────────────────────────────────────────────────────────────────────


def classify_g9_leaf(name: str, code: str) -> str:
    """根据子科目名称分类其他非流动金融资产。"""
    n = (name or "").lower()
    if any(kw in n for kw in ("债权", "债务工具", "债券")):
        return "debt-instrument"
    if any(kw in n for kw in ("非上市", "未上市", "私募")):
        return "unlisted-equity"
    if any(kw in n for kw in ("股权", "股票", "权益")):
        return "equity-instrument"
    if any(kw in n for kw in ("基金", "信托", "理财")):
        return "fund"
    return "other"



# ─────────────────────────────────────────────────────────────────────────────
# 四表取数
# ─────────────────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取 1507 其他非流动金融资产的四表数据。"""
    result: dict = {"tb_values": {}, "tb_source_codes": {}, "adjudication_prefill": {}}

    try:
        accounts = await resolve_semantic_accounts(ctx, G9_ACCOUNT_SPEC)

        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        # 本项目无「其他非流动金融资产」科目时返空（宁缺勿造，不退化为宽前缀）
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
            "G9", accounts, all_rows
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
                    "category": classify_g9_leaf(leaf.account_name, leaf.account_code),
                    "opening": leaf.opening,
                    "closing": leaf.closing,
                }
                for leaf in filtered_leaves
            ],
        }
        result["tb_source_codes"] = source_codes

    except Exception as e:  # noqa: BLE001
        logger.warning("G9 TB fetch failed: %s", e)

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
            {"wp_id": str(ctx.wp_id), "pfx": "G9-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("G9 responses fetch failed: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": "1507",
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
        logger.warning("G9 render: project context 失败: %s", e)

    # 四表取数
    tb_data = await _fetch_tb_data(ctx)
    tb_values = tb_data["tb_values"]
    tb_source_codes = tb_data["tb_source_codes"]

    project_context["tb_source_codes"] = tb_source_codes
    project_context["tb_amount"] = tb_values.get("closing", 0) if tb_values else 0

    return {
        "account_code": "1507",
        "component_type": "g9-other-noncurrent-financial",
        "prefix": "G9",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        "tb_values": tb_values,
        "adjudication_prefill": tb_data["adjudication_prefill"],
        "tb_source_codes": tb_source_codes,
        # 兼容既有前端读 trial_balance 键
        "trial_balance": {
            "current_amount": tb_values.get("closing", 0),
            "debit_amount": 0,
            "credit_amount": 0,
        } if tb_values else {},
        "sheets": G9_SHEETS,
    }
