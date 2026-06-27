"""A9-1 向管理层通报内部控制缺陷沟通函 — 专属渲染策略.

component_type = "a9-1-deficiency-letter"
7 区块组件（收件人/正文引言/独立性声明/内部控制缺陷/审计委员会监督/签发区/管理层回复区）。
核心价值：与 B22B 内控缺陷评价表联动，按 severity 自动分组。
数据持久化在 checklist_responses 表，item_id 前缀 `a91-`。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


@dataclass
class DeficiencyItem:
    """缺陷条目数据结构."""

    id: str
    description: str
    impact: str
    recommendation: str
    index_ref: str | None
    source: str  # "b22b" | "manual"
    severity: str  # "major" | "significant" | "general"


async def _load_section_data(
    ctx: RenderContext, prefix: str = "a91"
) -> tuple[dict, dict[str, list["DeficiencyItem"]]]:
    """加载 checklist_responses 中已保存的 section_data 和 manual_deficiencies.

    参数化 prefix 支持 A9-1 (a91) 和 A9-2 (a92) 共用。
    返回 (section_data, manual_deficiencies)。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    section_data: dict = {
        "addressee": {"client_name": "", "custom_text": None},
        "independence": {
            "team_independent": None,
            "no_relationships": None,
            "no_relationships_detail": None,
            "safeguards_taken": None,
            "non_audit_services": None,
            "non_audit_services_detail": None,
        },
        "committee": {"applicability": None, "description": None},
        "signature": {"date": None},
        "response": {
            "opinion": None,
            "conclusion": None,
            "representative": None,
            "response_date": None,
        },
    }

    manual_deficiencies: dict[str, list[DeficiencyItem]] = {
        "major": [],
        "significant": [],
        "general": [],
    }

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                f"AND item_id LIKE '{prefix}-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            _parse_row(item_id, row, section_data, manual_deficiencies, prefix)
    except Exception as e:  # noqa: BLE001
        logger.warning("%s checklist_responses 查询失败 wp_id=%s: %s", prefix.upper(), wp_id, e)

    return section_data, manual_deficiencies


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文信息（复用于 A9-1 和 A9-2）."""
    project_context: dict = {
        "client_name": "",
        "firm_name": "致同会计师事务所（特殊普通合伙）",
        "audit_report_date": None,
    }
    try:
        proj_result = await ctx.db.execute(
            sa.text(
                "SELECT client_name, audit_year FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            year = proj_row.audit_year
            if year:
                project_context["audit_report_date"] = f"{year}年12月31日"
    except Exception as e:  # noqa: BLE001
        logger.warning("project context 查询失败: %s", e)
    return project_context


async def render(ctx: RenderContext) -> dict | None:
    """A9-1 内控缺陷沟通函渲染策略.

    返回 {section_data, deficiency_list, project_context, b22b_warning}
    """
    # ─── 1. 加载 section_data + manual_deficiencies ──────────────────────
    section_data, manual_deficiencies = await _load_section_data(ctx, prefix="a91")

    # ─── 2. 从 B22B 加载缺陷数据 ────────────────────────────────────────
    b22b_result = await _load_b22b_deficiencies(ctx.project_id, ctx.db)
    b22b_deficiencies: dict[str, list] = b22b_result["deficiencies"]
    b22b_warning: str | None = b22b_result["warning"]

    # ─── 3. 合并缺陷列表（B22B + 手动） ─────────────────────────────────
    deficiency_list: dict[str, list] = {"major": [], "significant": [], "general": []}
    for severity in ("major", "significant", "general"):
        deficiency_list[severity] = (
            [asdict(d) for d in b22b_deficiencies.get(severity, [])]
            + [asdict(d) for d in manual_deficiencies.get(severity, [])]
        )

    # ─── 4. 项目上下文 ──────────────────────────────────────────────────
    project_context = await _load_project_context(ctx)

    # 自动填充收件人
    if not section_data["addressee"]["client_name"]:
        section_data["addressee"]["client_name"] = project_context["client_name"]

    return {
        "section_data": section_data,
        "deficiency_list": deficiency_list,
        "project_context": project_context,
        "b22b_warning": b22b_warning,
    }


def _parse_row(
    item_id: str,
    row,
    section_data: dict,
    manual_deficiencies: dict[str, list[DeficiencyItem]],
    prefix: str = "a91",
) -> None:
    """解析单条 checklist_response 行并填入对应结构.

    参数化 prefix 支持 a91/a92 共用。
    """
    # addressee
    if item_id == f"{prefix}-addressee-client_name":
        section_data["addressee"]["client_name"] = row.conclusion or row.remark or ""
        section_data["addressee"]["custom_text"] = row.remark or None

    # independence
    elif item_id.startswith(f"{prefix}-independence-"):
        key = item_id.removeprefix(f"{prefix}-independence-")
        if key in ("team_independent", "no_relationships", "safeguards_taken", "non_audit_services"):
            section_data["independence"][key] = row.conclusion or None
            # detail fields stored in remark
            if key == "no_relationships" and row.remark:
                section_data["independence"]["no_relationships_detail"] = row.remark
            elif key == "non_audit_services" and row.remark:
                section_data["independence"]["non_audit_services_detail"] = row.remark

    # deficiency (manual entries stored as JSON in remark)
    elif item_id.startswith(f"{prefix}-deficiency-"):
        severity = item_id.removeprefix(f"{prefix}-deficiency-")
        if severity in ("major", "significant", "general") and row.remark:
            try:
                items = json.loads(row.remark)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            manual_deficiencies[severity].append(
                                DeficiencyItem(
                                    id=item.get("id", ""),
                                    description=item.get("description", ""),
                                    impact=item.get("impact", ""),
                                    recommendation=item.get("recommendation", ""),
                                    index_ref=item.get("indexRef") or item.get("index_ref"),
                                    source="manual",
                                    severity=severity,
                                )
                            )
            except (json.JSONDecodeError, TypeError):
                logger.warning("%s deficiency JSON 解析失败 item_id=%s", prefix.upper(), item_id)

    # committee
    elif item_id == f"{prefix}-committee-applicability":
        section_data["committee"]["applicability"] = row.conclusion or None
        section_data["committee"]["description"] = row.remark or None

    # signature
    elif item_id == f"{prefix}-signature-date":
        section_data["signature"]["date"] = row.conclusion or None

    # response
    elif item_id.startswith(f"{prefix}-response-"):
        key = item_id.removeprefix(f"{prefix}-response-")
        if key in ("opinion", "conclusion", "representative"):
            section_data["response"][key] = row.remark or row.conclusion or None
        elif key == "date":
            section_data["response"]["response_date"] = row.conclusion or None


# Backward-compatible alias for tests that reference the old name
_parse_a91_row = _parse_row


async def _load_b22b_deficiencies(project_id, db) -> dict:
    """从 B22B 底稿的 checklist_responses 中提取已评价缺陷.

    1. 通过 wp_index JOIN working_papers 找到同项目的 B22B 底稿
    2. 从 checklist_responses (item_id LIKE 'b22b-deficiency-%') 读取缺陷列表
    3. 按 severity 字段分组
    4. 返回 {"deficiencies": {...}, "warning": str | None}
    """
    deficiencies: dict[str, list[DeficiencyItem]] = {
        "major": [],
        "significant": [],
        "general": [],
    }

    # Find B22B workpaper for the same project
    try:
        b22b_result = await db.execute(
            sa.text(
                "SELECT wp.id AS wp_id "
                "FROM wp_index wi "
                "JOIN working_papers wp ON wp.wp_index_id = wi.id "
                "WHERE wi.wp_code = 'B22B' AND wp.project_id = :project_id "
                "LIMIT 1"
            ),
            {"project_id": str(project_id)},
        )
        b22b_row = b22b_result.fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning("A9-1 B22B 底稿查询失败 project_id=%s: %s", project_id, e)
        return {"deficiencies": deficiencies, "warning": "B22B查询失败"}

    if not b22b_row:
        return {"deficiencies": deficiencies, "warning": "未找到B22B内控缺陷评价表"}

    # Load deficiency data from B22B checklist_responses
    try:
        cr_result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'b22b-deficiency-%'"
            ),
            {"wp_id": str(b22b_row.wp_id)},
        )
        for row in cr_result.fetchall():
            if not row.remark:
                continue
            try:
                data = json.loads(row.remark)
                if isinstance(data, dict):
                    severity = data.get("severity", "general")
                    if severity not in ("major", "significant", "general"):
                        severity = "general"
                    deficiencies[severity].append(
                        DeficiencyItem(
                            id=data.get("id", row.item_id),
                            description=data.get("description", ""),
                            impact=data.get("impact", ""),
                            recommendation=data.get("recommendation", ""),
                            index_ref=data.get("index_ref"),
                            source="b22b",
                            severity=severity,
                        )
                    )
            except (json.JSONDecodeError, TypeError):
                logger.warning("B22B deficiency JSON 解析失败 item_id=%s", row.item_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("A9-1 B22B checklist_responses 查询失败: %s", e)
        return {"deficiencies": deficiencies, "warning": "B22B缺陷数据读取失败"}

    return {"deficiencies": deficiencies, "warning": None}
