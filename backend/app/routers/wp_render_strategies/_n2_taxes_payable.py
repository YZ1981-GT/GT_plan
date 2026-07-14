"""N2 应交税费 — 专属渲染策略.

component_type = "n2-taxes-payable"

N2 前端组件 GtN2TaxesPayable 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/增值税测算/其他税费测算/房产税/土增税/出口退税等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 N2 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目2221应交税费（**贷方/负债类科目**）：期末=期初+贷方-借方
N税费循环最复杂底稿（18 sheet/~180+公式）。
多税种测算引擎：增值税/城建税及附加/房产税/土地增值税/出口退税。
数据持久化在 checklist_responses 表，item_id 前缀为 "N2-*"。

Requirements: 1.6
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

_N2_ACCOUNT_CODE = "2221"
_ADJUDICATED_ITEM_ID = "N2-1-adjudicated-amount"

N2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费审计程序表N2A", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费审定表N2-1", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费明细表N2-2", "component_type": "n2-taxes-payable"},
    {"sheet_name": "调整分录汇总N2-3", "component_type": "n2-taxes-payable"},
    {"sheet_name": "税收政策检查N2-4", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税金认定表N2-5", "component_type": "n2-taxes-payable"},
    {"sheet_name": "增值税测算表N2-6", "component_type": "n2-taxes-payable"},
    {"sheet_name": "出口退税核对表N2-7", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交其他税费测算表N2-8", "component_type": "n2-taxes-payable"},
    {"sheet_name": "房产税测算表N2-9", "component_type": "n2-taxes-payable"},
    {"sheet_name": "土地增值税测算表N2-10", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费检查表N2-11", "component_type": "n2-taxes-payable"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "n2-taxes-payable"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "n2-taxes-payable"},
]


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f  # NaN→0.0
    except (ValueError, TypeError):
        return 0.0


# ─── TB 取数（负债类！期末余额）──────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict[str, Any]:
    """从 tb_balance 取科目2221应交税费余额数据（负债类贷方）."""
    result: dict[str, Any] = {
        "account_code": _N2_ACCOUNT_CODE,
        "account_name": "应交税费",
        "direction": "credit",
        "begin_balance": 0,
        "debit_amount": 0,
        "credit_amount": 0,
        "end_balance": 0,
    }
    try:
        active_filter = get_active_filter(ctx.project_id)
        stmt = (
            sa.select(
                TbBalance.begin_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.end_balance,
            )
            .where(
                TbBalance.project_id == str(ctx.project_id),
                TbBalance.standard_account_code == _N2_ACCOUNT_CODE,
                active_filter,
            )
            .limit(1)
        )
        row = (await ctx.db.execute(stmt)).fetchone()
        if row:
            result["begin_balance"] = _parse_num(row.begin_balance)
            result["debit_amount"] = _parse_num(row.debit_amount)
            result["credit_amount"] = _parse_num(row.credit_amount)
            result["end_balance"] = _parse_num(row.end_balance)
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 render: TB 取数失败: %s", e)
    return result


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any]:
    """N2 应交税费专属渲染策略.

    轻量返回：project_context + responses_snapshot + TB数据。
    前端 GtN2TaxesPayable 为自加载组件（各子组件独立拉取 checklist_responses）。
    """
    # ─── 读取 checklist_responses 快照（列名对齐 schema: wp_id/conclusion/remark） ───
    responses_snapshot: dict[str, Any] = {}
    adjudicated_amount: float | None = None
    try:
        rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT item_id, conclusion, remark "
                    "FROM checklist_responses "
                    "WHERE wp_id = :wid"
                ),
                {"wid": str(ctx.wp_id)},
            )
        ).fetchall()
        for r in rows:
            responses_snapshot[r.item_id] = {
                "item_id": r.item_id,
                "conclusion": r.conclusion,
                "remark": r.remark,
            }
        # 提取审定数
        if _ADJUDICATED_ITEM_ID in responses_snapshot:
            raw_adj = responses_snapshot[_ADJUDICATED_ITEM_ID].get("conclusion")
            if raw_adj is not None:
                adjudicated_amount = _parse_num(raw_adj)
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 render: checklist_responses 查询失败: %s", e)

    # ─── 项目上下文 ────────────────────────────────────────────────────
    project_context: dict[str, str] = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
    }
    try:
        proj_row = (
            await ctx.db.execute(
                sa.text(
                    "SELECT client_name, audit_year, business_category "
                    "FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = (
                proj_row.business_category or ctx.business_category or ""
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 render: project context 查询失败: %s", e)

    # ─── TB 取数（科目2221应交税费，贷方/负债类）────────────────────
    tb = await _fetch_tb_data(ctx)

    return {
        "account_code": _N2_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # TB 余额数据（科目2221，贷方/负债类）
        "trial_balance": tb,
        # 负债类公式方向元数据
        "formula_direction": {
            "account_code": "2221",
            "account_name": "应交税费",
            "direction": "credit",  # 贷方/负债类！
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
            "note": (
                "负债类贷方科目：应交税费增加在贷方（计提时贷记2221），"
                "缴纳时借方减少。N税费循环最复杂底稿，涵盖增值税/城建税/"
                "教育费附加/房产税/土地增值税/出口退税多个税种。"
            ),
        },
        # N2 特有元数据
        "n2_metadata": {
            "engine": "multi_tax",
            "vat_formula": "payable_vat = output_vat - (input_vat - input_transfer_out)",
            "surtax_formula": "surtax = (vat + consumption_tax) × rate",
            "property_tax_by_value": "original_value × (1 - deduct_rate) × 1.2%",
            "property_tax_by_rent": "rent_income × 12%",
            "lvt_formula": "appreciation × rate - deduct_items × quick_deduct_coef",
            "cross_wp_links": ["N4", "L8"],
        },
        # sheet 列表元数据
        "sheets": N2_SHEETS,
        "component_type": "n2-taxes-payable",
    }
