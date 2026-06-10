"""附注显示编号 — 与 NoteSectionNumberingService（政策树）分工.

用于 ``{{seq:八}}`` 填充与 ``get_section_numbers`` API：
按 ``note_section`` 前缀（「八」）分组，组内连续阿拉伯编号；
组内仅 1 条目不编号（与现有端点行为一致）。

见 design.md §8；勿与 ``note_section_numbering_service.py`` 混用。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from app.services.note_section_catalog import (
    filter_tree_by_report_scope,
    normalize_report_scope,
)


def compute_section_numbers(
    tree: list[dict[str, Any]],
    *,
    report_scope: str | None = "both",
    template_type: str | None = None,
    include_deleted: bool = False,
) -> dict[str, str]:
    """计算 {note_section: rendered_number} 映射.

    Args:
        tree: 附注目录项，至少含 ``note_section``；可选 ``is_deleted``。
        report_scope: ``standalone`` | ``consolidated`` | ``both``。
        template_type: 用于 ``consolidated_only`` 过滤（``soe`` / ``listed``）。
        include_deleted: 是否包含已删除项（默认否）。

    Returns:
        如 ``{"八、1": "1", "八、2": "2"}``；组内仅 1 条时该组无条目。
    """
    rs = (report_scope or "both").strip().lower()
    if rs not in ("standalone", "consolidated", "both"):
        rs = "both"

    working = list(tree)
    if not include_deleted:
        working = [item for item in working if not item.get("is_deleted")]

    if rs != "both" and template_type:
        working = filter_tree_by_report_scope(working, template_type, rs)
    elif rs != "both":
        working = filter_tree_by_report_scope(working, "soe", rs)

    groups: dict[str, list[dict[str, Any]]] = OrderedDict()
    for item in working:
        section = (item.get("note_section") or "").strip()
        if not section:
            continue
        sep_idx = section.find("、")
        prefix = section[:sep_idx] if sep_idx > 0 else section
        groups.setdefault(prefix, []).append(item)

    result: dict[str, str] = {}
    for _prefix, items in groups.items():
        # 过滤：仅含"、"分隔符的子节参与编号计数
        # 纯前缀（如"一"、"二"、"三"）是章节标题头，不参与编号
        numbered_items = [it for it in items if "、" in (it.get("note_section") or "")]
        if len(numbered_items) <= 1:
            continue
        for idx, item in enumerate(numbered_items, 1):
            section = (item.get("note_section") or "").strip()
            if section:
                result[section] = str(idx)
    return result


def compute_section_numbers_for_project(
    tree: list[dict[str, Any]],
    *,
    template_type: str | None,
    report_scope: str | None,
) -> dict[str, str]:
    """便捷入口：用项目 template_type + report_scope 计算编号."""
    return compute_section_numbers(
        tree,
        report_scope=report_scope or "both",
        template_type=template_type,
    )
