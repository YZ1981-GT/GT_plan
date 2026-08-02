"""I1 无形资产、累计摊销及减值准备 — 专属渲染策略.

component_type = "i1-intangible-assets"

科目1701无形资产（借方/资产类）+ 1702累计摊销（贷方/资产备抵类）+ 1703无形资产减值准备（贷方/资产备抵类）
返回 allResponses + tb_values(1701+1702+1703) + projectContext + sheets元数据

资产类公式：期末=期初+借方-贷方（科目1701）
备抵类公式：期末=期初+贷方-借方（科目1702/1703）
三角勾稽：期末=期初+增加-减少
净值=原值-摊销-减值

联动：TB回写(1701+1702+1703) + I2资本化转入 + 摊销分配(K8/K9/I6) + 附注EventBus

Requirements: 1.1-1.10, 2.1-2.11
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.services.four_table.i_cycle_extraction import load_i_cycle_extraction

from ._context import RenderContext

logger = logging.getLogger(__name__)

I1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "i1-intangible-assets"},
    {"sheet_name": "无形资产实质性程序表I1A", "component_type": "i1-intangible-assets"},
    {"sheet_name": "审定表I1", "component_type": "i1-intangible-assets"},
    {"sheet_name": "明细表I1-2", "component_type": "i1-intangible-assets"},
    {"sheet_name": "调整分录汇总I1-3", "component_type": "i1-intangible-assets"},
    {"sheet_name": "无形资产摊销减值政策检查表I1-4", "component_type": "i1-intangible-assets"},
    {"sheet_name": "无形资产增加检查表I1-5", "component_type": "i1-intangible-assets"},
    {"sheet_name": "无形资产减少明细表I1-6", "component_type": "i1-intangible-assets"},
    {"sheet_name": "使用寿命检查表I1-7", "component_type": "i1-intangible-assets"},
    {"sheet_name": "无形资产权属检查表I1-8", "component_type": "i1-intangible-assets"},
    {"sheet_name": "摊销分配分析表I1-9", "component_type": "i1-intangible-assets"},
    {"sheet_name": "摊销测算表（不含减值）I1-10", "component_type": "i1-intangible-assets"},
    {"sheet_name": "摊销测算表（含减值）I1-11", "component_type": "i1-intangible-assets"},
    {"sheet_name": "减值准备测试表I1-12", "component_type": "i1-intangible-assets"},
    {"sheet_name": "可收回金额测试I1-13", "component_type": "i1-intangible-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "i1-intangible-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "i1-intangible-assets"},
]


async def _fetch_tb_data(ctx: RenderContext):
    """取 I1 三段（原值 / 累计摊销 / 减值准备）的四表数据。

    🔴 改造要点（详见 `four_table/i_cycle_accounts` 模块 docstring）：

    - 科目定位走**报表行动态解析**（项目级覆盖 → 按准则 → 行名校验），不再硬编码前缀；
    - 聚合走**叶子口径** —— 改造前对每个 `startswith('1701')` 的行累加，而 `tb_balance` 里
      `1701` 与 `1701.01~.06` 并存且父行恰等于子行之和 → 实证**恰好 2 倍虚增**；
    - 备抵段（1702/1703）`credit` 为计提、`debit` 为转回，聚合结果取绝对值。

    Returns:
        ``(tb_values, extraction)`` —— `tb_values` 键名与改造前逐字一致（前端零改动）。
    """
    try:
        extraction = await load_i_cycle_extraction(ctx, "I1")
    except Exception as e:  # noqa: BLE001 — 取数失败不阻断 render
        logger.warning("I1 四表取数失败: %s", e)
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
        logger.warning("I1 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """I1无形资产渲染策略：allResponses + projectContext + TB数据(1701+1702+1703).

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
            {"wp_id": str(ctx.wp_id), "pfx": "I1-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("I1 render responses load failed: %s", e)

    # 2. 获取TB数据（1701无形资产 + 1702累计摊销 + 1703减值准备）
    tb_values, extraction = await _fetch_tb_data(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    # 科目码改由解析结果给出（项目自定义映射生效），解析失败才回退默认三段
    account_codes = ["1701", "1702", "1703"]
    if extraction is not None:
        resolved_codes = [
            c for seg in extraction.accounts.segments for c in seg.original
        ]
        if resolved_codes:
            account_codes = resolved_codes

    payload = {
        "component_type": "i1-intangible-assets",
        "account_codes": account_codes,
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "I1",
        "sheets": I1_SHEETS,
        "meta": {"sheet_count": 17, "wp_code": "I1"},
    }

    # ─── 灰度：H/I 四表取数增强（三段 × 类别 + 取数溯源） ──────────────────
    # 🔴 只有这几个**新增**键受开关控制；`tb_values` 的口径修正（叶子聚合 + 科目动态解析）
    #    不受控制 —— 它修的是既有输出的错误值（父子双计），不是新能力。
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            if extraction is not None:
                payload["tb_source_codes"] = extraction.source_codes_payload()
                if extraction.adjudication_prefill:
                    payload["adjudication_prefill"] = extraction.adjudication_prefill
                    payload["tb_leaf_categories"] = [
                        row
                        for seg in extraction.adjudication_prefill.get("segments", [])
                        for row in seg.get("rows", [])
                    ]
                payload["hi_extraction_enabled"] = True
            # Tier A transient seed（TB核对行）
            from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
            from app.services.d_cycle_extraction.presets import resolve_effective
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
            await asyncio.wait_for(
                seed_tier_a_reconciliation(
                    ctx, "I1",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("HI extraction prefill failed (%s): %s", "I1", e)

    return payload
