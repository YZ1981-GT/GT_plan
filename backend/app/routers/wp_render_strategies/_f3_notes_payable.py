"""F3 应付票据 — 专属渲染策略."""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

F3_SHEETS = [
    "F3A",
    "F3-1",
    "F3-2",
    "F3-3",
    "F3-4",
    "F3-5",
    "F3-6",
    "F3-7",
    "附注披露信息(上市公司)",
    "附注披露信息(国企)",
]

_F3_ACCOUNT = "2201"


async def _fetch_f3_2201_audited(ctx: RenderContext) -> float | None:
    """从 trial_balance(v2 正数口径) 取 2201 审定数(无则未审数)，供 F3-1 试算核对预填."""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT unadjusted_amount, audited_amount "
                "FROM trial_balance "
                "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                "AND standard_account_code LIKE '2201%'"
            ),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        audited = 0.0
        unadjusted = 0.0
        found = False
        for row in result.fetchall():
            found = True
            audited += float(row.audited_amount or 0)
            unadjusted += float(row.unadjusted_amount or 0)
        if not found:
            return None
        return audited if abs(audited) > 1e-9 else unadjusted
    except Exception as e:  # noqa: BLE001
        logger.warning("F3 render: trial_balance 2201 取数失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return None


async def _fetch_f3_2201_tb_balance(ctx: RenderContext) -> float | None:
    """回退：从 tb_balance(v1 借正贷负) 取 2201 期末余额，负债取绝对值供正数展示."""
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )
        result = await ctx.db.execute(
            sa.select(TbBalance.account_code, TbBalance.closing_balance).where(active_filter)
        )
        total = 0.0
        found = False
        for row in result.fetchall():
            code = str(row.account_code or "")
            if code == _F3_ACCOUNT or code.startswith(_F3_ACCOUNT):
                total += float(row.closing_balance or 0)
                found = True
        return abs(total) if found else None
    except Exception as e:  # noqa: BLE001
        logger.warning("F3 render: tb_balance 2201 取数失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return None


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND (item_id LIKE :pfx OR item_id LIKE 'F3A%') LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "F3-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:
        logger.warning("F3 render failed: %s", e)

    # 项目上下文
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
        "bs_date": "",
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
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("F3 render: project context 查询失败: %s", e)

    # P0-4：F3-1 审定表试算核对数(2201) 预填 —— 优先 trial_balance 审定/未审，回退 tb_balance 期末。
    tb_values: dict = {}
    seed = await _fetch_f3_2201_audited(ctx)
    if seed is None:
        seed = await _fetch_f3_2201_tb_balance(ctx)
    if seed is not None and abs(seed) > 1e-9:
        tb_values["2201"] = round(seed, 2)

    return {
        "component_type": "f3-notes-payable",
        "account_code": _F3_ACCOUNT,
        "prefix": "F3",
        "sheets": F3_SHEETS,
        "project_context": project_context,
        "tb_values": tb_values,
        "responses_snapshot": responses_snapshot,
    }
