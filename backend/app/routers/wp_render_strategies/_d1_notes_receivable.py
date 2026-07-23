"""D1 应收票据 — 专属渲染策略.

component_type = "d1-notes-receivable"

D1 前端组件 GtD1NotesReceivable 为自加载组件（onMounted 调 checklist-responses
自行拉取数据），按 sheetName 分发到各子组件（审定表/明细/坏账/业务模式/备查簿/
贴现背书/贴息/附注等）。因此本渲染策略只需返回轻量 html_data（project_context +
responses_snapshot），关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，
避免多 sheet dispatch 循环把 D1 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "D1-*"。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """D1 应收票据渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtD1NotesReceivable，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 D1-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D1-%' "
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
        logger.warning("D1 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
        "bs_date": "",
        "related_parties": [],
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
            # bs_date（资产负债表日）：审计年度 → {year}-12-31，供 D1-3 期后回款/抽凭/截止取数使用
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("D1 render: project context 查询失败: %s", e)

    # 关联方清单：从关联方登记表（RelatedPartyRegistry）取项目级名单，供 D1-3 客户明细表关联方识别
    try:
        rp_rows = (
            await db.execute(
                sa.text(
                    "SELECT name FROM related_party_registry "
                    "WHERE project_id = :pid AND is_deleted = false "
                    "AND name IS NOT NULL AND name <> ''"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchall()
        project_context["related_parties"] = [r.name for r in rp_rows if r.name]
    except Exception as e:  # noqa: BLE001
        logger.warning("D1 render: related_parties 查询失败: %s", e)

    # 试算平衡表应收票据（科目 1121）未审/审定合计：供 D1-1 审定表试算平衡差异行预填 tb_amount，
    # 使审计师无需手工录入即可看到与 TB 的勾稽差异（审定行仍由 D1-2 明细带入，此处仅锚定 TB 数）。
    try:
        tb_row = (
            await db.execute(
                sa.text(
                    "SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadjusted, "
                    "COALESCE(SUM(audited_amount), 0) AS audited "
                    "FROM trial_balance "
                    "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                    "AND standard_account_code LIKE '1121%'"
                ),
                {"pid": str(ctx.project_id), "year": ctx.year},
            )
        ).fetchone()
        if tb_row:
            audited = float(tb_row.audited or 0)
            unadjusted = float(tb_row.unadjusted or 0)
            # 审定优先；审定为 0 时回退未审（TB 尚未回写审定数的场景）
            project_context["tb_amount"] = audited if audited else unadjusted
            project_context["tb_amount_unadjusted"] = unadjusted
            project_context["tb_amount_audited"] = audited
    except Exception as e:  # noqa: BLE001
        logger.warning("D1 render: trial_balance(1121) 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }
