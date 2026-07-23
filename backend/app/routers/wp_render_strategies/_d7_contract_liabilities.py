"""D7 合同负债 — 专属渲染策略.

component_type = "d7-contract-liabilities"
返回 html_data 含：审定表双区块结构 + 明细表行数据 + 各sheet配置。
数据持久化在 checklist_responses 表，item_id前缀为 "D7-{sheetCode}-{field}"。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """D7 合同负债渲染策略.

    返回完整 html_data：
    - sections: 各sheet元数据配置
    - adjudication_config: 审定表双区块固定行结构
    - project_context: 项目上下文
    - disclosure_visibility: 适用性标准判断
    - responses_snapshot: 关键item_id的已保存数据
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 审定表双区块固定行结构 ───────────────────────────────────────────
    adjudication_config = {
        "blocks": [
            {
                "blockKey": "nature",
                "blockTitle": "一、按性质分类",
                "rows": [
                    {"rowKey": "revenue", "label": "预收货款"},
                    {"rowKey": "development", "label": "开发项目预收款"},
                    {"rowKey": "engineering", "label": "预收工程款"},
                    {"rowKey": "other", "label": "其他"},
                ],
                "subtotalLabel": "小计",
                "deductionLabel": "减：计入其他非流动负债的合同负债",
                "totalLabel": "合同负债合计",
            },
            {
                "blockKey": "aging",
                "blockTitle": "二、按账龄分类",
                "rows": [
                    {"rowKey": "within-1-year", "label": "1年以内(含1年)"},
                    {"rowKey": "1-to-2-years", "label": "1至2年(含2年)"},
                    {"rowKey": "2-to-3-years", "label": "2至3年(含3年)"},
                    {"rowKey": "over-3-years", "label": "3年以上"},
                ],
                "totalLabel": "合计",
                "extraRows": ["试算平衡表数", "差异数"],
            },
        ],
        "columns": [
            "项目", "期初未审", "期初AJE", "期初RJE", "期初审定",
            "期末未审", "期末AJE", "期末RJE", "期末审定", "变动额", "变动率", "原因分析",
        ],
    }

    # ─── sections 结构定义（9个sheet） ─────────────────────────────────────
    sections = [
        {"code": "D7A", "label": "合同负债审计程序表D7A", "type": "procedure"},
        {"code": "D7-1", "label": "合同负债审定表D7-1", "type": "adjudication"},
        {"code": "D7-2", "label": "合同负债明细表D7-2", "type": "detail"},
        {"code": "D7-3", "label": "合同负债调整分录汇总D7-3", "type": "adjustment"},
        {"code": "D7-4", "label": "合同负债分析表D7-4", "type": "analysis"},
        {"code": "D7-5", "label": "账龄1年以上合同负债检查D7-5", "type": "long_term"},
        {"code": "D7-6", "label": "关联方合同负债检查D7-6", "type": "related_party"},
        {"code": "D7-7", "label": "合同负债凭证检查D7-7", "type": "voucher_check"},
        {"code": "D7-NOTE", "label": "合同负债附注披露", "type": "disclosure"},
    ]

    # ─── 从 checklist_responses 加载关键数据快照 ──────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D7-%' "
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
        logger.warning("D7 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)
        try:
            await db.rollback()
        except Exception:
            pass

    # ─── 项目上下文 + 适用性判断 ─────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "applicable_standards": "",
        "bs_date": "",
        "related_parties": [],
        "tb_amount": 0,
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
            if isinstance(raw_standards, dict):
                project_context["applicable_standards"] = raw_standards.get("type", "")
            else:
                project_context["applicable_standards"] = str(raw_standards or "")
            # bs_date 供期后窗口判断
            audit_year = proj_row.audit_year or ""
            project_context["bs_date"] = f"{audit_year}-12-31" if audit_year else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("D7 render: project context 查询失败: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass

    # ─── related_parties（关联方清单） ────────────────────────────────────
    try:
        rp_result = await db.execute(
            sa.text(
                "SELECT name FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        project_context["related_parties"] = [
            row.name for row in rp_result.fetchall() if row.name
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("D7 render: related_parties 查询失败: %s", e)
        project_context["related_parties"] = []
        try:
            await db.rollback()
        except Exception:
            pass

    # ─── tb_amount（科目2205期末审定数，供TB自动预填） ─────────────────────
    try:
        tb_result = await db.execute(
            sa.text(
                "SELECT COALESCE(SUM(COALESCE(audited_amount, unadjusted_amount)), 0) AS amt "
                "FROM trial_balance "
                "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                "AND standard_account_code LIKE '2205%'"
            ),
            {"pid": str(ctx.project_id), "year": int(project_context["audit_year"] or 0)},
        )
        tb_row = tb_result.fetchone()
        if tb_row:
            project_context["tb_amount"] = float(tb_row.amt)
    except Exception as e:  # noqa: BLE001
        logger.warning("D7 render: tb_amount 查询失败: %s", e)
        project_context["tb_amount"] = 0

    # 附注适用性
    standards = str(project_context.get("applicable_standards", "")).lower()
    disclosure_visibility = {
        "listed": "listed" in standards,
        "soe": "soe" in standards,
    }

    return {
        "sections": sections,
        "adjudication_config": adjudication_config,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
    }
