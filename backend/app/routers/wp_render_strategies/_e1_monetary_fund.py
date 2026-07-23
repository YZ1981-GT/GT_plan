"""E1 货币资金 — 专属渲染策略.

component_type = "e1-monetary-fund"

E1 前端组件 GtE1MonetaryFund 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/现金明细/银行明细/盘点/截止测试/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 E1 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "E1-*"。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """E1 货币资金渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtE1MonetaryFund，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 E1-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'E1-%' "
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
        logger.warning("E1 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
        "bs_date": "",
        "tb_amount": 0,
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
            # bs_date（资产负债表日）
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 render: project context 查询失败: %s", e)

    # ─── 试算平衡表 1001+1002+1012 货币资金（资产借方）─────────────────
    year = project_context.get("audit_year")
    if year:
        try:
            tb_row = (
                await db.execute(
                    sa.text(
                        "SELECT COALESCE(SUM(audited_amount), 0) AS audited, "
                        "COALESCE(SUM(unadjusted_amount), 0) AS unadjusted "
                        "FROM trial_balance "
                        "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                        "AND (standard_account_code LIKE '1001%' "
                        "OR standard_account_code LIKE '1002%' "
                        "OR standard_account_code LIKE '1012%')"
                    ),
                    {"pid": str(ctx.project_id), "year": int(year)},
                )
            ).fetchone()
            if tb_row:
                audited = float(tb_row.audited or 0)
                unadjusted = float(tb_row.unadjusted or 0)
                project_context["tb_amount"] = audited if audited else unadjusted
        except Exception as e:  # noqa: BLE001
            logger.warning("E1 render: trial_balance(1001/1002/1012) 查询失败: %s", e)

    # ─── 关联方清单 ──────────────────────────────────────────────────────
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
        logger.warning("E1 render: related_parties 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }
