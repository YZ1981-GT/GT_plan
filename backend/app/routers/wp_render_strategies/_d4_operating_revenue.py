"""D4 营业收入 — 专属渲染策略.

component_type = "d4-operating-revenue"
返回 html_data 含：sections结构 / visible_groups（基于business_category）/ sheet配置。
数据持久化在 checklist_responses 表，item_id前缀为 "D4-{sheetCode}-{field}"。
"""

from __future__ import annotations

import json
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

# D4 wp_code base（Tier A 提取公式 / 锚点登记 key）
_D4_WP_CODE = "D4"

# IPO/舞弊组可见性关键字
_IPO_KEYWORDS = ("ipo", "listed", "neeq", "restructuring", "fraud_risk")


def _is_ipo_visible(business_category: str) -> bool:
    """判断IPO/舞弊组一级Tab是否可见"""
    if not business_category:
        return False
    bc_lower = business_category.lower()
    return any(kw in bc_lower for kw in _IPO_KEYWORDS)


async def render(ctx: RenderContext) -> dict | None:
    """D4 营业收入渲染策略.

    返回完整 html_data：
    - sections: 7组嵌套Tab结构配置
    - visible_groups: 各组可见性标记
    - project_context: 项目上下文
    - responses_snapshot: 关键item_id的已保存数据
    """
    wp_id = ctx.wp_id
    db = ctx.db
    business_category = ctx.business_category or ""

    # ─── 可见性判断 ────────────────────────────────────────────────────────
    ipo_visible = _is_ipo_visible(business_category)

    visible_groups = {
        "core": True,
        "policy": True,
        "analysis": True,
        "inspection": True,
        "related": True,
        "ipo": ipo_visible,
        "other": True,
    }

    # ─── sections 结构定义 ─────────────────────────────────────────────────
    sections = [
        {
            "key": "core",
            "label": "核心",
            "sheets": [
                {"code": "D4-INDEX", "label": "底稿目录"},
                {"code": "D4-1", "label": "审定表"},
                {"code": "D4-2", "label": "主营明细"},
                {"code": "D4-3", "label": "其他明细"},
                {"code": "D4-4", "label": "调整分录"},
                {"code": "D4-NOTE-LISTED", "label": "附注(上市)"},
                {"code": "D4-NOTE-SOE", "label": "附注(国企)"},
            ],
        },
        {
            "key": "policy",
            "label": "政策",
            "sheets": [
                {"code": "D4-5", "label": "会计政策检查"},
            ],
        },
        {
            "key": "analysis",
            "label": "分析程序",
            "sheets": [
                {"code": "D4-6", "label": "重要指标"},
                {"code": "D4-7", "label": "毛利率月度"},
                {"code": "D4-8", "label": "产品毛利"},
                {"code": "D4-9", "label": "客户结构"},
                {"code": "D4-10", "label": "客户价格"},
                {"code": "D4-11", "label": "产品价格"},
            ],
        },
        {
            "key": "inspection",
            "label": "检查程序",
            "sheets": [
                {"code": "D4-12", "label": "合同检查"},
                {"code": "D4-13", "label": "ERP核对"},
                {"code": "D4-14", "label": "发生检查"},
                {"code": "D4-15", "label": "完整性检查"},
                {"code": "D4-16", "label": "出口核对"},
                {"code": "D4-17", "label": "截止(正向)"},
                {"code": "D4-18", "label": "截止(反向)"},
                {"code": "D4-19", "label": "折扣折让"},
                {"code": "D4-20", "label": "退货检查"},
            ],
        },
        {
            "key": "related",
            "label": "关联方",
            "sheets": [
                {"code": "D4-21", "label": "关联价格分析"},
            ],
        },
        {
            "key": "ipo",
            "label": "IPO/舞弊",
            "sheets": [
                {"code": "D4-22A", "label": "IPO程序表"},
                {"code": "D4-22", "label": "IPO指标"},
                {"code": "D4-23", "label": "发票对比"},
                {"code": "D4-24", "label": "第三方回款"},
                {"code": "D4-25", "label": "经销商"},
                {"code": "D4-26", "label": "境外销售"},
                {"code": "D4-27", "label": "未披露关联方"},
                {"code": "D4-28", "label": "核查清单"},
                {"code": "D4-29", "label": "核查详细"},
                {"code": "D4-30", "label": "访谈汇总"},
                {"code": "D4-31", "label": "访谈详细"},
                {"code": "D4-32", "label": "资金流水"},
            ],
        },
        {
            "key": "other",
            "label": "其他收入",
            "sheets": [
                {"code": "D4-33", "label": "其他毛利"},
                {"code": "D4-34", "label": "合同测算"},
                {"code": "D4-35", "label": "其他检查"},
                {"code": "D4-36", "label": "其他截止"},
            ],
        },
    ]

    # ─── 从 checklist_responses 加载关键数据快照 ──────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D4-%' "
                "LIMIT 500"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("D4 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": business_category,
        "applicable_standards": "",
        "has_export_business": False,
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = proj_row.business_category or business_category
    except Exception as e:  # noqa: BLE001
        logger.warning("D4 render: project context 查询失败: %s", e)

    html_data = {
        "sections": sections,
        "visible_groups": visible_groups,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }

    # ─── Tier B 四表库审定表预填（D4：宁缺勿造 R3.4，ADDITIVE，灰度开关控制）───────
    # spec: d-cycle-four-table-extraction-formulas (R1.1 / R2.3 / R3.4 / R7.1 / R7.2
    #        / Property 9)
    #
    # 【宁缺勿造决策】D4-1 审定表主营/其他收入明细行按**产品/项目**（`D4-1-adj-rows`），
    # 由 D4-2 主营明细（`D4-2-rows`，序时账 6001 贷方按产品×月归集）+ D4-3 其他明细
    # （`D4-3-rows`）经 SUMIF 聚合派生（useD4Adjudication mainRevenueByProduct）；而
    # trial_balance / tb_balance 的 6001/6051 **只有科目总额、无产品/项目维度**（产品是
    # 序时账明细维度，非科目结构）→ 无法把 TB 干净映射到明细行 → D4 render **不返回
    # adjudication_prefill**（不臆造明细行 = 诚实部分覆盖，对齐 R3.4）。
    #
    # D4 四表库数据的正确落点（均为既有链路，本 render 不介入，手工优先精度）：
    #   * D4-1 `D4-1-adj-tb-6001`/`D4-1-adj-tb-6051`（6001 主营/6051 其他审定发生额，
    #     TB↔审定小计核对标量）—— 注册为 Tier A **可编辑**公式 TB('6001','审定数')/
    #     TB('6051','审定数')（d_cycle_extraction_presets.json，公式管理面板可查可编，
    #     求值经 get_active_filter 与 Tier B 同口径）。
    #   * D4-2 主营明细 ← **序时账 6001 贷方按产品×月归集**（d4_ledger_monthly_by_product
    #     resolver，前端「从序时账取数」，Tier B 复杂归集）—— 非单条公式，本 render 不介入。
    #
    # → 因此 D4 render 输出在开关开/关时**逐字节等价**（不新增任何键，Property 9 天然成立，
    #   零回归）。收入类 occurrence 若未来 6001 出现产品级子科目、且可干净映射，可在此接入
    #   Tier B seed（build_d_adjudication_prefill mode='occurrence'）。
    if settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        logger.debug(
            "D4 render: 宁缺勿造（R3.4）— 无干净 TB→审定表明细行映射（收入按产品/项目 "
            "SUMIF from D4-2/D4-3），不发 adjudication_prefill（wp_id=%s）",
            wp_id,
        )
        # ─── Tier A 公式驱动 TB 核对行 transient seed（P0-1 主机制，D4 双标量）────────
        # spec: d-cycle-tier-a-writeback-detail-seed R3（决策1/3 / Property 6/7/10/11/13）
        # D4 是**双标量**：resolve_effective 返回两条绑定——D4-1-adj-tb-6001（TB('6001','审定数')
        # 主营）+ D4-1-adj-tb-6051（TB('6051','审定数') 其他），共享助手的锚点遍历天然覆盖两条，
        # 各自 transient seed 进 responses_snapshot（不落库；手工优先；disabled 跳过；写对字段
        # remark；fail-open，单条求值失败不影响另一条）。主开关关（默认）→ 不 seed，零回归。
        try:
            await seed_tier_a_reconciliation(
                ctx,
                _D4_WP_CODE,
                responses_snapshot,
                resolve_effective=resolve_effective,
                evaluate_wp_formula_expression=evaluate_wp_formula_expression,
            )
        except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
            logger.warning("D4 render: Tier A seed 兜底异常（fail-open）: %s", e)

    return html_data
