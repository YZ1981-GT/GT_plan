"""A27-1 IT审计总结备忘录 — 专属渲染策略.

component_type = "a27-1-it-audit-memo"
备忘录抬头(4字段) + IT团队表 + 7章节卡片(含三选一radio+条件展开+GtIndexChip跳转)。
跨引用联动: B22A-4-3 / C22 / C21-1 / B23-15。
数据持久化在 checklist_responses 表，item_id 前缀 `a271-`。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 固定目的段文本
PURPOSE_TEXT = (
    "本备忘录旨在总结本次审计中对被审计单位信息技术环境的了解、"
    "IT一般控制和信息处理控制的测试结果，以及对识别出的IT控制缺陷的评估。"
)

# 7 章节元数据
CHAPTERS_META = [
    {"number": 1, "title": "了解信息系统环境", "cross_ref": "B22A-4-3"},
    {"number": 2, "title": "IT风险和一般控制", "cross_ref": "C22"},
    {"number": 3, "title": "IT一般控制结论", "cross_ref": None},
    {"number": 4, "title": "IT一般控制缺陷", "cross_ref": "C21-1"},
    {"number": 5, "title": "信息处理控制", "cross_ref": "B23-15"},
    {"number": 6, "title": "信息处理控制结论", "cross_ref": None},
    {"number": 7, "title": "缺陷评估", "cross_ref": None},
]

# 跨引用 wp_code 列表
CROSS_REF_WP_CODES = ["B22A-4-3", "C22", "C21-1", "B23-15"]


async def _load_it_cross_references(project_id, db) -> dict:
    """查找 B22A-4-3, C22, C21-1, B23-15 底稿的 wp_id.

    通过 wp_index JOIN working_papers 定位同项目下的目标底稿。
    返回 dict: {b22a_4_3_wp_id, c22_wp_id, c21_1_wp_id, b23_15_wp_id}，
    缺失时对应值为 None。
    """
    cross_refs: dict[str, str | None] = {
        "b22a_4_3_wp_id": None,
        "c22_wp_id": None,
        "c21_1_wp_id": None,
        "b23_15_wp_id": None,
    }

    key_map = {
        "B22A-4-3": "b22a_4_3_wp_id",
        "C22": "c22_wp_id",
        "C21-1": "c21_1_wp_id",
        "B23-15": "b23_15_wp_id",
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
        logger.warning("A27-1 跨引用查询失败 project_id=%s: %s", project_id, e)

    return cross_refs


async def render(ctx: RenderContext) -> dict | None:
    """A27-1 IT审计总结备忘录渲染策略.

    返回 {meta_info, header, purpose_text, it_team_table, chapters(7),
           cross_references(4), project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db
    project_id = ctx.project_id

    # ─── 1. 加载 checklist_responses (item_id LIKE 'a271-%') ─────────────
    header: dict = {"date": None, "to": None, "from_user": None, "subject": None}
    it_team_table: list[dict] = []
    chapters_data: dict[int, dict] = {}

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a271-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            _parse_row(row.item_id, row, header, it_team_table, chapters_data)
    except Exception as e:  # noqa: BLE001
        logger.warning("A27-1 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 2. 加载项目上下文 ───────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_period": "",
        "partner": None,
        "current_user": None,
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
        logger.warning("A27-1 project context 查询失败: %s", e)

    # ─── 3. 加载跨引用 wp_ids ────────────────────────────────────────────
    cross_references = await _load_it_cross_references(project_id, db)

    # ─── 4. 构建 chapters 数组 ───────────────────────────────────────────
    chapters: list[dict] = []
    for meta in CHAPTERS_META:
        num = meta["number"]
        ch_data = chapters_data.get(num, {})
        chapters.append({
            "number": num,
            "title": meta["title"],
            "content": ch_data.get("content"),
            "conclusion": ch_data.get("conclusion"),
            "deficiency": ch_data.get("deficiency"),
            "cross_ref": meta["cross_ref"],
        })

    # ─── 5. 构建 meta_info ───────────────────────────────────────────────
    meta_info = {
        "client_name": project_context["client_name"],
        "audit_period": project_context["audit_period"],
        "index_no": "A27-1",
    }

    # ─── 6. 自动填充 header 默认值 ──────────────────────────────────────
    if not header["subject"]:
        header["subject"] = "IT审计总结"

    return {
        "meta_info": meta_info,
        "header": header,
        "purpose_text": PURPOSE_TEXT,
        "it_team_table": it_team_table,
        "chapters": chapters,
        "cross_references": cross_references,
        "project_context": project_context,
    }


def _parse_row(
    item_id: str,
    row,
    header: dict,
    it_team_table: list[dict],
    chapters_data: dict[int, dict],
) -> None:
    """解析单条 checklist_response 行并填入对应结构."""
    # Header fields: a271-header-{date|to|from|subject}
    if item_id.startswith("a271-header-"):
        field = item_id.removeprefix("a271-header-")
        if field in ("date", "to", "from", "subject"):
            key = "from_user" if field == "from" else field
            header[key] = row.conclusion or row.remark or None

    # Team: a271-team (remark = JSON array)
    elif item_id == "a271-team":
        if row.remark:
            try:
                data = json.loads(row.remark)
                if isinstance(data, list):
                    it_team_table.clear()
                    for i, item in enumerate(data):
                        if isinstance(item, dict):
                            it_team_table.append({
                                "index": i + 1,
                                "name": item.get("name"),
                                "title": item.get("title"),
                            })
            except (json.JSONDecodeError, TypeError):
                logger.warning("A27-1 team JSON 解析失败 item_id=%s", item_id)

    # Chapters: a271-ch{N}-{content|conclusion|deficiency}
    elif item_id.startswith("a271-ch"):
        try:
            # Extract chapter number and field: "a271-ch1-content" → 1, "content"
            rest = item_id.removeprefix("a271-ch")
            dash_idx = rest.index("-")
            ch_num = int(rest[:dash_idx])
            field = rest[dash_idx + 1:]

            if ch_num < 1 or ch_num > 7:
                return
            if field not in ("content", "conclusion", "deficiency"):
                return

            if ch_num not in chapters_data:
                chapters_data[ch_num] = {}
            chapters_data[ch_num][field] = row.conclusion or row.remark or None
        except (ValueError, IndexError):
            logger.warning("A27-1 chapter 解析失败 item_id=%s", item_id)
