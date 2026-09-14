"""C1 企业层面控制测试 — 专属渲染策略.

component_type = "c1-entity-level-control"

C1 前端组件 GtC1EntityControl 为自加载组件（子 sheet 各自拉取 checklist-responses），
按 sheetName v-if 分发到各渲染模式（program 九段程序中控台 / example 示例只读 /
fr-summary 财报内控汇总 / process-record 过程记录表 + C1-4-4 样本借贷勾稽）。
因此本渲染策略只需返回轻量 html_data（project_context + section_groups + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 C1 各 sheet 误判为非白名单而重写成 onlyoffice-sheet（铁律：D~N/专属组件必须注册）。

数据持久化在 checklist_responses 表，item_id 前缀为 "C1-*"（详见 phase0-notes 第 6 节）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


# ─── 主程序表九段分组（Phase0 实测：源模板为九段而非 COSO 五段） ──────────
# slug / 中文标题 / 是否默认适用 —— 供前端九段折叠中控台与 item_id key 使用。
C1_SECTION_GROUPS: list[dict] = [
    {"slug": "ce", "title": "控制环境", "defaultApplicable": True},
    {"slug": "ra", "title": "风险评估", "defaultApplicable": True},
    {"slug": "mo", "title": "监督", "defaultApplicable": True},
    {"slug": "bu", "title": "监控业务单元", "defaultApplicable": False},  # 集团审计才适用
    {"slug": "ic", "title": "信息与沟通", "defaultApplicable": True},
    {"slug": "fr", "title": "财务报告", "defaultApplicable": True},
    {"slug": "el", "title": "对业务层面控制的影响", "defaultApplicable": True},
    {"slug": "ye", "title": "年终程序", "defaultApplicable": True},
    {"slug": "rp", "title": "关联方相关内容", "defaultApplicable": False},  # 有关联方交易才适用
]


async def render(ctx: RenderContext) -> dict | None:
    """C1 企业层面控制测试渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtC1EntityControl，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 C1-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'C1-%' "
                "LIMIT 1000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("C1 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
    }
    try:
        proj_row = (
            await db.execute(
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
        logger.warning("C1 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "section_groups": C1_SECTION_GROUPS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }
