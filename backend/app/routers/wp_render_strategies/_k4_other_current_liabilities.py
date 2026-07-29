"""K4 其他流动负债 — 专属渲染策略.

componentType: k4-other-current-liabilities
科目 2245 其他流动负债（贷方/负债类）。

返回 allResponses + projectContext + TB数据(2245)
供前端 K4-1 审定表试算表列（只读）seed。

**负债口径**：期末 = 期初 + 贷方 - 借方（正数=期末贷方余额）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：2245其他流动负债(贷方/负债类)
_K4_ACCOUNT_PREFIXES = {
    "2245": ("liability_unadjusted", "liability_audited"),
}

K4_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "其他流动负债实质性程序表K4A", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "审定表K4-1", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "明细表K4-2", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "调整分录汇总K4-3", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "其他流动负债检查表K4-4", "component_type": "k4-other-current-liabilities"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目2245的期初/期末余额及借贷发生额（负债口径：正数=贷方余额）."""
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
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(active_filter)
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _K4_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K4 TB balance fetch failed: %s", e)

    # 从trial_balance取未审数/审定数
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '2245%'
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _K4_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K4 trial_balance fetch failed: %s", e)

    return tb


_K4_ACCOUNT_PREFIX = "2245"


async def _build_adjudication_prefill(ctx: RenderContext) -> list[dict]:
    """从 tb_balance 2245 明细子科目预填 K4-1 审定表行（负债类取余额）.

    2245 其他流动负债为负债/贷方科目：
    期初未审 = ABS(opening_balance)
    期末未审 = ABS(closing_balance)
    返回 [{name, code, opening_balance, closing_balance}]，前端在无持久化行时据此建行。
    """
    rows: list[dict] = []
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code.label("code"),
                TbBalance.account_name.label("name"),
                sa.func.sum(TbBalance.opening_balance).label("opening"),
                sa.func.sum(TbBalance.closing_balance).label("closing"),
            )
            .where(
                active_filter,
                TbBalance.account_code.startswith(_K4_ACCOUNT_PREFIX),
                TbBalance.account_code != _K4_ACCOUNT_PREFIX,
            )
            .group_by(TbBalance.account_code, TbBalance.account_name)
        )
        raw = [
            {
                "code": (r.code or "").strip(),
                "name": (r.name or "").strip(),
                "opening": float(r.opening or 0),
                "closing": float(r.closing or 0),
            }
            for r in result.fetchall()
        ]
        all_codes = [x["code"] for x in raw if x["code"]]

        def _is_leaf(code: str) -> bool:
            if not code:
                return True
            return not any(c != code and c.startswith(code) for c in all_codes)

        leaves = [x for x in raw if _is_leaf(x["code"])]
        leaves.sort(key=lambda x: abs(x["closing"]), reverse=True)
        for x in leaves:
            name = x["name"]
            opening = x["opening"]
            closing = x["closing"]
            if not name or (abs(opening) < 0.005 and abs(closing) < 0.005):
                continue
            rows.append({
                "name": name,
                "code": x["code"],
                "opening_balance": abs(opening),
                "closing_balance": abs(closing),
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("K4 adjudication prefill build failed: %s", e)
    return rows


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row:
            project_ctx["client_name"] = row.client_name or ""
            project_ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
            project_ctx["business_category"] = row.business_category or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("K4 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K4其他流动负债渲染策略：allResponses + projectContext + TB数据（负债口径）."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K4-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K4 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)
    adjudication_prefill = await _build_adjudication_prefill(ctx)

    return {
        "component_type": "k4-other-current-liabilities",
        "account_codes": ["2245"],
        "account_direction": "credit",  # 负债类！贷方增加
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "adjudication_prefill": adjudication_prefill,
        "prefix": "K4",
        "sheets": K4_SHEETS,
    }
