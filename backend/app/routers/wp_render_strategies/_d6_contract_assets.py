"""D6 合同资产 — 专属渲染策略.

component_type = "d6-contract-assets"
返回 html_data 含：审定表三区块结构 + 明细表行数据 + 减值明细 + ECL组合数据 + 各sheet配置。
数据持久化在 checklist_responses 表，item_id前缀为 "D6-{sheetCode}-{field}"。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """D6 合同资产渲染策略.

    返回完整 html_data：
    - sections: 各sheet元数据配置
    - adjudication_config: 审定表三区块固定行结构
    - detail_columns: 明细表D6-2 30列定义
    - impairment_columns: 减值准备明细D6-3 14列定义
    - ecl_config: ECL测算D6-8配置
    - project_context: 项目上下文
    - disclosure_visibility: 适用性标准判断
    - responses_snapshot: 关键item_id的已保存数据
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 审定表三区块固定行结构 ───────────────────────────────────────────
    adjudication_config = {
        "blocks": [
            {
                "blockKey": "block1",
                "blockTitle": "一、合同资产原值",
                "subtotalLabel": "小计",
                "deductionLabel": "减：列示于其他非流动资产的合同资产",
                "totalLabel": "合同资产原值小计",
            },
            {
                "blockKey": "block2",
                "blockTitle": "二、合同资产坏账准备",
                "subtotalLabel": "小计",
                "deductionLabel": "减：列示于其他非流动资产的合同资产坏账准备",
                "totalLabel": "合同资产坏账准备小计",
            },
            {
                "blockKey": "block3",
                "blockTitle": "三、合同资产净值",
                "subtotalLabel": "小计",
                "deductionLabel": "减：列示于其他非流动资产的合同资产净值",
                "totalLabel": "合同资产净值合计",
                "extraRows": ["试算平衡表数", "差异数"],
            },
        ],
        "columns": [
            "项目", "期初未审", "期初AJE", "期初RJE", "期初审定",
            "期末未审", "期末AJE", "期末RJE", "期末审定", "变动额", "变动率", "原因分析",
        ],
    }

    # ─── sections 结构定义（12个sheet） ────────────────────────────────────
    sections = [
        {"code": "D6A", "label": "实质性程序表D6A", "type": "procedure"},
        {"code": "D6-1", "label": "合同资产审定表D6-1", "type": "adjudication"},
        {"code": "D6-2", "label": "合同资产明细表D6-2", "type": "detail"},
        {"code": "D6-3", "label": "合同资产减值准备明细表D6-3", "type": "impairment_detail"},
        {"code": "D6-4", "label": "调整分录汇总表D6-4", "type": "adjustment"},
        {"code": "D6-5", "label": "关联关系及交易检查D6-5", "type": "related_party"},
        {"code": "D6-6", "label": "合同资产检查表D6-6", "type": "inspection"},
        {"code": "D6-7", "label": "合同资产减值准备会计政策检查D6-7", "type": "policy_check"},
        {"code": "D6-8", "label": "合同资产减值准备测算D6-8", "type": "ecl_calculation"},
        {"code": "D6-9", "label": "减值准备转回核销检查D6-9", "type": "writeoff_check"},
        {"code": "D6-NOTE-LISTED", "label": "合同资产附注披露信息（上市公司）", "type": "disclosure"},
        {"code": "D6-NOTE-SOE", "label": "合同资产附注披露信息（国企）", "type": "disclosure"},
    ]

    # ─── ECL测算配置 ──────────────────────────────────────────────────────
    ecl_config = {
        "single_columns": [
            {"key": "debtorName", "label": "债务人名称", "width": 140, "editable": True},
            {"key": "auditedBalance", "label": "审定余额①", "width": 110, "editable": True, "type": "number"},
            {"key": "lossRate", "label": "损失率②", "width": 90, "editable": True, "type": "number"},
            {"key": "expectedProvision", "label": "应计提③", "width": 100, "editable": False, "formula": "①×②"},
            {"key": "bookBalance", "label": "账面余额④", "width": 100, "editable": True, "type": "number"},
            {"key": "difference", "label": "差异⑤", "width": 90, "editable": False, "formula": "③-④"},
            {"key": "basis", "label": "依据", "width": 120, "editable": True},
            {"key": "indexRef", "label": "索引号", "width": 80, "editable": True},
        ],
        "aging_bands": ["1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上"],
    }

    # ─── 从 checklist_responses 加载关键数据快照 ──────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D6-%' "
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
        logger.warning("D6 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
                "SELECT client_name, audit_year, business_category, "
                "applicable_standard_v2 AS applicable_standards "
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
                project_context["applicable_standards"] = (
                    raw_standards.get("type")
                    or raw_standards.get("entity_type")
                    or ""
                )
            elif isinstance(raw_standards, str):
                project_context["applicable_standards"] = raw_standards
            else:
                project_context["applicable_standards"] = ""
    except Exception as e:  # noqa: BLE001
        logger.warning("D6 render: project context 查询失败: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass

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
        "ecl_config": ecl_config,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
    }
