"""H9 租赁负债 — 专属渲染策略.

component_type = "h9-lease-liabilities"

科目定位（语义驱动，2026-08-03 纠正）：
  租赁负债 = 2601（贷方/负债类）
  未确认融资费用 = 2602（借方/负债备抵类）
  报表行 BS-063 = TB('2601') - TB('2602')

🔴 旧实现写死 `2205`（合同负债，D7 循环），**取错整个科目族**。

CAS21: 与H8使用权资产配对
返回 allResponses + tb_values(两层) + h8_linkage + formula_validation
     + sheets元数据 + tb_source_codes(溯源)

负债类公式：期末=期初+贷方-借方（与资产类相反！）
备抵类公式：期末=期初+借方-贷方
联动：H8使用权资产(双向) + TB回写(语义定位后的科目码) + 附注

Requirements: 1.6
spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.h9_account_scope import H9_ACCOUNT_SPEC, H9_SLOT_KEY_PREFIX
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

# ──────────────────────────────────────────────────────────────────────────────
# 两层取数纯函数（无 DB 依赖，可独立单测）
# ──────────────────────────────────────────────────────────────────────────────


def build_h9_tb_values(
    accounts: SemanticAccountResult,
    tb_rows,
    trial_rows,
) -> dict[str, float]:
    """按语义槽聚合租赁负债两层金额。纯函数。

    输出键契约::

        lease_liability_unadjusted_opening / _closing / _debit / _credit   ← tb_balance
        unearned_finance_unadjusted_opening / _closing / _debit / _credit  ← tb_balance（新增）
        {prefix}_unadjusted / {prefix}_audited                             ← trial_balance

    某槽 `found=False` 时不产生该槽的任何键（宁缺勿造）。

    🔴 既有前端消费方可能读 `lease_2205_*` 旧键名 → 保留兼容别名。
    """
    leaves = select_leaves(to_leaf_rows(tb_rows))
    out: dict[str, float] = {}

    for slot_key, prefix in H9_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        agg = aggregate_leaves(leaves, slot.codes)
        out[f"{prefix}_unadjusted_opening"] = agg["opening"]
        out[f"{prefix}_unadjusted_closing"] = agg["closing"]
        out[f"{prefix}_unadjusted_debit"] = agg["debit"]
        out[f"{prefix}_unadjusted_credit"] = agg["credit"]

    # 兼容旧键名（前端可能仍读 `lease_2205_*`）
    if "lease_liability_unadjusted_opening" in out:
        out["lease_2205_opening"] = out["lease_liability_unadjusted_opening"]
        out["lease_2205_closing"] = out["lease_liability_unadjusted_closing"]
        out["lease_2205_debit"] = out["lease_liability_unadjusted_debit"]
        out["lease_2205_credit"] = out["lease_liability_unadjusted_credit"]
    if "unearned_finance_unadjusted_opening" in out:
        out["lease_finance_cost_opening"] = out["unearned_finance_unadjusted_opening"]
        out["lease_finance_cost_closing"] = out["unearned_finance_unadjusted_closing"]
        out["lease_finance_cost_debit"] = out["unearned_finance_unadjusted_debit"]
        out["lease_finance_cost_credit"] = out["unearned_finance_unadjusted_credit"]

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

    for slot_key, prefix in H9_SLOT_KEY_PREFIX.items():
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
        # 兼容旧键名
        if slot_key == "gross":
            out["lease_2205_unadjusted"] = unadj
            out["lease_2205_audited"] = audited
        elif slot_key == "unearned_finance":
            out["lease_finance_cost_unadjusted"] = unadj
            out["lease_finance_cost_audited"] = audited

    return out

H9_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h9-lease-liabilities"},
    {"sheet_name": "租赁负债实质性程序表H9A", "component_type": "h9-lease-liabilities"},
    {"sheet_name": "审定表H9-1", "component_type": "h9-lease-liabilities"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h9-lease-liabilities"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "h9-lease-liabilities"},
    {"sheet_name": "租赁负债明细表H9-2", "component_type": "h9-lease-liabilities"},
    {"sheet_name": "未确认融资费用明细表H9-3", "component_type": "h9-lease-liabilities"},
    {"sheet_name": "调整分录汇总H9-4", "component_type": "h9-lease-liabilities"},
]


async def _fetch_tb_data(ctx: RenderContext) -> tuple[dict, SemanticAccountResult]:
    """按语义槽取租赁负债两层数据（租赁负债 2601 / 未确认融资费用 2602）。

    Returns:
        ``(tb_values, accounts)`` —— ``accounts`` 供 render 下发 `tb_source_codes` 溯源。
    """
    accounts = await resolve_semantic_accounts(ctx, H9_ACCOUNT_SPEC)

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
        logger.warning("H9 TB balance fetch failed: %s", e)

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
            logger.warning("H9 trial_balance fetch failed: %s", e)

    tb = build_h9_tb_values(accounts, tb_rows, trial_rows)
    tb["_parent_check"] = build_parent_check(
        accounts, tb_rows, trial_rows, H9_SLOT_KEY_PREFIX.keys()
    )
    return tb, accounts


async def _validate_liability_formulas(tb_values: dict) -> dict[str, Any]:
    """负债类公式验证.

    验证项:
    1. 租赁负债(贷方/负债类)：期末=期初+贷方-借方
    2. 未确认融资费用(借方/备抵类)：期末=期初+借方-贷方
    3. 净额=租赁负债-未确认融资费用 >= 0
    """
    validation: dict[str, Any] = {
        "liability_balance_valid": True,
        "finance_cost_balance_valid": True,
        "net_liability_positive": True,
        "messages": [],
    }

    # 验证租赁负债余额公式: 期末=期初+贷方-借方 (负债类贷方科目)
    opening = tb_values.get("lease_2205_opening", 0.0)
    debit = tb_values.get("lease_2205_debit", 0.0)
    credit = tb_values.get("lease_2205_credit", 0.0)
    closing = tb_values.get("lease_2205_closing", 0.0)

    expected_closing = opening + credit - debit
    if abs(closing - expected_closing) > 1.0 and closing != 0.0:
        validation["liability_balance_valid"] = False
        validation["messages"].append(
            f"租赁负债期末余额校验不通过: 期末{closing:.2f} ≠ "
            f"期初{opening:.2f}+贷{credit:.2f}-借{debit:.2f}(={expected_closing:.2f})"
        )

    # 验证未确认融资费用余额公式: 期末=期初+借方-贷方 (借方/备抵类)
    fc_opening = tb_values.get("lease_finance_cost_opening", 0.0)
    fc_debit = tb_values.get("lease_finance_cost_debit", 0.0)
    fc_credit = tb_values.get("lease_finance_cost_credit", 0.0)
    fc_closing = tb_values.get("lease_finance_cost_closing", 0.0)

    expected_fc_closing = fc_opening + fc_debit - fc_credit
    if abs(fc_closing - expected_fc_closing) > 1.0 and fc_closing != 0.0:
        validation["finance_cost_balance_valid"] = False
        validation["messages"].append(
            f"未确认融资费用期末校验不通过: 期末{fc_closing:.2f} ≠ "
            f"期初{fc_opening:.2f}+借{fc_debit:.2f}-贷{fc_credit:.2f}(={expected_fc_closing:.2f})"
        )

    # 验证净额非负（租赁负债 - 未确认融资费用 >= 0）
    net_liability = closing - abs(fc_closing)
    if net_liability < -1.0 and closing != 0.0:
        validation["net_liability_positive"] = False
        validation["messages"].append(
            f"租赁负债净额为负: {net_liability:.2f}"
            f"（租赁负债{closing:.2f} - 未确认融资费用{abs(fc_closing):.2f}）"
        )

    return validation


async def _fetch_h8_linkage(ctx: RenderContext) -> dict[str, Any]:
    """查询H8使用权资产数据，与H9初始计量交叉验证.

    CAS21: H8初始计量 = H9初始确认 + 初始直接费用 - 租赁激励
    即: H9初始 ≈ H8初始 - 直接费用 + 激励
    校验容差: ±1元
    """
    h8_data: dict[str, Any] = {
        "h8_initial": 0.0,
        "h9_initial": 0.0,
        "diff": 0.0,
        "is_consistent": True,
        "h8_available": False,
        "message": "",
    }

    try:
        # 查H8 checklist_responses 获取使用权资产初始计量
        result = await ctx.db.execute(
            sa.text("""
                SELECT cr.item_id, cr.conclusion, cr.remark
                FROM checklist_responses cr
                JOIN working_paper wp ON cr.wp_id = wp.id
                JOIN wp_index wi ON wi.project_id = wp.project_id
                    AND wi.wp_code = 'H8'
                WHERE wp.project_id = :pid
                  AND wp.is_deleted = false
                  AND cr.item_id LIKE 'H8-%'
                LIMIT 500
            """),
            {"pid": str(ctx.project_id)},
        )
        rows = result.fetchall()
        if rows:
            h8_data["h8_available"] = True
            for row in rows:
                item_id = row.item_id or ""
                if "initial" in item_id.lower() or "初始" in (row.remark or ""):
                    try:
                        h8_data["h8_initial"] = float(row.conclusion or 0)
                    except (ValueError, TypeError):
                        pass

        # 获取H9当前底稿的初始确认值
        h9_result = await ctx.db.execute(
            sa.text("""
                SELECT item_id, conclusion FROM checklist_responses
                WHERE wp_id = :wp_id
                  AND (item_id LIKE 'H9-1-initial%' OR item_id LIKE 'H9-2-initial%')
                LIMIT 50
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        for row in h9_result.fetchall():
            item_id = row.item_id or ""
            if "total" in item_id or "合计" in item_id:
                try:
                    h8_data["h9_initial"] = float(row.conclusion or 0)
                except (ValueError, TypeError):
                    pass

        # 计算差异（允许±1元容差）
        diff = h8_data["h8_initial"] - h8_data["h9_initial"]
        h8_data["diff"] = round(diff, 2)
        h8_data["is_consistent"] = abs(diff) <= 1.0

        if not h8_data["h8_available"]:
            h8_data["message"] = "H8使用权资产底稿尚未编制"
        elif not h8_data["is_consistent"]:
            h8_data["message"] = f"H8与H9不一致，差额：{diff:.2f}元，请检查"
        else:
            h8_data["message"] = "H8-H9联动校验通过"

    except Exception as e:  # noqa: BLE001
        logger.warning("H9 H8 linkage fetch failed: %s", e)
        h8_data["message"] = "H8联动查询异常"

    return h8_data


