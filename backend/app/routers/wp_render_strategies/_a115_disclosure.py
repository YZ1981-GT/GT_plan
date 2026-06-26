"""A1-15 企业会计准则财务报表列报及披露核对表 — 专属渲染策略.

component_type = "a1-15-disclosure-checklist"
解析 A1-15 DOCX 模板为结构化 35 章节 + 500 actionable 条目，
合并 checklist_responses + field_overrides(toc_applicability)。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─── 静态配置：科目章节 → 建议关联底稿编码 ──────────────────────────────────
CROSS_REFERENCE_MAP: dict[str, str] = {
    "S02": "D0",   # 货币资金
    "S03": "D1",   # 应收票据
    "S04": "D2",   # 应收账款
    "S05": "D3",   # 预付款项
    "S06": "E1",   # 存货
    "S07": "I1",   # 长期股权投资
    "S08": "G1",   # 固定资产
    "S09": "H1",   # 无形资产
    "S10": "F1",   # 应付账款
    "S11": "F2",   # 应付职工薪酬
    "S12": "K1",   # 收入
}


def format_a115_to_summary(parse_output: dict) -> str:
    """将 A1-15 解析输出格式化为可读文本摘要.

    用于 round-trip 验证：解析 → 格式化 → 验证章节标题+条目数+总计一致。

    Args:
        parse_output: _parse_a1_15 或 get_checklist_template("A1-15") 的返回值，
                      包含 title, sections, stats 等字段。

    Returns:
        格式化的文本摘要，包含标题、各章节条目数和总计。
    """
    title = parse_output.get("title", "")
    sections = parse_output.get("sections", [])
    stats = parse_output.get("stats", {})

    separator = "━" * 30
    lines: list[str] = [title, separator]

    for section in sections:
        section_id = section.get("id", "")
        section_title = section.get("title", "")
        # 统计该章节 actionable 条目数
        actionable_count = sum(
            1 for item in section.get("items", []) if item.get("type") == "actionable"
        )
        lines.append(f"{section_id}: {section_title} ({actionable_count} actionable)")

    lines.append(separator)

    total_sections = stats.get("total_sections", len(sections))
    total_actionable = stats.get("total_actionable", 0)
    total_guidance = stats.get("total_guidance", 0)
    lines.append(
        f"总计: {total_sections} 章节, {total_actionable} actionable, "
        f"{total_guidance} guidance"
    )

    return "\n".join(lines)


async def render(ctx: RenderContext) -> dict | None:
    """A1-15 披露核对表专属渲染策略.

    返回 {template, responses, cross_reference_map} 供前端
    GtA115DisclosureChecklist 消费。

    流程:
    1. 调用现有 _parse_a1_15（经 get_checklist_template 缓存）获取模板数据
    2. 从 checklist_responses 查询用户 responses（wp_id 过滤）
    3. 从 field_overrides 查询 toc_applicability（scope=a115_disclosure:{wp_id}）
    4. 组装返回结构
    """
    from app.services.checklist_docx_parser import get_checklist_template
    from app.services.field_override_service import FieldOverrideService

    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 1. 解析 DOCX 获取模板数据（全局 mtime 缓存） ───────────────────────
    template: dict | None = None
    try:
        template = await get_checklist_template("A1-15")
    except FileNotFoundError:
        logger.warning("A1-15 模板文件未找到")
    except Exception as e:  # noqa: BLE001
        logger.warning("A1-15 模板解析失败: %s", e)

    if template is None:
        return None

    # ─── 2. 从 checklist_responses 查询用户填写数据 ──────────────────────────
    items_responses: dict[str, dict] = {}
    toc_from_responses: dict[str, bool] = {}

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark, wp_ref "
                "FROM checklist_responses WHERE wp_id = :wp_id"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            if item_id.startswith("TOC-"):
                # 章节适用性: TOC-S01 → S01, conclusion Y=适用 N=不适用
                section_id = item_id[4:]  # "TOC-S01" → "S01"
                toc_from_responses[section_id] = (row.conclusion == "Y")
            else:
                items_responses[item_id] = {
                    "conclusion": row.conclusion,
                    "remark": row.remark or "",
                    "wp_ref": row.wp_ref or "",
                }
    except Exception as e:  # noqa: BLE001
        logger.warning("A1-15 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 3. 从 field_overrides 查询 toc_applicability 补充 ──────────────────
    toc_applicability: dict[str, bool] = dict(toc_from_responses)

    try:
        svc = FieldOverrideService(db)
        scope = f"a115_disclosure:{wp_id}"
        overrides = await svc.get_batch(
            project_id=ctx.project_id,
            year=ctx.year or 0,
            scope=scope,
        )

        # field_overrides 中 toc_applicability 以 "toc-{section_id}" 为 item_key
        for item_key, fields in overrides.items():
            if item_key.startswith("toc-"):
                section_id = item_key[4:].upper()  # "toc-s01" → "S01"
                val = fields.get("applicable")
                if val is not None:
                    toc_applicability[section_id] = bool(val)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "A1-15 field_overrides 查询失败 wp_id=%s: %s", wp_id, e,
        )

    # ─── 4. 组装返回结构 ────────────────────────────────────────────────────
    return {
        "template": template,
        "responses": {
            "items": items_responses,
            "toc_applicability": toc_applicability,
        },
        "cross_reference_map": CROSS_REFERENCE_MAP,
    }
