"""D5 应收款项融资 — 专属渲染策略.

component_type = "d5-receivables-financing"
返回 html_data 含：审定表OCI结构 + 明细表行数据 + FV测算行数据 + 各sheet配置。
数据持久化在 checklist_responses 表，item_id前缀为 "D5-{sheetCode}-{field}"。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from app.core.config import settings
from app.services.d_cycle_extraction.d_account_resolver import (
    resolve_d_cycle_account_codes,
)
from app.services.d_cycle_extraction.d_tb_fetch import (
    build_d_tb_source_codes,
    fetch_d_cycle_tb,
    seed_tb_amount_scalars,
)
from app.services.d_cycle_extraction.presets import resolve_effective
from app.services.d_cycle_extraction.tier_a_seed import (
    seed_tier_a_reconciliation,
)
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

from ._context import RenderContext

logger = logging.getLogger(__name__)

# D5 wp_code base（Tier A 提取公式 / 锚点登记 key）
_D5_WP_CODE = "D5"


async def render(ctx: RenderContext) -> dict | None:
    """D5 应收款项融资渲染策略.

    返回完整 html_data：
    - sections: 各sheet元数据配置
    - adjudication_config: 审定表固定行结构（含OCI减项）
    - project_context: 项目上下文
    - disclosure_visibility: 适用性标准判断
    - responses_snapshot: 关键item_id的已保存数据
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 审定表固定行结构（含OCI特殊减项） ────────────────────────────────
    adjudication_config = {
        "rows": [
            {"rowKey": "notes-receivable", "label": "应收票据", "isFromCrossSheet": True, "isEditable": True},
            {"rowKey": "accounts-receivable", "label": "应收账款", "isFromCrossSheet": True, "isEditable": True},
            {"rowKey": "subtotal", "label": "小计", "isComputed": True, "isEditable": False},
            {"rowKey": "oci-change", "label": "减：其他综合收益-公允价值变动", "isFromFV": True, "isEditable": False},
            {"rowKey": "fv-total", "label": "应收款项融资公允价值合计", "isComputed": True, "isEditable": False},
            {"rowKey": "trial-balance", "label": "试算平衡表数", "isFromTB": True, "isEditable": False},
            {"rowKey": "difference", "label": "差异数", "isComputed": True, "isEditable": False},
        ],
        "columns": [
            "项目", "期初未审", "期初AJE", "期初RJE", "期初审定",
            "期末未审", "期末AJE", "期末RJE", "期末审定", "变动额", "变动率",
        ],
    }

    # ─── sections 结构定义（6个Tab） ──────────────────────────────────────
    sections = [
        {"code": "D5A", "label": "D5A 程序表", "type": "procedure"},
        {"code": "D5-1", "label": "D5-1 审定表", "type": "adjudication"},
        {"code": "D5-2", "label": "D5-2 明细表", "type": "detail"},
        {"code": "D5-3", "label": "D5-3 调整分录", "type": "adjustment"},
        {"code": "D5-4", "label": "D5-4 公允价值测算", "type": "fair_value"},
        {"code": "D5-NOTE", "label": "附注", "type": "disclosure"},
    ]

    # ─── 明细表D5-2列定义 ─────────────────────────────────────────────────
    detail_columns = [
        {"key": "category", "label": "类别", "width": 100, "editable": True, "type": "select", "options": ["应收票据", "应收账款"]},
        {"key": "itemName", "label": "明细项目", "width": 140, "editable": True},
        {"key": "priorUnadjusted", "label": "期初未审", "width": 100, "editable": True, "type": "number"},
        {"key": "priorAje", "label": "期初AJE", "width": 90, "editable": True, "type": "number"},
        {"key": "priorRje", "label": "期初RJE", "width": 90, "editable": True, "type": "number"},
        {"key": "priorAudited", "label": "期初审定", "width": 100, "editable": False, "formula": "C+D+E"},
        {"key": "ociImpairment", "label": "OCI减值", "width": 90, "editable": True, "type": "number"},
        {"key": "periodIncrease", "label": "本期增加", "width": 100, "editable": True, "type": "number"},
        {"key": "periodDecrease", "label": "本期减少", "width": 100, "editable": True, "type": "number"},
        {"key": "endBalance", "label": "期末余额", "width": 100, "editable": False, "formula": "F+H-I"},
        {"key": "entityReclass", "label": "重分类", "width": 90, "editable": True, "type": "number"},
        {"key": "endUnadjusted", "label": "期末未审", "width": 100, "editable": False, "formula": "J+K"},
        {"key": "endAje", "label": "期末AJE", "width": 90, "editable": True, "type": "number"},
        {"key": "endRje", "label": "期末RJE", "width": 90, "editable": True, "type": "number"},
        {"key": "endAudited", "label": "期末审定", "width": 100, "editable": False, "formula": "L+M+N"},
        {"key": "endOciImpairment", "label": "期末OCI减值", "width": 100, "editable": True, "type": "number"},
        {"key": "postRealized", "label": "期后兑现金额", "width": 110, "editable": True, "type": "number"},
        {"key": "eclStage", "label": "ECL阶段", "width": 90, "editable": True, "type": "select", "options": ["阶段一", "阶段二", "阶段三"]},
        {"key": "remark", "label": "备注", "width": 120, "editable": True},
    ]

    # ─── 公允价值D5-4列定义 ───────────────────────────────────────────────
    fv_columns = [
        {"key": "category", "label": "类别", "width": 100, "editable": True, "type": "select", "options": ["应收票据", "应收账款"]},
        {"key": "itemName", "label": "明细项目", "width": 140, "editable": True},
        {"key": "billNo", "label": "票据号", "width": 120, "editable": True},
        {"key": "faceValue", "label": "票面金额", "width": 110, "editable": True, "type": "number"},
        {"key": "measurementDate", "label": "计量日", "width": 110, "editable": True, "type": "date"},
        {"key": "maturityDate", "label": "到期日", "width": 110, "editable": True, "type": "date"},
        {"key": "remainingDays", "label": "剩余天数", "width": 90, "editable": False, "formula": "F-E"},
        {"key": "discountRate", "label": "贴现利率", "width": 90, "editable": True, "type": "number"},
        {"key": "discountInterest", "label": "贴现利息", "width": 100, "editable": False, "formula": "D×H×G÷360"},
        {"key": "discountAmount", "label": "贴现金额", "width": 100, "editable": False, "formula": "D-I"},
        {"key": "fairValue", "label": "公允价值", "width": 100, "editable": False, "formula": "J"},
        {"key": "fvHierarchy", "label": "层次", "width": 90, "editable": True, "type": "select", "options": ["第二层次", "第三层次"]},
        {"key": "remark", "label": "备注", "width": 120, "editable": True},
    ]

    # ─── 从 checklist_responses 加载关键数据快照 ──────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D5-%' "
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
        logger.warning("D5 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 + 适用性判断 ─────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "applicable_standards": "",
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category, applicable_standard_v2 AS applicable_standards "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = proj_row.business_category or ""
            raw_standards = proj_row.applicable_standards
            # applicable_standard_v2 可能是 JSONB(dict) 或 string 或 None
            if isinstance(raw_standards, dict):
                project_context["applicable_standards"] = raw_standards.get("type", "")
            elif isinstance(raw_standards, str):
                project_context["applicable_standards"] = raw_standards
            else:
                project_context["applicable_standards"] = ""
    except Exception as e:  # noqa: BLE001
        logger.warning("D5 render: project context 查询失败: %s", e)

    # ─── TB 自动取数：报表规则映射驱动（替代硬编码 1124）────────────────────
    # spec: d-cycle-four-table-extraction-and-disclosure-completion R1
    #
    # 改造前是硬编码 `LIKE '1124%'` 的裸 SQL，有两个缺陷（本次一并修掉）：
    #   1. **缺 `year` 过滤** → 多年度项目把所有年份加总
    #   2. 用 `ORDER BY ... LIMIT 1` 取第一行而非 `SUM` → 该科目有多行时漏数
    #
    # 🔴 关于「取不到数」：`1124` 与「应收款项融资」这个**名字**在活体 `account_chart`
    # 的两个 source 下**均零命中**，`account_mapping` 零反解、`tb_balance` 零数据行 ——
    # 这是**业务事实**（这批项目没有应收款项融资业务），不是错码（`1124` 在 CAS 里确实
    # 是应收款项融资，财会[2019]6 号新增）。故 `D5_SPEC` 刻意不给兜底码，取数为空时
    # 由 `tb_source_codes.slots` 如实呈现「本项目无此科目」而非 0。
    # 旧键 `tb_amount` 仍按改造前语义无条件写（`write_zero_when_missing=True`），
    # 避免前端从「读到 0」变成「读不到」。
    d5_codes = None
    try:
        d5_codes = await resolve_d_cycle_account_codes(ctx, _D5_WP_CODE)
        await seed_tb_amount_scalars(
            ctx, d5_codes, project_context, write_zero_when_missing=True
        )
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("D5 render: 科目解析/取数异常（fail-open）: %s", e)
        project_context.setdefault("tb_amount", 0)

    project_context["bs_date"] = f"{project_context['audit_year']}-12-31" if project_context['audit_year'] else ""

    # 关联方
    related_parties: list[str] = []
    try:
        rp_result = await db.execute(
            sa.text(
                "SELECT name FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        related_parties = [r.name for r in rp_result.fetchall() if r.name]
    except Exception as e:
        logger.warning("D5 render: related_party_registry 查询失败: %s", e)

    project_context["related_parties"] = related_parties

    # 附注适用性
    raw_std = project_context["applicable_standards"]
    standards = raw_std.lower() if isinstance(raw_std, str) else ""
    disclosure_visibility = {
        "listed": "listed" in standards,
        "soe": "soe" in standards,
    }

    html_data = {
        "sections": sections,
        "adjudication_config": adjudication_config,
        "detail_columns": detail_columns,
        "fv_columns": fv_columns,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
    }

    # ─── Tier B 四表库审定表预填（D5：宁缺勿造 R3.4，ADDITIVE，灰度开关控制）───────
    # spec: d-cycle-four-table-extraction-formulas (R1.1 / R2.3 / R3.4 / R7.1 / R7.2
    #        / Property 9)
    #
    # 【宁缺勿造决策】D5-1 审定表两固定分类行（应收票据/应收账款），未审数由 D5-2 明细
    # （`D5-2-rows`）按类别 SUMIF 聚合派生（useD5Adjudication categoryAggregation）；而
    # trial_balance / tb_balance 的 1124 **只有科目总额、无「应收票据/应收账款」类别拆分** →
    # 无法把 TB 干净映射到分类行 → D5 render **不返回 adjudication_prefill**（不臆造分类行
    # 未审数 = 诚实部分覆盖，对齐 R3.4）。OCI 公允价值变动减项来自 D5-4 测算，非四表库。
    #
    # D5 四表库数据的正确落点（均为既有链路，本 render 不介入，手工优先精度）：
    #   * D5-1 `D5-1-tb-amount`（1124 总额，试算平衡表数核对行）—— 已由前端从 render
    #     project_context.tb_amount seed；注册为 Tier A **可编辑**公式 TB('1124','期末余额')
    #     （公式管理面板可查可编，求值经 get_active_filter 与 Tier B 同口径）。
    #   * D5-2 明细 ← tb_aux_balance 1124 按**类别维度**归集 + 序时账期后兑现（Tier B 复杂
    #     归集）—— 非单条公式，本 render 不介入、不冲突。
    #
    # → 因此 D5 render 输出在开关开/关时**逐字节等价**（不新增任何键，Property 9 天然成立，
    #   零回归）。
    if settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        logger.debug(
            "D5 render: 宁缺勿造（R3.4）— 无干净 TB→审定表分类行映射（应收票据/应收账款 "
            "SUMIF from D5-2），不发 adjudication_prefill（wp_id=%s）",
            wp_id,
        )
        # ─── 取数溯源与三口径自检（新增，前端消费）────────────────────────────
        # D5 是四态之「本项目无此科目」的唯一活体样本 —— 溯源面板据 slots 呈现
        # info 级「本项目无此科目」而非把它显示成余额 0。
        if d5_codes is not None:
            try:
                d5_tb = await fetch_d_cycle_tb(ctx, d5_codes)
                html_data["tb_source_codes"] = build_d_tb_source_codes(d5_codes, d5_tb)
                html_data["parent_check"] = d5_tb.parent_check
            except Exception as e:  # noqa: BLE001 — fail-open
                logger.warning("D5 render: 取数溯源构造异常（fail-open）: %s", e)

        # ─── Tier A 公式驱动 TB 核对行 transient seed（P0-1 主机制）──────────────
        # spec: d-cycle-tier-a-writeback-detail-seed R3（决策1/3 / Property 6/7/10/11/13）
        # 用 resolve_effective 的有效 Tier A 公式（默认 TB('1124','期末余额')）求值 transient
        # seed 单标量 试算平衡表数核对行锚点 D5-1-tb-amount 进 responses_snapshot（不落库；
        # 手工优先；disabled 跳过；写对字段 remark；fail-open）。主开关关（默认）→ 不 seed，零回归。
        try:
            await seed_tier_a_reconciliation(
                ctx,
                _D5_WP_CODE,
                responses_snapshot,
                resolve_effective=resolve_effective,
                evaluate_wp_formula_expression=evaluate_wp_formula_expression,
            )
        except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
            logger.warning("D5 render: Tier A seed 兜底异常（fail-open）: %s", e)

    return html_data