async def render(ctx: RenderContext) -> dict | None:
    """H9租赁负债渲染策略.

    返回:
    - component_type: h9-lease-liabilities
    - account_codes: [2205]
    - responses_snapshot: checklist_responses快照
    - tb_values: 租赁负债+未确认融资费用余额数据
    - h8_linkage: H8联动校验结果
    - formula_validation: 负债类公式验证结果
    - sheets: sheet元数据列表
    - formula_direction: 负债类公式方向元数据
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # 1. 加载 checklist_responses (H9-* 前缀)
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(wp_id), "pfx": "H9-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H9 render responses load failed: %s", e)

    # 2. 获取TB数据（语义定位：2601 租赁负债 + 2602 未确认融资费用）
    tb_values, accounts = await _fetch_tb_data(ctx)

    # 3. 负债类公式验证
    formula_validation = await _validate_liability_formulas(tb_values)

    # 4. H8联动校验
    h8_linkage = await _fetch_h8_linkage(ctx)

    # 解析后的主科目码（供前端 writebackTB 等，不再写死 `2205`）
    resolved_gross_codes = accounts.codes_of("gross") or ["2601"]

    payload = {
        "component_type": "h9-lease-liabilities",
        "account_codes": resolved_gross_codes,
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": accounts.as_dict(),
        "formula_validation": formula_validation,
        "h8_linkage": h8_linkage,
        "prefix": "H9",
        "sheets": H9_SHEETS,
        "meta": {
            "sheet_count": 8,
            "wp_code": "H9",
            "paired_wp": "H8",
            "direction": "credit",  # 贷方/负债类
        },
        # 负债类公式方向元数据（前端可用于初始化校验）
        "formula_direction": {
            "account_code": resolved_gross_codes[0] if resolved_gross_codes else "2601",
            "account_name": "租赁负债",
            "direction": "credit",  # 贷方/负债类
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
            "contra_account": {
                "account_name": "未确认融资费用",
                "direction": "debit",  # 借方/负债备抵类
                "end_balance_formula": "begin + debit - credit",
            },
        },
    }

    # ─── 灰度：H/I 四表取数增强 ───────────────────────────────────────────
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill

            # 按解析后的两层各发一段（不再传 "2205"）
            segments = []
            for slot_key, prefix in H9_SLOT_KEY_PREFIX.items():
                slot = accounts.slots.get(slot_key)
                if not slot or not slot.found:
                    continue
                for code in slot.codes:
                    seg_items = await asyncio.wait_for(
                        build_d_adjudication_prefill(ctx, account_prefix=code, mode="balance"),
                        timeout=5.0,
                    )
                    segments.append({"segment": slot_key, "account_prefix": code, "mode": "balance", "items": seg_items})

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
                    ctx, "H9",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("HI extraction prefill failed (%s): %s", "H9", e)

    return payload
