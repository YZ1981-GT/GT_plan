"""D1 应收票据 — 专属渲染策略.

component_type = "d1-notes-receivable"

D1 前端组件 GtD1NotesReceivable 为自加载组件（onMounted 调 checklist-responses
自行拉取数据），按 sheetName 分发到各子组件（审定表/明细/坏账/业务模式/备查簿/
贴现背书/贴息/附注等）。因此本渲染策略只需返回轻量 html_data（project_context +
responses_snapshot），关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，
避免多 sheet dispatch 循环把 D1 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "D1-*"。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.core.config import settings
from app.services.d_cycle_extraction.presets import resolve_effective
from app.services.d_cycle_extraction.tier_a_seed import (
    seed_tier_a_reconciliation,
)
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

from ._context import RenderContext

logger = logging.getLogger(__name__)

# D1 wp_code base（Tier A 提取公式 / 锚点登记 key）
_D1_WP_CODE = "D1"


async def render(ctx: RenderContext) -> dict | None:
    """D1 应收票据渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtD1NotesReceivable，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 D1-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D1-%' "
                "LIMIT 1000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("D1 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
        "bs_date": "",
        "related_parties": [],
    }
    try:
        proj_row = (
            await db.execute(
                sa.text(
                    "SELECT client_name, audit_year, business_category "
                    "FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = (
                proj_row.business_category or ctx.business_category or ""
            )
            # bs_date（资产负债表日）：审计年度 → {year}-12-31，供 D1-3 期后回款/抽凭/截止取数使用
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("D1 render: project context 查询失败: %s", e)

    # 关联方清单：从关联方登记表（RelatedPartyRegistry）取项目级名单，供 D1-3 客户明细表关联方识别
    try:
        rp_rows = (
            await db.execute(
                sa.text(
                    "SELECT name FROM related_party_registry "
                    "WHERE project_id = :pid AND is_deleted = false "
                    "AND name IS NOT NULL AND name <> ''"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchall()
        project_context["related_parties"] = [r.name for r in rp_rows if r.name]
    except Exception as e:  # noqa: BLE001
        logger.warning("D1 render: related_parties 查询失败: %s", e)

    # 试算平衡表应收票据（科目 1121）未审/审定合计：供 D1-1 审定表试算平衡差异行预填 tb_amount，
    # 使审计师无需手工录入即可看到与 TB 的勾稽差异（审定行仍由 D1-2 明细带入，此处仅锚定 TB 数）。
    try:
        tb_row = (
            await db.execute(
                sa.text(
                    "SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadjusted, "
                    "COALESCE(SUM(audited_amount), 0) AS audited "
                    "FROM trial_balance "
                    "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                    "AND standard_account_code LIKE '1121%'"
                ),
                {"pid": str(ctx.project_id), "year": ctx.year},
            )
        ).fetchone()
        if tb_row:
            audited = float(tb_row.audited or 0)
            unadjusted = float(tb_row.unadjusted or 0)
            # 审定优先；审定为 0 时回退未审（TB 尚未回写审定数的场景）
            project_context["tb_amount"] = audited if audited else unadjusted
            project_context["tb_amount_unadjusted"] = unadjusted
            project_context["tb_amount_audited"] = audited
    except Exception as e:  # noqa: BLE001
        logger.warning("D1 render: trial_balance(1121) 查询失败: %s", e)

    html_data: dict = {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }

    # ─── Tier B 四表库审定表预填（D1：宁缺勿造 R3.4，ADDITIVE，灰度开关控制）───────
    # spec: d-cycle-four-table-extraction-formulas (Task 5.2 / R1.1 R2.3 R3.4 R7.1 R7.2
    #        / Property 9)
    #
    # 【宁缺勿造决策】D1-1 审定表按**票据类型固定分类**（银行承兑汇票 / 商业承兑汇票），
    # 分原值 / 坏账准备 / 净值三区块（`useD1Adjudication` GROSS_ROWS / BAD_DEBT_ROWS /
    # NET_VALUE_ROWS，固定 2 行 × 3 区块，非 D6-1 block1 那种动态叶子行）。原值区块未审数
    # 由 **D1-2 按类别明细（`D1-cat-rows`）经 cross-sheet 派生**（`useD1Adjudication`
    # categoryRows 按 category 含「银行」/「商业」匹配填入），非从 tb_balance 叶子直接填；
    # 坏账准备来自减值模型（`D1-bd-*-rows`）；净值 = 原值 − 坏账（computed 不落库）。
    # trial_balance / tb_balance 1121 **只有科目总额、无「原值/坏账/净值 × 银行/商业」组合
    # 维度**（分类是审计判断，非科目结构）→ 无法把 TB 干净映射到审定表分类行。故 D1 render
    # **不返回 adjudication_prefill**（不臆造分类行未审数 = 诚实的部分覆盖，对齐 R3.4）。
    #
    # D1 四表库数据的正确落点（均为既有链路，本 render 不重复介入，手工优先精度）：
    #   * D1-1 `D1-adj-tb-amount`（1121 总额，TB↔审定净值核对行）—— 已由 render 上方
    #     `project_context.tb_amount` seed（前端 `useD1Adjudication` tbSeedAmount 回退），
    #     并注册为 Tier A **可编辑**公式 `TB('1121','期末余额')`（d_cycle_extraction_presets.json，
    #     公式管理面板可查可编，求值经 get_active_filter 与 Tier B 同口径）。本 render 不重复 seed。
    #   * D1-1 分类行未审 ← D1-2 按类别明细（`D1-cat-rows`）**cross-sheet 派生**（银行/商业），
    #     非四表库直接可填。
    #   * D1-3 客户明细 `D1-cust-rows` 期后兑付 ← **序时账 1121 贷方**（`importPostSettlementFromLedger`，
    #     Tier B 复杂归集）—— 前端既有一键取数，非单条公式，本 render 不介入、不与之冲突。
    #
    # → 因此 D1 render 输出在开关开/关时**逐字节等价**（不新增 adjudication_prefill 或任何键，
    #   Property 9 天然成立，零回归）。保留此显式分支为决策文档锚点：未来若 D1-1 结构支持
    #   叶子明细行、或出现可干净映射的四表库维度，可在此接入 Tier B seed。
    if settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        logger.debug(
            "D1 render: 宁缺勿造（R3.4）— 无干净 TB→审定表分类行映射（票据类型固定分类），"
            "不发 adjudication_prefill（wp_id=%s）",
            ctx.wp_id,
        )
        # ─── Tier A 公式驱动 TB 核对行 transient seed（P0-1 主机制）──────────────
        # spec: d-cycle-tier-a-writeback-detail-seed R3（决策1/3 / Property 6/7/10/11/13）
        # 用 resolve_effective 的有效 Tier A 公式（默认 TB('1121','期末余额')）求值 transient
        # seed 单标量 TB↔审定净值核对行锚点 D1-adj-tb-amount 进 responses_snapshot（不落库；
        # 手工优先；disabled 跳过；写对字段 remark；fail-open）。主开关关（默认）→ 不 seed，零回归。
        try:
            await seed_tier_a_reconciliation(
                ctx,
                _D1_WP_CODE,
                responses_snapshot,
                resolve_effective=resolve_effective,
                evaluate_wp_formula_expression=evaluate_wp_formula_expression,
            )
        except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
            logger.warning("D1 render: Tier A seed 兜底异常（fail-open）: %s", e)

    return html_data
