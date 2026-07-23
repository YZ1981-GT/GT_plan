"""F4 应付账款 — 专属渲染策略.

componentType: f4-accounts-payable
科目2202应付账款（贷方/负债类）
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

F4_SHEETS = [
    "F4A",
    "F4-1",
    "附注披露(上市)",
    "附注披露(国企)",
    "F4-2",
    "F4-3",
    "F4-4",
    "F4-5",
    "F4-6",
    "F4-7",
    "F4-8",
    "F4-9",
]


async def render(ctx: RenderContext) -> dict | None:
    db = ctx.db
    wp_id = str(ctx.wp_id)

    # ─── checklist_responses 快照 ────────────────────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND (item_id LIKE :pfx OR item_id LIKE 'F4A%') LIMIT 800"
            ),
            {"wp_id": wp_id, "pfx": "F4-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:
        logger.warning("F4 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文（client_name / audit_year / bs_date / related_parties） ─
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
        "bs_date": "",
        "related_parties": [],
        "tb_amount": 0,
        "tb_amount_unadjusted": 0,
        "tb_amount_audited": 0,
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
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("F4 render: project context 查询失败: %s", e)

    # ─── 关联方清单（related_party_registry） ────────────────────────────
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
        logger.warning("F4 render: related_parties 查询失败: %s", e)

    # ─── 试算平衡表 2202 应付账款（贷方，取绝对值）──────────────────────
    year = project_context.get("audit_year")
    if year:
        try:
            tb_row = (
                await db.execute(
                    sa.text(
                        "SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadjusted, "
                        "COALESCE(SUM(audited_amount), 0) AS audited "
                        "FROM trial_balance "
                        "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                        "AND standard_account_code LIKE '2202%'"
                    ),
                    {"pid": str(ctx.project_id), "year": int(year)},
                )
            ).fetchone()
            if tb_row:
                unadjusted = abs(float(tb_row.unadjusted or 0))
                audited = abs(float(tb_row.audited or 0))
                project_context["tb_amount"] = audited if audited else unadjusted
                project_context["tb_amount_unadjusted"] = unadjusted
                project_context["tb_amount_audited"] = audited
        except Exception as e:  # noqa: BLE001
            logger.warning("F4 render: trial_balance(2202) 查询失败: %s", e)

    return {
        "component_type": "f4-accounts-payable",
        "account_code": "2202",
        "prefix": "F4",
        "sheets": F4_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }
