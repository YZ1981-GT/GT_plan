"""I3 商誉 — 专属渲染策略.

component_type = "i3-goodwill"

科目1711商誉（借方/资产类）— 商誉不摊销！仅年度减值测试
返回 allResponses + tb_values(1711) + projectContext + sheets元数据

商誉核心特殊：
- 期末=期初+新并购-减值（只减不增，无摊销）
- DCF资产组(CGU)模型是核心
- 减值先冲商誉再分摊至资产组其他资产
- 减值不可转回

联动：TB回写(1711) + 附注EventBus + I3-6→I3-7 DCF联动

Requirements: 1.1-1.10, 2.1-2.8, 5.1-5.5, 6.1-6.7
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.services.four_table.i_cycle_extraction import load_i_cycle_extraction

from ._context import RenderContext

logger = logging.getLogger(__name__)


I3_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "i3-goodwill"},
    {"sheet_name": "商誉实质性程序表I3A", "component_type": "i3-goodwill"},
    {"sheet_name": "审定表I3-1", "component_type": "i3-goodwill"},
    {"sheet_name": "明细表I3-2", "component_type": "i3-goodwill"},
    {"sheet_name": "调整分录汇总I3-3", "component_type": "i3-goodwill"},
    {"sheet_name": "入账价值测算表I3-4", "component_type": "i3-goodwill"},
    {"sheet_name": "针对性检查表I3-5", "component_type": "i3-goodwill"},
    {"sheet_name": "商誉减值测试I3-6", "component_type": "i3-goodwill"},
    {"sheet_name": "可收回金额测试I3-7", "component_type": "i3-goodwill"},
    {"sheet_name": "复核公司减值测试过程及结论I3-8", "component_type": "i3-goodwill"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "i3-goodwill"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "i3-goodwill"},
]


async def _fetch_tb_data(ctx: RenderContext):
    """取 I3 的四表数据（走 `four_table` 共享件，科目按项目动态解析）。

    🔴 改造要点（详见 `four_table/i_cycle_accounts` 模块 docstring）：

    - 科目定位走**报表行动态解析**（项目级覆盖 → 按准则 → 行名校验），不再硬编码前缀；
    - 聚合走**叶子口径**（改造前父科目与子科目一起累加 → 实证恰好 2 倍虚增）；
    - 商誉减值准备在 `account_chart` 中无标准科目 → 该段留空（宁缺勿造）。

    Returns:
        ``(tb_values, extraction)`` —— `tb_values` 键名与改造前逐字一致（前端零改动）。
    """
    try:
        extraction = await load_i_cycle_extraction(ctx, "I3")
    except Exception as e:  # noqa: BLE001 — 取数失败不阻断 render
        logger.warning("I3 四表取数失败: %s", e)
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
        logger.warning("I3 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """I3商誉渲染策略：allResponses + projectContext + TB数据(1711).

    支持selfLoad模式：前端selfLoad时调用render-config获取tb_values种子数据。
    商誉特殊：不摊销，仅年度减值测试，期末=期初+新并购-减值。
    """
    # 1. 加载 checklist_responses 快照
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "I3-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("I3 render responses load failed: %s", e)

    # 2. 获取TB数据（1711商誉）
    tb_values, extraction = await _fetch_tb_data(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    # 科目码改由解析结果给出（项目自定义映射生效），解析失败才回退
    account_codes = [
        c for seg in (extraction.accounts.segments if extraction else ()) for c in seg.original
    ]

    payload = {
        "component_type": "i3-goodwill",
        "account_codes": account_codes,
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "I3",
        "sheets": I3_SHEETS,
        "meta": {
            "sheet_count": 12,
            "wp_code": "I3",
            "special_rules": {
                "no_amortization": True,
                "impairment_only": True,
                "impairment_not_reversible": True,
                "allocation_rule": "先冲商誉再分摊至资产组其他资产",
            },
        },
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
                    ctx, "I3",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning("HI extraction prefill failed (%s): %s", "I3", e)

    return payload
