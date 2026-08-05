"""H10 资产处置损益 — 专属渲染策略.

科目定位（语义驱动，2026-08-03 纠正）：
  资产处置损益 = 6115（损益类）
  报表行 IS-018 = TB('6115','本期发生额')

🔴 **损益口径**：取本期发生额，不取期末余额。
- `trial_balance` 优先（`unadjusted_amount` 即发生额）
- 兜底 `tb_balance`：按正方向取（6115 多为 credit，取 credit_amount）
- 禁用 `debit - credit`（含年末结转损益的全年账上结构性恒为 0）

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations
import logging
import sqlalchemy as sa
from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.h10_account_scope import H10_ACCOUNT_SPEC, H10_SLOT_KEY_PREFIX
from app.services.four_table.semantic_account_resolver import (
    SemanticAccountResult,
    resolve_semantic_accounts,
)
from app.services.four_table.leaf_aggregation import (
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.parent_check import build_parent_check
from ._context import RenderContext

logger = logging.getLogger(__name__)

_ADJUDICATED_ITEM_ID = "H10-1-adjudicated-amount"

H10_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "资产处置损益实质性程序表H10A", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "审定表H10-1", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "明细表H10-2", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "调整分录汇总H10-3", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "检查表H10-4", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h10-asset-disposal-income"},
]


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（对齐 H1/D2 范式：客户名/审计年度/资产负债表日/关联方/变体）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category,
                       p.applicable_standard_v2 AS applicable_standards,
                       p.template_type, p.report_scope
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row:
            project_ctx["client_name"] = row.client_name or ""
            audit_year = str(row.audit_year) if row.audit_year else ""
            project_ctx["audit_year"] = audit_year
            project_ctx["business_category"] = row.business_category or ""
            project_ctx["applicable_standards"] = row.applicable_standards or ""
            project_ctx["template_type"] = (
                str(row.template_type.value) if hasattr(row.template_type, "value")
                else (str(row.template_type) if row.template_type else "")
            )
            project_ctx["report_scope"] = (
                str(row.report_scope.value) if hasattr(row.report_scope, "value")
                else (str(row.report_scope) if row.report_scope else "")
            )
            project_ctx["bs_date"] = f"{audit_year}-12-31" if audit_year else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("H10 project context load failed: %s", e)

    # 关联方（供 H10-4 关联方处置检查）
    try:
        rp_result = await ctx.db.execute(
            sa.text(
                "SELECT name, relation_type FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        project_ctx["related_parties"] = [
            {"name": r.name, "relation_type": r.relation_type or ""}
            for r in rp_result.fetchall()
        ]
    except Exception:  # noqa: BLE001
        project_ctx["related_parties"] = []

    return project_ctx


async def _fetch_tb_pl_amount(ctx: RenderContext) -> tuple[dict, SemanticAccountResult]:
    """损益类取数：本期发生额（trial_balance 优先，兜底 tb_balance credit_amount）。

    Returns:
        ``(tb_values, accounts)``
    """
    accounts = await resolve_semantic_accounts(ctx, H10_ACCOUNT_SPEC)
    tb: dict[str, float] = {}

    gross_slot = accounts.slots.get("gross")
    if not gross_slot or not gross_slot.found:
        return tb, accounts

    codes = gross_slot.codes  # 语义定位后的科目码

    # 优先从 trial_balance 取发生额（权威口径）
    standard_codes = gross_slot.standard_codes
    if standard_codes:
        try:
            result = await ctx.db.execute(
                sa.text(
                    "SELECT standard_account_code, unadjusted_amount, audited_amount "
                    "FROM trial_balance "
                    "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                    "  AND standard_account_code = ANY(:codes)"
                ),
                {"pid": str(ctx.project_id), "year": ctx.year, "codes": standard_codes},
            )
            trial_rows = list(result.fetchall())
            unadj_total = 0.0
            audited_total = 0.0
            for row in trial_rows:
                unadj_total += float(row.unadjusted_amount or 0)
                audited_total += float(row.audited_amount or 0)
            if unadj_total != 0 or audited_total != 0:
                tb["current_amount"] = unadj_total
                tb["current_audited"] = audited_total
                tb["source"] = "trial_balance"
                # 走 trial_balance 路径时也要出 parent_check（Req 3.4）；
                # 此处未查 tb_balance 故叶子侧为空，只暴露 trial 口径
                tb["_parent_check"] = build_parent_check(
                    accounts, [], trial_rows, H10_SLOT_KEY_PREFIX.keys(), occurrence=True
                )
                return tb, accounts
        except Exception as e:  # noqa: BLE001
            logger.warning("H10 trial_balance fetch failed: %s", e)

    # 兜底：从 tb_balance 取本期发生额（按正方向：损益类取 credit_amount）
    tb_rows: list = []
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(active_filter)
        )
        # 按解析后的科目码前缀匹配（点号边界）
        tb_rows = list(result.fetchall())
        debit = 0.0
        credit = 0.0
        matched = False
        for row in tb_rows:
            code = (row.account_code or "").strip()
            if any(code == c or code.startswith(c + ".") for c in codes):
                debit += float(row.debit_amount or 0)
                credit += float(row.credit_amount or 0)
                matched = True
        if matched:
            # 损益类正方向：资产处置损益 direction 多为 credit
            # 但贷方-借方在含年末结转的全年账上恒为 0 → 单侧取 credit_amount
            tb = {"current_amount": credit, "debit_amount": debit, "credit_amount": credit}
            tb["source"] = "tb_balance_credit"
    except Exception as e:  # noqa: BLE001
        logger.warning("H10 TB fetch failed: %s", e)

    # Req 3.4：损益类用发生额口径自检（`occurrence=True`）
    tb["_parent_check"] = build_parent_check(
        accounts, tb_rows, [], H10_SLOT_KEY_PREFIX.keys(), occurrence=True
    )
    return tb, accounts


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H10-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:
        logger.warning("H10 render failed: %s", e)

    tb_values, accounts = await _fetch_tb_pl_amount(ctx)
    project_context = await _load_project_context(ctx)

    resolved_gross_codes = accounts.codes_of("gross") or ["6115"]

    payload = {
        "component_type": "h10-asset-disposal-income",
        "account_code": resolved_gross_codes[0] if resolved_gross_codes else "6115",
        "account_codes": resolved_gross_codes,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        "tb_values": tb_values,
        "tb_source_codes": accounts.as_dict(),
        "project_context": project_context,
        "prefix": "H10",
        "sheets": H10_SHEETS,
    }

    # ─── 灰度：H/I 四表取数增强（损益类 mode=occurrence） ─────────────────
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill

            # 按解析后的科目码取数（不再硬编码 "6115"）
            segments = []
            gross_slot = accounts.slots.get("gross")
            if gross_slot and gross_slot.found:
                for code in gross_slot.codes:
                    seg_items = await asyncio.wait_for(
                        build_d_adjudication_prefill(ctx, account_prefix=code, mode="occurrence"),
                        timeout=5.0,
                    )
                    segments.append({"segment": "gross", "account_prefix": code, "mode": "occurrence", "items": seg_items})

            payload["adjudication_segment_prefill"] = {
                "segments": segments,
                "enabled": True,
            }
            payload["hi_extraction_enabled"] = True
            # Tier A transient seed（TB核对行）
            from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
            from app.services.d_cycle_extraction.presets import resolve_effective
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
            await asyncio.wait_for(
                seed_tier_a_reconciliation(
                    ctx, "H10",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("HI extraction prefill failed (%s): %s", "H10", e)

    return payload
