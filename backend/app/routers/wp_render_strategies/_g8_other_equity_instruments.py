"""G8 其他权益工具投资 — 专属渲染策略.

componentType: g8-other-equity-instruments

科目映射链路（**语义驱动、逐项目**，单一真源 `four_table/g_cycle_specs.G8_SPEC`）：
  槽「其他权益工具投资」→ 真值标准码 **1507**

🔴 `report_config` 的 ``BS-025 = TB('1506')`` **是错码**（1506 实为「其他债权投资」，
连续偏移一位），故本文件不再按报表公式取码，改按科目名在本项目 `account_chart` 里定位。

G8-1 审定表：动态行（从 G8-2 明细表联动），按公允价值列示各投资项目。
无备抵（以公允价值计量且变动计入其他综合收益，信用风险由 G14 管理）。

四表取数：
  1. resolve_semantic_accounts(G8_SPEC) → 本项目实际存在的原始码前缀集
  2. tb_balance 叶子聚合 → tb_values / tb_source_codes
  3. build_g_adjudication_prefill → adjudication_prefill（逐叶子明细，归类在前端）
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
from app.services.four_table.g_cycle_specs import G8_SPEC

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 科目定位规格
# ─────────────────────────────────────────────────────────────────────────────

#: 🔴 科目定位改走**语义驱动**（单一真源 `four_table/g_cycle_specs.G8_SPEC`）。
#:
#: 原用 ``fallback_gross=("1506",)`` + `report_config` 的 ``BS-025 = TB('1506')`` ——
#: 两者都错：`account_chart` + `trial_balance.account_name` 双证 **``1506`` 实为
#: 「其他债权投资」（G6 的科目）**，其他权益工具投资的真实科目是 **``1507``**。
#: 根因是 `report_config` 的 BS-022/025/026 连续偏移一位（平台在 1504 与 1506 之间
#: 插了 `1505 债权投资减值准备`，且其他非流动金融资产跳到 1519）。
#: 无备抵槽（FVOCI 权益工具不计提减值准备）
G8_ACCOUNT_SPEC = G8_SPEC

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



# ─────────────────────────────────────────────────────────────────────────────
# 四表取数
# ─────────────────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取 1506 其他权益工具投资的四表数据。"""
    result: dict = {"tb_values": {}, "tb_source_codes": {}, "adjudication_prefill": {}}

    try:
        accounts = await resolve_semantic_accounts(ctx, G8_ACCOUNT_SPEC)

        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        # 本项目无「其他权益工具投资」科目时返空（宁缺勿造，不退化为宽前缀）
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
            "G8", accounts, all_rows
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
                    "category": classify_g8_leaf(leaf.account_name, leaf.account_code),
                    "opening": leaf.opening,
                    "closing": leaf.closing,
                }
                for leaf in filtered_leaves
            ],
        }
        result["tb_source_codes"] = source_codes

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
        "adjudication_prefill": tb_data["adjudication_prefill"],
        "tb_source_codes": tb_source_codes,
        # 兼容既有前端读 trial_balance 键
        "trial_balance": {
            "current_amount": tb_values.get("closing", 0),
            "debit_amount": 0,
            "credit_amount": 0,
        } if tb_values else {},
        "sheets": G8_SHEETS,
    }
