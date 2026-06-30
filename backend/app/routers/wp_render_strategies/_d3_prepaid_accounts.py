"""D3 预收账款 — 专属渲染策略.

component_type = "d3-prepaid-accounts"
返回 html_data 含：审定表双区块配置 + 明细表列定义 + 各sheet元数据 + 项目上下文。
数据持久化在 checklist_responses 表，item_id前缀为 "D3-{sheetPrefix}-{field}"。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """D3 预收账款渲染策略.

    返回完整 html_data：
    - sections: 各sheet元数据配置
    - adjudication_config: 审定表双区块固定结构
    - project_context: 项目上下文
    - applicable_standards: 适用性标准判断
    - responses_snapshot: 关键item_id的已保存数据
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 审定表双区块结构 ──────────────────────────────────────────────────
    adjudication_config = {
        "nature_rows": [
            {"rowKey": "fixed-asset-sales", "label": "预收销售固定资产款"},
            {"rowKey": "land-use-right", "label": "预收销售土地使用权款"},
            {"rowKey": "contract-invalid", "label": "合同不成立时已收取的对价"},
            {"rowKey": "other", "label": "其他"},
        ],
        "aging_rows": [
            {"rowKey": "within-1-year", "label": "1年以内"},
            {"rowKey": "1-to-2-years", "label": "1至2年"},
            {"rowKey": "2-to-3-years", "label": "2至3年"},
            {"rowKey": "over-3-years", "label": "3年以上"},
        ],
    }

    # ─── sections 结构定义（9个Tab） ──────────────────────────────────────
    sections = [
        {"code": "D3A", "label": "D3A 程序表", "type": "procedure"},
        {"code": "D3-1", "label": "D3-1 审定表", "type": "adjudication"},
        {"code": "D3-2", "label": "D3-2 明细表", "type": "detail"},
        {"code": "D3-3", "label": "D3-3 调整分录", "type": "adjustment"},
        {"code": "D3-4", "label": "D3-4 分析表", "type": "analysis"},
        {"code": "D3-5", "label": "D3-5 长期检查", "type": "long_term"},
        {"code": "D3-6", "label": "D3-6 关联方", "type": "related_party"},
        {"code": "D3-7", "label": "D3-7 凭证检查", "type": "voucher_check"},
        {"code": "D3-NOTE", "label": "附注", "type": "disclosure"},
    ]

    # ─── 从 checklist_responses 加载关键数据快照 ──────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D3-%' "
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
        logger.warning("D3 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 + 适用性判断 ─────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "applicable_standards": "",
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category, applicable_standards "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = proj_row.business_category or ""
            project_context["applicable_standards"] = proj_row.applicable_standards or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("D3 render: project context 查询失败: %s", e)

    # 附注适用性
    standards = project_context["applicable_standards"].lower()
    disclosure_visibility = {
        "listed": "listed" in standards,
        "soe": "soe" in standards,
    }

    return {
        "sections": sections,
        "adjudication_config": adjudication_config,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
    }
