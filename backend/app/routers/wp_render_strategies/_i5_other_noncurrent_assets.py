"""I5 其他非流动资产 — 专属渲染策略.

component_type = "i5-other-noncurrent-assets"

其他非流动资产（借方/资产类）— 最简标准底稿。
🔴 **无标准科目**：`account_chart` 无「其他非流动资产」科目，`report_config` 的
`BS-040`/`BS-050` 公式为 None（`1911` 是历史错码，全库不存在）→ 取数按
「宁缺勿造」返回空集，审定表/披露表回退手工编制。
返回 allResponses + tb_values + projectContext + sheets元数据

I5核心特点：
- 最简单标准底稿（9 sheets），无特殊逻辑
- 标准资产类三角勾稽：期末=期初+增加-减少
- 审定=未审+AJE+RJE

联动：TB回写（按解析出的科目，通常为空） + 附注EventBus + substantive:adjudicated

Requirements: 1.1-1.10, 2.1-2.7
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.services.four_table.i_cycle_extraction import load_i_cycle_extraction

from ._context import RenderContext

logger = logging.getLogger(__name__)


I5_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "其他非流动资产实质性程序表I5A", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "审定表I5-1", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "明细表I5-2", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "调整分录汇总I5-3", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "针对性检查表I5-4", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "i5-other-noncurrent-assets"},
]


async def _fetch_tb_data(ctx: RenderContext):
    """取 I5 的四表数据（走 `four_table` 共享件，科目按项目动态解析）。

    🔴 改造要点（详见 `four_table/i_cycle_accounts` 模块 docstring）：

    - 科目定位走**报表行动态解析**（项目级覆盖 → 按准则 → 行名校验），不再硬编码前缀；
    - 聚合走**叶子口径**（改造前父科目与子科目一起累加 → 实证恰好 2 倍虚增）；
    - 科目由 `1911`（全库不存在）改为**无兜底码** —— 其他非流动资产无标准科目、
      且报表行公式为 None（`BS-050` 在 listed 下语义是「合同负债」，行名校验拦住）。

    Returns:
        ``(tb_values, extraction)`` —— `tb_values` 键名与改造前逐字一致（前端零改动）。
    """

    try:
        extraction = await load_i_cycle_extraction(ctx, "I5")
    except Exception as e:  # noqa: BLE001 — 取数失败不阻断 render
        logger.warning("I5 四表取数失败: %s", e)
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
        logger.warning("I5 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """I5其他非流动资产渲染策略：allResponses + projectContext + TB数据（无标准科目时为空）.

    支持selfLoad模式：前端selfLoad时调用render-config获取tb_values种子数据。
    最简标准底稿：标准资产类三角勾稽，期末=期初+增加-减少。
    """
    # 1. 加载 checklist_responses 快照
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "I5-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("I5 render responses load failed: %s", e)

    # 2. 获取TB数据（其他非流动资产：无标准科目 → 宁缺勿造）
    tb_values, extraction = await _fetch_tb_data(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    # 科目码改由解析结果给出（项目自定义映射生效），解析失败才回退
    account_codes = [
        c for seg in (extraction.accounts.segments if extraction else ()) for c in seg.original
    ]

    payload = {
        "component_type": "i5-other-noncurrent-assets",
        "account_codes": account_codes,
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "I5",
        "sheets": I5_SHEETS,
        "meta": {
            "sheet_count": 9,
            "wp_code": "I5",
            "special_rules": {
                "simplest_standard": True,
                "triangle_reconciliation": "期末=期初+增加-减少",
                "no_amortization": True,
                "no_impairment_model": True,
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
                    ctx, "I5",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning("HI extraction prefill failed (%s): %s", "I5", e)

    return payload
