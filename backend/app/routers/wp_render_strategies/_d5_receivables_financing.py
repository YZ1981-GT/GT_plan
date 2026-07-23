"""D5 应收款项融资 — 专属渲染策略.

component_type = "d5-receivables-financing"
返回 html_data 含：审定表OCI结构 + 明细表行数据 + FV测算行数据 + 各sheet配置。
数据持久化在 checklist_responses 表，item_id前缀为 "D5-{sheetCode}-{field}"。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


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

    # ─── TB 自动取数（科目 1124）──────────────────────────────────────────
    tb_amount = 0
    try:
        tb_result = await db.execute(
            sa.text(
                "SELECT COALESCE(audited_amount, unadjusted_amount, 0) AS amount "
                "FROM trial_balance "
                "WHERE project_id = :pid AND standard_account_code LIKE '1124%' "
                "ORDER BY standard_account_code "
                "LIMIT 1"
            ),
            {"pid": str(ctx.project_id)},
        )
        tb_row = tb_result.fetchone()
        if tb_row:
            tb_amount = float(tb_row.amount or 0)
    except Exception as e:
        logger.warning("D5 render: trial_balance 1124 查询失败: %s", e)

    project_context["tb_amount"] = tb_amount

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

    return {
        "sections": sections,
        "adjudication_config": adjudication_config,
        "detail_columns": detail_columns,
        "fv_columns": fv_columns,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
    }
