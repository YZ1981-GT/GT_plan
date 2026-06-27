"""A17-1 重大事项概要汇总 — 专属渲染策略.

component_type = "a17-1-audit-summary"
16 章折叠卡片（textarea/table/yn）+ 签字表(10行) + 左侧导航 + 跨引用联动。
跨引用: B50(风险评估)、A13(错报汇总)、A1-15(披露核对)。
数据持久化在 checklist_responses 表，item_id 前缀 `a171-`。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 16 章节元数据 (type: textarea / table / yn)
CHAPTERS_META: list[dict] = [
    {"number": 1, "type": "textarea", "title": "一、审计工作概况"},
    {"number": 2, "type": "textarea", "title": "二、重大会计政策及估计变更"},
    {"number": 3, "type": "textarea", "title": "三、关键审计事项"},
    {"number": 4, "type": "textarea", "title": "四、持续经营评估"},
    {"number": 5, "type": "textarea", "title": "五、审计范围调整"},
    {"number": 6, "type": "table", "title": "六、重大错报风险应对"},
    {"number": 7, "type": "textarea", "title": "七、集团审计事项"},
    {"number": 8, "type": "table", "title": "八、已审财务报表分析"},
    {"number": 9, "type": "yn", "title": "九、舞弊识别"},
    {"number": 10, "type": "yn", "title": "十、违反法规情况"},
    {"number": 11, "type": "yn", "title": "十一、关联方事项"},
    {"number": 12, "type": "yn", "title": "十二、期后事项"},
    {"number": 13, "type": "textarea", "title": "十三、审计意见"},
    {"number": 14, "type": "textarea", "title": "十四、错报汇总与处理"},
    {"number": 15, "type": "textarea", "title": "十五、与治理层沟通事项"},
    {"number": 16, "type": "textarea", "title": "十六、审计总结"},
]

# 签字表 10 行角色
SIGNATURE_ROLES: list[str] = [
    "编制人",
    "一级复核",
    "二级复核",
    "三级复核",
    "项目合伙人",
    "质量控制复核",
    "项目质量控制复核人",
    "技术复核人",
    "独立复核人",
    "其他",
]

# 跨引用 wp_code 列表
CROSS_REF_WP_CODES = ["B50", "A13", "A1-15"]


async def _load_cross_references(project_id, db) -> dict:
    """查找 B50, A13, A1-15 底稿的 wp_id."""
    cross_refs: dict[str, str | None] = {
        "b50_wp_id": None,
        "a13_wp_id": None,
        "a115_wp_id": None,
    }

    key_map = {
        "B50": "b50_wp_id",
        "A13": "a13_wp_id",
        "A1-15": "a115_wp_id",
    }

    try:
        result = await db.execute(
            sa.text(
                "SELECT wi.wp_code, wp.id AS wp_id "
                "FROM wp_index wi "
                "JOIN working_papers wp ON wp.wp_index_id = wi.id "
                "WHERE wi.wp_code IN :codes AND wp.project_id = :project_id"
            ),
            {"codes": tuple(CROSS_REF_WP_CODES), "project_id": str(project_id)},
        )
        for row in result.fetchall():
            dict_key = key_map.get(row.wp_code)
            if dict_key:
                cross_refs[dict_key] = str(row.wp_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("A17-1 跨引用查询失败 project_id=%s: %s", project_id, e)

    return cross_refs


async def render(ctx: RenderContext) -> dict | None:
    """A17-1 重大事项概要汇总渲染策略.

    返回 {chapters(16), signature_table(10), cross_references, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db
    project_id = ctx.project_id

    # ─── 1. 加载 checklist_responses (item_id LIKE 'a171-%') ─────────────
    # textarea: item_id = a171-ch{N}-content, remark = content
    # table:    item_id = a171-ch{N}-table, remark = JSON array of rows
    # yn:       item_id = a171-ch{N}-yn, conclusion = Y/N, remark = explanation
    # signature: item_id = a171-signature-{row_index}-name/date

    chapters_textarea: dict[int, str | None] = {}
    chapters_table: dict[int, list[dict]] = {}
    chapters_yn: dict[int, dict] = {}
    signature_data: dict[str, str | None] = {}

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a171-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id = row.item_id

            if item_id.startswith("a171-ch") and item_id.endswith("-content"):
                # textarea: a171-ch{N}-content
                try:
                    num_str = item_id.removeprefix("a171-ch").removesuffix("-content")
                    ch_num = int(num_str)
                    if 1 <= ch_num <= 16:
                        chapters_textarea[ch_num] = row.remark or None
                except (ValueError, IndexError):
                    pass

            elif item_id.startswith("a171-ch") and item_id.endswith("-table"):
                # table: a171-ch{N}-table
                try:
                    num_str = item_id.removeprefix("a171-ch").removesuffix("-table")
                    ch_num = int(num_str)
                    if ch_num in (6, 8):
                        if row.remark:
                            try:
                                data = json.loads(row.remark)
                                if isinstance(data, list):
                                    chapters_table[ch_num] = data
                            except (json.JSONDecodeError, TypeError):
                                logger.warning("A17-1 ch%d table JSON 解析失败", ch_num)
                except (ValueError, IndexError):
                    pass

            elif item_id.startswith("a171-ch") and item_id.endswith("-yn"):
                # yn: a171-ch{N}-yn
                try:
                    num_str = item_id.removeprefix("a171-ch").removesuffix("-yn")
                    ch_num = int(num_str)
                    if ch_num in (9, 10, 11, 12):
                        answer = row.conclusion if row.conclusion in ("Y", "N") else None
                        explanation = row.remark or None
                        chapters_yn[ch_num] = {"answer": answer, "explanation": explanation}
                except (ValueError, IndexError):
                    pass

            elif item_id.startswith("a171-signature-"):
                # signature: a171-signature-{row_index}-name / a171-signature-{row_index}-date
                signature_data[item_id] = row.conclusion or row.remark or None

    except Exception as e:  # noqa: BLE001
        logger.warning("A17-1 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 2. 加载项目上下文 ───────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_period": "",
        "preparer": None,
    }
    try:
        proj_result = await db.execute(
            sa.text("SELECT client_name, audit_year FROM projects WHERE id = :pid"),
            {"pid": str(project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            year = proj_row.audit_year
            if year:
                project_context["audit_period"] = f"{year}年度"
    except Exception as e:  # noqa: BLE001
        logger.warning("A17-1 project context 查询失败: %s", e)

    # ─── 3. 加载跨引用 wp_ids ────────────────────────────────────────────
    cross_references = await _load_cross_references(project_id, db)

    # ─── 4. 构建 chapters dict (16) ──────────────────────────────────────
    chapters: dict[str, dict] = {}
    for meta in CHAPTERS_META:
        num = meta["number"]
        ch_type = meta["type"]
        ch_data: dict = {
            "type": ch_type,
            "title": meta["title"],
        }

        if ch_type == "textarea":
            ch_data["content"] = chapters_textarea.get(num)
        elif ch_type == "table":
            ch_data["rows"] = chapters_table.get(num, [])
        elif ch_type == "yn":
            yn_data = chapters_yn.get(num, {})
            ch_data["answer"] = yn_data.get("answer")
            ch_data["explanation"] = yn_data.get("explanation")

        chapters[str(num)] = ch_data

    # ─── 5. 构建 signature_table (10 rows) ───────────────────────────────
    signature_table: list[dict] = []
    for i, role in enumerate(SIGNATURE_ROLES):
        name_key = f"a171-signature-{i}-name"
        date_key = f"a171-signature-{i}-date"
        signature_table.append({
            "role": role,
            "name": signature_data.get(name_key),
            "date": signature_data.get(date_key),
        })

    return {
        "chapters": chapters,
        "signature_table": signature_table,
        "cross_references": cross_references,
        "project_context": project_context,
    }
