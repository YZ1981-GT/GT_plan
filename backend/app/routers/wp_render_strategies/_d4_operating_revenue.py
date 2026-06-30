"""D4 营业收入 — 专属渲染策略.

component_type = "d4-operating-revenue"
返回 html_data 含：sections结构 / visible_groups（基于business_category）/ sheet配置。
数据持久化在 checklist_responses 表，item_id前缀为 "D4-{sheetCode}-{field}"。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# IPO/舞弊组可见性关键字
_IPO_KEYWORDS = ("ipo", "listed", "neeq", "restructuring", "fraud_risk")


def _is_ipo_visible(business_category: str) -> bool:
    """判断IPO/舞弊组一级Tab是否可见"""
    if not business_category:
        return False
    bc_lower = business_category.lower()
    return any(kw in bc_lower for kw in _IPO_KEYWORDS)


async def render(ctx: RenderContext) -> dict | None:
    """D4 营业收入渲染策略.

    返回完整 html_data：
    - sections: 7组嵌套Tab结构配置
    - visible_groups: 各组可见性标记
    - project_context: 项目上下文
    - responses_snapshot: 关键item_id的已保存数据
    """
    wp_id = ctx.wp_id
    db = ctx.db
    business_category = ctx.business_category or ""

    # ─── 可见性判断 ────────────────────────────────────────────────────────
    ipo_visible = _is_ipo_visible(business_category)

    visible_groups = {
        "core": True,
        "policy": True,
        "analysis": True,
        "inspection": True,
        "related": True,
        "ipo": ipo_visible,
        "other": True,
    }

    # ─── sections 结构定义 ─────────────────────────────────────────────────
    sections = [
        {
            "key": "core",
            "label": "核心",
            "sheets": [
                {"code": "D4-INDEX", "label": "底稿目录"},
                {"code": "D4-1", "label": "审定表"},
                {"code": "D4-2", "label": "主营明细"},
                {"code": "D4-3", "label": "其他明细"},
                {"code": "D4-4", "label": "调整分录"},
                {"code": "D4-NOTE-LISTED", "label": "附注(上市)"},
                {"code": "D4-NOTE-SOE", "label": "附注(国企)"},
            ],
        },
        {
            "key": "policy",
            "label": "政策",
            "sheets": [
                {"code": "D4-5", "label": "会计政策检查"},
            ],
        },
        {
            "key": "analysis",
            "label": "分析程序",
            "sheets": [
                {"code": "D4-6", "label": "重要指标"},
                {"code": "D4-7", "label": "毛利率月度"},
                {"code": "D4-8", "label": "产品毛利"},
                {"code": "D4-9", "label": "客户结构"},
                {"code": "D4-10", "label": "客户价格"},
                {"code": "D4-11", "label": "产品价格"},
            ],
        },
        {
            "key": "inspection",
            "label": "检查程序",
            "sheets": [
                {"code": "D4-12", "label": "合同检查"},
                {"code": "D4-13", "label": "ERP核对"},
                {"code": "D4-14", "label": "发生检查"},
                {"code": "D4-15", "label": "完整性检查"},
                {"code": "D4-16", "label": "出口核对"},
                {"code": "D4-17", "label": "截止(正向)"},
                {"code": "D4-18", "label": "截止(反向)"},
                {"code": "D4-19", "label": "折扣折让"},
                {"code": "D4-20", "label": "退货检查"},
            ],
        },
        {
            "key": "related",
            "label": "关联方",
            "sheets": [
                {"code": "D4-21", "label": "关联价格分析"},
            ],
        },
        {
            "key": "ipo",
            "label": "IPO/舞弊",
            "sheets": [
                {"code": "D4-22A", "label": "IPO程序表"},
                {"code": "D4-22", "label": "IPO指标"},
                {"code": "D4-23", "label": "发票对比"},
                {"code": "D4-24", "label": "第三方回款"},
                {"code": "D4-25", "label": "经销商"},
                {"code": "D4-26", "label": "境外销售"},
                {"code": "D4-27", "label": "未披露关联方"},
                {"code": "D4-28", "label": "核查清单"},
                {"code": "D4-29", "label": "核查详细"},
                {"code": "D4-30", "label": "访谈汇总"},
                {"code": "D4-31", "label": "访谈详细"},
                {"code": "D4-32", "label": "资金流水"},
            ],
        },
        {
            "key": "other",
            "label": "其他收入",
            "sheets": [
                {"code": "D4-33", "label": "其他毛利"},
                {"code": "D4-34", "label": "合同测算"},
                {"code": "D4-35", "label": "其他检查"},
                {"code": "D4-36", "label": "其他截止"},
            ],
        },
    ]

    # ─── 从 checklist_responses 加载关键数据快照 ──────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D4-%' "
                "LIMIT 500"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("D4 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": business_category,
        "applicable_standards": "",
        "has_export_business": False,
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = proj_row.business_category or business_category
    except Exception as e:  # noqa: BLE001
        logger.warning("D4 render: project context 查询失败: %s", e)

    return {
        "sections": sections,
        "visible_groups": visible_groups,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }
