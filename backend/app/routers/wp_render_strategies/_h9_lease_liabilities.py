"""H9 租赁负债 — 专属渲染策略.

component_type = "h9-lease-liabilities"

科目2205租赁负债（贷方/负债类）+ 未确认融资费用（借方/负债备抵类）
CAS21: 与H8使用权资产配对
返回 allResponses + tb_values(2205+未确认融资费用) + h8_linkage + formula_validation
     + sheets元数据

负债类公式：期末=期初+贷方-借方（与资产类相反！）
备抵类公式：期末=期初+借方-贷方
联动：H8使用权资产(双向) + TB回写(2205+未确认融资费用) + 附注

Requirements: 1.6
"""
from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：2205租赁负债（贷方/负债类）
_H9_ACCOUNT_PREFIXES = {
    "2205": ("lease_liability", "lease_liability_audited"),
}

# 未确认融资费用可能使用的科目编码（借方/负债备抵类）
_H9_FINANCE_COST_PREFIXES = ["220501", "2205%融资%", "6602%租赁%"]

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


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目2205的期初/期末余额及未审数/审定数.

    包含租赁负债(2205, 贷方/负债类)和未确认融资费用(备抵/借方)。
    负债类贷方科目：期末=期初+贷方-借方
    备抵类借方科目：期末=期初+借方-贷方
    """
    tb: dict[str, float] = {}

    try:
        from app.models.audit_platform_models import TbBalance
        from app.services.dataset_query import get_active_filter

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
            ).where(
                active_filter,
                sa.or_(
                    TbBalance.account_code == "2205",
                    TbBalance.account_code.startswith("2205"),
                ),
            )
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            # 判断是否为未确认融资费用子科目(220501等)
            is_finance_cost = len(code) > 4 and code.startswith("2205")
            key_prefix = "lease_finance_cost" if is_finance_cost else "lease_2205"

            tb[f"{key_prefix}_opening"] = tb.get(f"{key_prefix}_opening", 0.0) + float(row.opening_balance or 0)
            tb[f"{key_prefix}_closing"] = tb.get(f"{key_prefix}_closing", 0.0) + float(row.closing_balance or 0)
            tb[f"{key_prefix}_debit"] = tb.get(f"{key_prefix}_debit", 0.0) + float(row.debit_amount or 0)
            tb[f"{key_prefix}_credit"] = tb.get(f"{key_prefix}_credit", 0.0) + float(row.credit_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("H9 TB balance fetch failed: %s", e)

    # 从 trial_balance 取未审数+审定数
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '2205%'
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            is_finance_cost = len(code) > 4 and code.startswith("2205")
            key_prefix = "lease_finance_cost" if is_finance_cost else "lease_2205"

            tb[f"{key_prefix}_unadjusted"] = tb.get(f"{key_prefix}_unadjusted", 0.0) + float(row.unadjusted_amount or 0)
            tb[f"{key_prefix}_audited"] = tb.get(f"{key_prefix}_audited", 0.0) + float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("H9 trial_balance fetch failed: %s", e)

    return tb


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

    # 2. 获取TB数据（2205租赁负债 + 未确认融资费用子科目）
    tb_values = await _fetch_tb_data(ctx)

    # 3. 负债类公式验证
    formula_validation = await _validate_liability_formulas(tb_values)

    # 4. H8联动校验
    h8_linkage = await _fetch_h8_linkage(ctx)

    payload = {
        "component_type": "h9-lease-liabilities",
        "account_codes": ["2205"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
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
            "account_code": "2205",
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
            segment_prefill = await asyncio.wait_for(
                build_d_adjudication_prefill(ctx, account_prefix="2205", mode="balance"),
                timeout=5.0,
            )
            payload["adjudication_segment_prefill"] = {
                "segments": [{"segment": "cost", "account_prefix": "2205", "mode": "balance", "items": segment_prefill}],
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
