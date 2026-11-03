"""H7 生产性生物资产 — 专属渲染策略.

科目定位（语义驱动）：
  原值 = 1621 生产性生物资产
  累计折旧 = 1622 生产性生物资产累计折旧
  减值准备 = （无独立编码）
  报表行 BS-030 = TB('1621')

不按行业判定：平台没有项目级行业来源，原先把质控分类码当行业比对农林牧渔，``is_applicable`` 恒 False、
四表增强永远不跑（spec trim-followup-residual-findings-closure R1）。返回 ``accounts_found`` 供前端在
试算表里找不到生产性生物资产科目时给不阻断提示。
返回本页 html_data：TB数据(三层) + sheet_list + tb_source_codes + 已保存的计量模式。

🔴 2026-07-09 起本策略每页都抛 AttributeError（读 RenderContext 没有的 ``sheet_name``，路由吞成告警、
html_data 为 None），返回值还多包了一层 ``{"sheets": [{"html_data": …}]}``；路由与宿主都按「返回值即本页
html_data」读（同 H3 / H5）⇒ 改为直接返回 html_data。计量模式原先写死 ``cost``，接通后会在每次重载时把用户
选的公允价值模式改回成本模式 ⇒ 读宿主保存的 ``H7-measurement-model``。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.h7_account_scope import H7_ACCOUNT_SPEC, H7_SLOT_KEY_PREFIX
from app.services.four_table.semantic_account_resolver import (
    SemanticAccountResult,
    has_resolved_tb_rows,
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

H7_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h7-biological-assets"},
    {"sheet_name": "生物资产实质性程序表H7A", "component_type": "h7-biological-assets"},
    {"sheet_name": "审定表H7-1", "component_type": "h7-biological-assets"},
    {"sheet_name": "明细表H7-2", "component_type": "h7-biological-assets"},
    {"sheet_name": "调整分录汇总H7-3", "component_type": "h7-biological-assets"},
    {"sheet_name": "会计政策检查表H7-4", "component_type": "h7-biological-assets"},
    {"sheet_name": "分析表H7-5", "component_type": "h7-biological-assets"},
    {"sheet_name": "增加检查表H7-6", "component_type": "h7-biological-assets"},
    {"sheet_name": "减少检查表H7-7", "component_type": "h7-biological-assets"},
    {"sheet_name": "监盘计划H7-8", "component_type": "h7-biological-assets"},
    {"sheet_name": "盘点检查表H7-9", "component_type": "h7-biological-assets"},
    {"sheet_name": "监盘小结H7-10", "component_type": "h7-biological-assets"},
    {"sheet_name": "折旧测算表H7-11", "component_type": "h7-biological-assets"},
    {"sheet_name": "折旧分配分析表H7-12", "component_type": "h7-biological-assets"},
    {"sheet_name": "公允价值复核表H7-13", "component_type": "h7-biological-assets"},
    {"sheet_name": "互转审核表H7-14", "component_type": "h7-biological-assets"},
    {"sheet_name": "减值测算表H7-15", "component_type": "h7-biological-assets"},
    {"sheet_name": "可收回金额测试表H7-16", "component_type": "h7-biological-assets"},
    {"sheet_name": "关联交易检查表H7-17", "component_type": "h7-biological-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h7-biological-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h7-biological-assets"},
]


async def _fetch_tb_data(
    ctx: RenderContext,
) -> tuple[dict, SemanticAccountResult, bool | None]:
    """按语义槽取生产性生物资产三层数据，并按 active TB 实际行返回科目存在状态。"""
    accounts = await resolve_semantic_accounts(ctx, H7_ACCOUNT_SPEC)

    tb_rows: list = []
    tb_fetch_ok = True
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
        tb_fetch_ok = False
        logger.warning("H7 TB balance fetch failed: %s", e)

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
            logger.warning("H7 trial_balance fetch failed: %s", e)

    tb = _build_h7_tb_values(accounts, tb_rows, trial_rows)
    tb["_parent_check"] = build_parent_check(
        accounts, tb_rows, trial_rows, H7_SLOT_KEY_PREFIX.keys()
    )
    return tb, accounts, (
        has_resolved_tb_rows(accounts, tb_rows) if tb_fetch_ok else None
    )


def _build_h7_tb_values(accounts: SemanticAccountResult, tb_rows, trial_rows) -> dict[str, float]:
    """按语义槽聚合生产性生物资产各层金额。纯函数。"""
    leaves = select_leaves(to_leaf_rows(tb_rows))
    out: dict[str, float] = {}

    for slot_key, prefix in H7_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        agg = aggregate_leaves(leaves, slot.codes)
        out[f"{prefix}_unadjusted_opening"] = agg["opening"]
        out[f"{prefix}_unadjusted_closing"] = agg["closing"]
        out[f"{prefix}_unadjusted_debit"] = agg["debit"]
        out[f"{prefix}_unadjusted_credit"] = agg["credit"]

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

    for slot_key, prefix in H7_SLOT_KEY_PREFIX.items():
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


_MEASUREMENT_MODELS = ("cost", "fair_value")


async def _load_measurement_model(ctx: RenderContext) -> str:
    """宿主保存的计量模式（``PUT checklist-responses`` 写在 remark）；没存过或读不到按成本模式。

    保存点隔离：读失败不让 PG 事务停在 aborted、连累同一请求里后面页签的渲染。
    """
    try:
        async with ctx.db.begin_nested():
            row = (await ctx.db.execute(
                sa.text(
                    "SELECT remark, conclusion FROM checklist_responses "
                    "WHERE wp_id = :wp_id AND item_id = 'H7-measurement-model' LIMIT 1"
                ),
                {"wp_id": str(ctx.wp_id)},
            )).first()
    except Exception as e:  # noqa: BLE001
        logger.warning("H7 measurement_model load failed: %s", e)
        return "cost"
    for value in (getattr(row, "remark", None), getattr(row, "conclusion", None)):
        if value in _MEASUREMENT_MODELS:
            return value
    return "cost"


async def render_h7_biological_assets(ctx: RenderContext) -> dict:
    """H7 生产性生物资产 RENDERER_DISPATCH 入口（不按行业判定，见模块说明）."""
    # TB 取数（语义定位）
    tb_data, accounts, accounts_found = await _fetch_tb_data(ctx)
    resolved_codes = sorted({c for slot in accounts.slots.values() if slot.found for c in slot.codes})

    # 构建 html_data
    html_data = {
        "component_type": "h7-biological-assets",
        "measurement_model": await _load_measurement_model(ctx),
        "account_codes": resolved_codes or ["1621"],
        # active TB 查询实际命中行才算找到；解析器裸 fallback 码不算，查询失败为 None（未知）
        "accounts_found": accounts_found,
        "tb_data": tb_data,
        "tb_source_codes": accounts.as_dict(),
        "sheet_list": H7_SHEETS,
    }

    # ─── 灰度：H/I 四表取数增强（按解析到的科目槽取数，找不到科目时自然无段） ─────────
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill

            segments = []
            for slot_key, prefix in H7_SLOT_KEY_PREFIX.items():
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
                html_data["adjudication_segment_prefill"] = {"segments": segments, "enabled": True}
                html_data["hi_extraction_enabled"] = True
            if "responses_snapshot" not in html_data:
                html_data["responses_snapshot"] = {}
            from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
            from app.services.d_cycle_extraction.presets import resolve_effective
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
            await asyncio.wait_for(
                seed_tier_a_reconciliation(
                    ctx, "H7",
                    html_data["responses_snapshot"],
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:
            logger.warning("HI extraction prefill failed (%s): %s", "H7", e)

    return html_data


# Alias for RENDERER_DISPATCH registration pattern
render = render_h7_biological_assets
