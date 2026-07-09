"""C24 会计分录细节测试 — 专属渲染策略.

component_type = "c24-journal-entry-detail"

C24 前端组件 GtC24JournalDetail 为自加载组件（子 sheet 各自拉取 checklist-responses），
按 sheetName v-if 分发到各渲染模式（C24A 程序表 / C24-0 汇总 / C24-1 借贷发生额 /
C24-2 科目余额对比 / C24-3 跳号 / C24-4 异常账户 / C24-5 异常分录 / 本福特 /
本福特-数据 / 假期清单）。

本渲染策略的关键作用（对齐 render_c1_entity_control）：
让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch 循环把 C24
各 sheet 误判为非白名单而重写成 onlyoffice-sheet（铁律：D~N/专属组件必须注册）。

返回轻量 html_data（project_context + responses_snapshot + journal_entries 缓存摘要），
前端组件自行消费。C24 的分录明细导入导出走独立端点（_c24_import_export.py）。

数据持久化在 checklist_responses 表，item_id 前缀为 "C24-*"。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """C24 会计分录细节测试渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtC24JournalDetail，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 C24-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    journal_entry_count = 0
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'C24-%' "
                "LIMIT 5000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            # 统计已导入分录数量
            if row.item_id == "C24-journal-source" and row.remark:
                try:
                    meta = json.loads(row.remark)
                    if isinstance(meta, dict) and meta.get("count") is not None:
                        journal_entry_count = int(meta["count"])
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            elif row.item_id == "C24-journal-entries" and row.remark:
                try:
                    entries = json.loads(row.remark)
                    if isinstance(entries, list):
                        journal_entry_count = len(entries)
                except (json.JSONDecodeError, TypeError):
                    pass
    except Exception as e:  # noqa: BLE001
        logger.warning("C24 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("C24 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "journal_entry_count": journal_entry_count,
    }
