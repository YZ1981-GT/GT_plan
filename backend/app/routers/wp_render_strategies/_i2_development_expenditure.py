"""I2 开发支出 — 专属渲染策略.

component_type = "i2-development-expenditure"

科目1704开发支出（借方/资产类；`1717` 全库不存在，为历史错码）
返回 allResponses + tb_values(1704) + projectContext + sheets元数据

资产类公式：期末=期初+借方-贷方（科目1704）
三角勾稽：期末=期初+增加(资本化)-减少(转无形/转费用)
核心特殊：CAS6五条件资本化判断 + I6↔I2双向联动 + I1转入联动

Requirements: 1.1-1.10, 2.1-2.7
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.services.four_table.i_cycle_extraction import load_i_cycle_extraction

from ._context import RenderContext

logger = logging.getLogger(__name__)


I2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "i2-development-expenditure"},
    {"sheet_name": "开发支出实质性程序表I2A", "component_type": "i2-development-expenditure"},
    {"sheet_name": "审定表I2-1", "component_type": "i2-development-expenditure"},
    {"sheet_name": "明细表I2-2", "component_type": "i2-development-expenditure"},
    {"sheet_name": "调整分录汇总I2-3", "component_type": "i2-development-expenditure"},
    {"sheet_name": "会计政策检查I2-4", "component_type": "i2-development-expenditure"},
    {"sheet_name": "实质性分析I2-5", "component_type": "i2-development-expenditure"},
    {"sheet_name": "资本化时点判断I2-6", "component_type": "i2-development-expenditure"},
    {"sheet_name": "研发项目构成明细表I2-7", "component_type": "i2-development-expenditure"},
    {"sheet_name": "研发材料投入检查表I2-8", "component_type": "i2-development-expenditure"},
    {"sheet_name": "研发人员认定检查表I2-9", "component_type": "i2-development-expenditure"},
    {"sheet_name": "研发人员工时检查表I2-10", "component_type": "i2-development-expenditure"},
    {"sheet_name": "委外研发检查表I2-11", "component_type": "i2-development-expenditure"},
    {"sheet_name": "针对性检查表I2-12", "component_type": "i2-development-expenditure"},
    {"sheet_name": "截止性测试（账到单据）I2-13", "component_type": "i2-development-expenditure"},
    {"sheet_name": "截止性测试（单据到账）I2-14", "component_type": "i2-development-expenditure"},
    {"sheet_name": "减值准备测试表I2-15", "component_type": "i2-development-expenditure"},
    {"sheet_name": "可收回金额测试I2-16", "component_type": "i2-development-expenditure"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "i2-development-expenditure"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "i2-development-expenditure"},
]


async def _fetch_tb_data(ctx: RenderContext):
    """取 I2 的四表数据（走 `four_table` 共享件，科目按项目动态解析）。

    🔴 改造要点（详见 `four_table/i_cycle_accounts` 模块 docstring）：

    - 科目定位走**报表行动态解析**（项目级覆盖 → 按准则 → 行名校验），不再硬编码前缀；
    - 聚合走**叶子口径**（改造前父科目与子科目一起累加 → 实证恰好 2 倍虚增）；
    - 科目由 `1717`（全库不存在）纠正为 `1704`（`account_chart` 实证）。

    Returns:
        ``(tb_values, extraction)`` —— `tb_values` 键名与改造前逐字一致（前端零改动）。
    """

    try:
        extraction = await load_i_cycle_extraction(ctx, "I2")
    except Exception as e:  # noqa: BLE001 — 取数失败不阻断 render
        logger.warning("I2 四表取数失败: %s", e)
        return {}, None
    return dict(extraction.tb_values), extraction


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/适用准则/行业类别）."""
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
        logger.warning("I2 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """I2开发支出渲染策略：allResponses + projectContext + TB数据(1704).

    支持selfLoad模式：前端selfLoad时调用render-config获取tb_values种子数据。
    """
    # 1. 加载 checklist_responses 快照
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "I2-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("I2 render responses load failed: %s", e)

    # 2. 获取TB数据（1704开发支出，按报表行动态解析）
    tb_values, extraction = await _fetch_tb_data(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    # 科目码改由解析结果给出（项目自定义映射生效），解析失败才回退
    account_codes = [
        c for seg in (extraction.accounts.segments if extraction else ()) for c in seg.original
    ]

    payload = {
        "component_type": "i2-development-expenditure",
        "account_codes": account_codes,
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "I2",
        "sheets": I2_SHEETS,
        "meta": {"sheet_count": 20, "wp_code": "I2"},
    }

    # ─── 灰度：H/I 四表取数增强 ───────────────────────────────────────────
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
                    ctx, "I2",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning("HI extraction prefill failed (%s): %s", "I2", e)

    return payload
