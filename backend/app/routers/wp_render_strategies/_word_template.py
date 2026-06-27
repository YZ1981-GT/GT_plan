"""word-template 通用渲染策略 — 返回模板结构 + 已填响应.

适用所有 25 个 word-template wp_code（A8-1, A8-2, ... S34-1-1）。
解析 docx 模板提取占位符/段落/表格结构，合并 checklist_responses 当前值。

数据持久化：checklist_responses 表，item_id 前缀 `wt-{wp_code}-`。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """word-template 渲染策略：返回 template_structure + filled_responses + sign_status.

    Returns:
        dict with template_structure, filled_responses, sign_status
        None if template file not found or parse failure (fallback to OO-only mode)
    """
    from app.services.wp_docx_template_parser import get_cached_structure

    wp_id = ctx.wp_id
    wp_code = ctx.wp_code
    db = ctx.db

    # ─── 1. 解析模板文件路径 ─────────────────────────────────────────────
    file_path = ctx.template_file_path
    if not file_path:
        logger.debug("word-template 模板文件路径为空, wp_code=%s, wp_id=%s", wp_code, wp_id)
        return None

    # ─── 2. 获取缓存的 TemplateStructure ─────────────────────────────────
    try:
        structure = get_cached_structure(file_path, wp_code)
    except FileNotFoundError:
        logger.debug("word-template 模板文件不存在: %s, wp_code=%s", file_path, wp_code)
        return None
    except (ValueError, Exception) as e:  # noqa: BLE001
        logger.warning("word-template 模板解析失败 wp_code=%s: %s", wp_code, e)
        return None

    # ─── 3. 查询 checklist_responses (item_id LIKE 'wt-{wp_code}-%') ────
    filled_responses: dict[str, str] = {}
    prefix = f"wt-{wp_code}-"

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :prefix"
            ),
            {"wp_id": str(wp_id), "prefix": f"{prefix}%"},
        )
        for row in result.fetchall():
            # 从 item_id 提取 field_id: "wt-A8-1-entity_name" → "entity_name"
            field_id = row.item_id[len(prefix):]
            # conclusion 优先（短文本），remark 备选（长文本/textarea）
            value = row.conclusion or row.remark or ""
            if value:
                filled_responses[field_id] = value
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "word-template checklist_responses 查询失败 wp_id=%s: %s", wp_id, e
        )

    # ─── 4. 合并 current_value 到 placeholders ──────────────────────────
    template_structure = _serialize_structure(structure, filled_responses)

    return {
        "template_structure": template_structure,
        "filled_responses": filled_responses,
        "sign_status": None,  # placeholder for future signing integration
    }


def _serialize_structure(structure, filled_responses: dict[str, str]) -> dict:
    """将 TemplateStructure 序列化为 API 响应格式，合并 current_value."""
    from dataclasses import asdict as _asdict

    placeholders = []
    for p in structure.placeholders:
        p_dict = _asdict(p)
        p_dict["current_value"] = filled_responses.get(p.field_id, "")
        placeholders.append(p_dict)

    paragraphs = [_asdict(para) for para in structure.paragraphs]
    tables = [_asdict(tbl) for tbl in structure.tables]

    return {
        "placeholders": placeholders,
        "paragraphs": paragraphs,
        "tables": tables,
        "metadata": structure.metadata,
    }
