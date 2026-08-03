"""I6 研发费用 — 专属渲染策略.

component_type = "i6-research-development-expense"

科目6604研发费用（**损益类/借方科目**）— I循环唯一损益类底稿
🔴 `6602` 是**管理费用**（全库借方 6.24 亿），历史实现取错科目族，已按
`report_config` 的 `IS-006`/`IS-024` = `TB('6604','本期发生额')` 纠正。
**损益类取数逻辑**：取本期发生额（`trial_balance` 优先、`tb_balance` 借方回退），
NOT `tb_balance` 期末余额，也 **NOT** `debit - credit` —— 含年末结转损益分录时
借贷两侧恒相等，净额恒为 0（平台级铁律）。

与H10(6115资产处置损益)同款处理逻辑。

联动：TB回写(**发生额**6604) + I6↔I2双向(VR-I6-01) + 附注EventBus

Requirements: 1.1-1.10, 2.1-2.8, 4.1-4.7, 10.1-10.4
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.services.four_table.i_cycle_extraction import load_i_cycle_extraction

from ._context import RenderContext

logger = logging.getLogger(__name__)


I6_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "i6-research-development-expense"},
    {"sheet_name": "研发费用实质性程序表I6A", "component_type": "i6-research-development-expense"},
    {"sheet_name": "审定表I6-1", "component_type": "i6-research-development-expense"},
    {"sheet_name": "明细表I6-2", "component_type": "i6-research-development-expense"},
    {"sheet_name": "调整分录汇总I6-3", "component_type": "i6-research-development-expense"},
    {"sheet_name": "针对性检查表I6-4", "component_type": "i6-research-development-expense"},
    {"sheet_name": "截止性测试（账到单据）I6-5", "component_type": "i6-research-development-expense"},
    {"sheet_name": "截止性测试（单据到账）I6-6", "component_type": "i6-research-development-expense"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "i6-research-development-expense"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "i6-research-development-expense"},
]


async def _fetch_tb_income_statement(ctx: RenderContext):
    """取 I6 的四表数据（走 `four_table` 共享件，科目按项目动态解析）。

    🔴 改造要点（详见 `four_table/i_cycle_accounts` 模块 docstring）：

    - 科目定位走**报表行动态解析**（项目级覆盖 → 按准则 → 行名校验），不再硬编码前缀；
    - 聚合走**叶子口径**（改造前父科目与子科目一起累加 → 实证恰好 2 倍虚增）；
    - 科目由 `6602`（**管理费用**，全库借方 6.24 亿）纠正为 `6604` 研发费用；
    - 损益类取**本期发生额**（`trial_balance` 优先、`tb_balance` 借方回退）——
      禁用 `debit - credit`：含年末结转损益分录时两侧恒相等 → 恒为 0。

    Returns:
        ``(tb_values, extraction)`` —— `tb_values` 键名与改造前逐字一致（前端零改动）。
    """
    try:
        extraction = await load_i_cycle_extraction(ctx, "I6")
    except Exception as e:  # noqa: BLE001 — 取数失败不阻断 render
        logger.warning("I6 四表取数失败: %s", e)
        return {}, None
    return dict(extraction.tb_values), extraction


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文."""
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
        logger.warning("I6 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """I6研发费用渲染策略：损益类取发生额 + I2联动数据.

    核心特殊：
    1. **损益类取发生额**非余额（与H10同款）
    2. I6↔I2双向联动（VR-I6-01: 费用化+资本化=研发总额）
    3. 月度12列横向宽表
    """
    # 1. 加载 checklist_responses 快照
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "I6-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("I6 render responses load failed: %s", e)

    # 2. 获取TB数据（损益类！取发生额）
    tb_values, extraction = await _fetch_tb_income_statement(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    # 科目码改由解析结果给出（项目自定义映射生效），解析失败才回退
    account_codes = [
        c for seg in (extraction.accounts.segments if extraction else ()) for c in seg.original
    ]

    payload = {
        "component_type": "i6-research-development-expense",
        "account_codes": account_codes,
        "income_statement": True,  # 标识损益类
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "I6",
        "sheets": I6_SHEETS,
        "meta": {
            "sheet_count": 11,
            "wp_code": "I6",
            "special_rules": {
                "income_statement": True,
                "account_direction": "debit",
                "net_formula": "本期发生额（禁用 借方-贷方：含结转损益时恒为 0）",
                "source_table": "trial_balance 本期发生额优先 / tb_balance 借方回退",
                "cross_wp_linkage": "I6↔I2双向(VR-I6-01)",
                "monthly_matrix": True,
                "cutoff_test_bidirectional": True,
            },
        },
    }

    # ─── 灰度：H/I 四表取数增强（损益类 mode=occurrence） ─────────────────
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            if extraction is not None:
                payload["tb_source_codes"] = extraction.source_codes_payload()
                if extraction.adjudication_prefill:
                    payload["adjudication_prefill"] = extraction.adjudication_prefill
                payload["hi_extraction_enabled"] = True
            # Tier A transient seed（TB核对行）
            from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
            from app.services.d_cycle_extraction.presets import resolve_effective
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
            await asyncio.wait_for(
                seed_tier_a_reconciliation(
                    ctx, "I6",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("HI extraction prefill failed (%s): %s", "I6", e)

    return payload
