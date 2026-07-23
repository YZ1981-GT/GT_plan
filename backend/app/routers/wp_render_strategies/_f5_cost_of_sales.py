"""F5 主营业务成本 — 专属渲染策略.

除返回 checklist 快照外，为 F5-7 成本倒轧表自动取数：
- 1401 原材料 / 1404 在产品 / 1405 产成品 的期初/期末余额（tb_balance）
供前端 F5-7 校验区只读字段 seed。

P0 改进(2026-07-22)：
- 补 project_context（client_name/audit_year/bs_date/related_parties）
- 补 tb_amount_6401（trial_balance 6401 发生额，供 F5-1 TB预填）
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 成本倒轧 TB 取数科目（前缀匹配，兼容明细科目如 140101）
_ROLLFORWARD_ACCOUNTS = {
    "1401": ("openingMaterial", "closingMaterial"),  # 原材料
    "1404": ("openingWIP", "closingWIP"),            # 在产品
    "1405": ("openingFG", "closingFG"),              # 产成品
}


async def _fetch_rollforward_tb(ctx: RenderContext) -> dict:
    """取 1401/1404/1405 期初/期末余额，按父科目前缀聚合。"""
    tb: dict[str, float] = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
            ).where(active_filter)
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            for prefix, (open_key, close_key) in _ROLLFORWARD_ACCOUNTS.items():
                if code == prefix or code.startswith(prefix):
                    tb[open_key] = tb.get(open_key, 0.0) + float(row.opening_balance or 0)
                    tb[close_key] = tb.get(close_key, 0.0) + float(row.closing_balance or 0)
                    break
    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("F5 rollforward TB fetch failed: %s", e)
    return tb


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    adjudicated_cogs = ""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "F5-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
        # F5-7 校验区回退：读取已持久化的审定营业成本
        adjudicated_cogs = responses_snapshot.get("F5-7-adjudicated-cogs", {}).get("remark", "")
    except Exception as e:  # noqa: BLE001
        logger.warning("F5 render failed: %s", e)

    rollforward_tb = await _fetch_rollforward_tb(ctx)

    # ─── project_context（client_name / audit_year / bs_date / related_parties） ─
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "bs_date": "",
        "related_parties": [],
        "tb_amount": 0,
        "tb_amount_unadjusted": 0,
        "tb_amount_audited": 0,
    }
    try:
        proj_row = (
            await ctx.db.execute(
                sa.text(
                    "SELECT client_name, audit_year "
                    "FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("F5 render: project context failed: %s", e)

    # ─── 关联方清单 ──────────────────────────────────────────────────────
    try:
        rp_rows = (
            await ctx.db.execute(
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
        logger.warning("F5 render: related_parties failed: %s", e)

    # ─── 试算平衡表 6401 营业成本（借方/损益类，发生额=unadjusted/audited） ──
    year = project_context.get("audit_year")
    if year:
        try:
            tb_row = (
                await ctx.db.execute(
                    sa.text(
                        "SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadjusted, "
                        "COALESCE(SUM(audited_amount), 0) AS audited "
                        "FROM trial_balance "
                        "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                        "AND standard_account_code LIKE '6401%'"
                    ),
                    {"pid": str(ctx.project_id), "year": int(year)},
                )
            ).fetchone()
            if tb_row:
                unadjusted = float(tb_row.unadjusted or 0)
                audited = float(tb_row.audited or 0)
                # 损益借方科目：正数=发生额，无需取绝对值
                project_context["tb_amount"] = audited if audited else unadjusted
                project_context["tb_amount_unadjusted"] = unadjusted
                project_context["tb_amount_audited"] = audited
        except Exception as e:  # noqa: BLE001
            logger.warning("F5 render: trial_balance(6401) failed: %s", e)

    return {
        "account_code": "6401",
        "responses_snapshot": responses_snapshot,
        "prefix": "F5",
        "rollforward_tb": rollforward_tb,
        "adjudicated_cogs": adjudicated_cogs,
        "project_context": project_context,
    }
