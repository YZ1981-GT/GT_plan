"""H5 油气资产 — 专属渲染策略.

科目定位（语义驱动）：
  原值 = 1631 油气资产
  累计折耗 = 1632 油气资产累计折耗
  无 BS 报表行（仅 CFSS-005 提折耗）

行业适用性守卫：仅 oil_gas / mining 行业适用
返回 allResponses + projectContext + TB数据(三层) + sheet_list + tb_source_codes

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.h5_account_scope import H5_ACCOUNT_SPEC, H5_SLOT_KEY_PREFIX
from app.services.four_table.semantic_account_resolver import (
    SemanticAccountResult,
    resolve_semantic_accounts,
)
from app.services.four_table.leaf_aggregation import (
    aggregate_leaves,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.parent_check import build_parent_check

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 适用行业
_APPLICABLE_INDUSTRIES = {"oil_gas", "mining"}

# 适用行业
_APPLICABLE_INDUSTRIES = {"oil_gas", "mining"}

H5_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "油气资产实质性程序表H5A", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "审定表H5-1", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "明细表H5-2", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "调整分录汇总H5-3", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "闲置检查表H5-4", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "会计政策检查表H5-5", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "分析表H5-6", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "增加检查表H5-7", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "减少检查表H5-8", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "监盘计划H5-9", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "盘点检查表H5-10", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "监盘小结H5-11", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "折耗测算表H5-12", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "折耗分配分析表H5-13", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "减值测算表H5-14", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "可收回金额测试表H5-15", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "权属检查表H5-16", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "关联交易检查表H5-17", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "经营租出检查表H5-18", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "融资租出检查表H5-19", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "调整分录汇总H5-3A", "component_type": "h5-oil-gas-assets"},
]


async def _check_industry_applicability(ctx: RenderContext) -> tuple[bool, str]:
    """检查项目行业适用性（oil_gas/mining）."""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT business_category FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        row = result.fetchone()
        if row:
            industry = (row.business_category or "").strip().lower()
            if industry in _APPLICABLE_INDUSTRIES:
                return True, industry
            return False, industry
    except Exception as e:  # noqa: BLE001
        logger.warning("H5 industry check failed: %s", e)
    return False, ""


async def _fetch_tb_data(ctx: RenderContext) -> tuple[dict, SemanticAccountResult]:
    """按语义槽取油气资产三层数据（原值 / 累计折耗 / 减值准备）。

    Returns:
        ``(tb_values, accounts)``
    """
    accounts = await resolve_semantic_accounts(ctx, H5_ACCOUNT_SPEC)

    tb_rows: list = []
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.dataset_id,
            ).where(active_filter)
        )
        tb_rows = list(result.fetchall())
    except Exception as e:  # noqa: BLE001
        logger.warning("H5 TB balance fetch failed: %s", e)

    trial_rows: list = []
    standard_codes = sorted(
        {c for slot in accounts.slots.values() for c in slot.standard_codes if c}
    )
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
        except Exception as e:  # noqa: BLE001
            logger.warning("H5 trial_balance fetch failed: %s", e)

    tb = _build_h5_tb_values(accounts, tb_rows, trial_rows)
    tb["_parent_check"] = build_parent_check(
        accounts, tb_rows, trial_rows, H5_SLOT_KEY_PREFIX.keys()
    )
    return tb, accounts


def _build_h5_tb_values(
    accounts: SemanticAccountResult,
    tb_rows,
    trial_rows,
) -> dict[str, float]:
    """按语义槽聚合油气资产各层金额。纯函数。

    输出键契约（保持既有 `cost_*`/`dep_*` 不变）::

        {prefix}_unadjusted_opening / _closing / _debit / _credit  ← tb_balance 叶子
        {prefix}_unadjusted / {prefix}_audited                     ← trial_balance
    """
    leaves = select_leaves(to_leaf_rows(tb_rows))
    out: dict[str, float] = {}

    for slot_key, prefix in H5_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        agg = aggregate_leaves(leaves, slot.codes)
        out[f"{prefix}_unadjusted_opening"] = agg["opening"]
        out[f"{prefix}_unadjusted_closing"] = agg["closing"]
        out[f"{prefix}_unadjusted_debit"] = agg["debit"]
        out[f"{prefix}_unadjusted_credit"] = agg["credit"]

    # trial_balance：按标准码精确匹配
    by_code: dict[str, tuple[float, float]] = {}
    for row in trial_rows or []:
        get = row.get if isinstance(row, dict) else (lambda k, _r=row: getattr(_r, k, None))
        code = str(get("standard_account_code") or "").strip()
        if not code:
            continue
        prev = by_code.get(code, (0.0, 0.0))
        by_code[code] = (
            prev[0] + float(get("unadjusted_amount") or 0),
            prev[1] + float(get("audited_amount") or 0),
        )

    for slot_key, prefix in H5_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        wanted = set(slot.standard_codes)
        if not wanted:
            continue
        unadj = sum(v[0] for c, v in by_code.items() if c in wanted)
        audited = sum(v[1] for c, v in by_code.items() if c in wanted)
        out[f"{prefix}_unadjusted"] = unadj
        out[f"{prefix}_audited"] = audited

    return out


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/行业/适用准则）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category, p.applicable_standard_v2 AS applicable_standards
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
            project_ctx["applicable_standards"] = row.applicable_standards or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("H5 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """H5油气资产渲染策略：行业校验 + allResponses + projectContext + TB数据.

    行业适用性前后端双重校验（ADR-2）：
    - oil_gas / mining → 正常渲染
    - 其他行业 → 返回 industry_error 信息供前端显示 el-empty
    """
    # ─── 1. 行业适用性守卫 ──────────────────────────────────────────────────
    is_applicable, industry = await _check_industry_applicability(ctx)
    if not is_applicable:
        return {
            "component_type": "h5-oil-gas-assets",
            "industry_error": True,
            "industry_detected": industry,
            "message": "本底稿仅适用于石油天然气/采矿行业项目",
            "applicable_industries": list(_APPLICABLE_INDUSTRIES),
        }

    # ─── 2. 加载 checklist_responses（H5-前缀） ────────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 3000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H5-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H5 render responses load failed: %s", e)

    # ─── 3. TB 数据（语义定位：油气资产 + 累计折耗 + 减值准备） ────────────
    tb_values, accounts = await _fetch_tb_data(ctx)

    # ─── 4. 项目上下文 ──────────────────────────────────────────────────────
    project_context = await _load_project_context(ctx)

    resolved_codes = sorted({c for slot in accounts.slots.values() if slot.found for c in slot.codes})

    payload = {
        "component_type": "h5-oil-gas-assets",
        "account_codes": resolved_codes or ["1631"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": accounts.as_dict(),
        "project_context": project_context,
        "prefix": "H5",
        "sheets": H5_SHEETS,
        "industry": industry,
    }

    # ─── 灰度：H/I 四表取数增强（仅行业适用时，AFTER industry guard） ──────
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill

            # 按解析后的各槽动态取数
            segments = []
            for slot_key, prefix in H5_SLOT_KEY_PREFIX.items():
                slot = accounts.slots.get(slot_key)
                if not slot or not slot.found:
                    continue
                for code in slot.codes:
                    seg_items = await asyncio.wait_for(
                        build_d_adjudication_prefill(ctx, account_prefix=code, mode="balance"),
                        timeout=5.0,
                    )
                    if seg_items:
                        segments.append({"segment": slot_key, "account_prefix": code, "mode": "balance", "items": seg_items})

            if segments:
                payload["adjudication_segment_prefill"] = {"segments": segments, "enabled": True}
                payload["hi_extraction_enabled"] = True
            # Tier A transient seed（TB核对行）
            from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
            from app.services.d_cycle_extraction.presets import resolve_effective
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
            await asyncio.wait_for(
                seed_tier_a_reconciliation(
                    ctx, "H5",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("HI extraction prefill failed (%s): %s", "H5", e)

    return payload
