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
    skip_empty: bool = False,
) -> dict[str, str]:
    """计算 {note_section: rendered_number} 映射.

    Args:
        tree: 附注目录项，至少含 ``note_section``；可选 ``is_deleted``。
        report_scope: ``standalone`` | ``consolidated`` | ``both``。
        template_type: 用于 ``consolidated_only`` 过滤（``soe`` / ``listed``）。
        include_deleted: 是否包含已删除项（默认否）。
        skip_empty: 跳过不需要输出的章节。启用后
            ``status='not_applicable'`` 的章节（用户标记"不导出"/裁剪/不适用）
            不参与编号，后续章节序号自动连续。
            注：空但未标记不导出的章节（``has_data=False, status='draft'``）
            仍参与编号，避免编号在填写过程中不稳定。

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

    # 跳过不需要输出的章节（对齐用户裁剪意图）：
    # 仅跳过 status='not_applicable' 的章节（用户标记不导出/裁剪/不适用）。
    # ① is_deleted 已在上方过滤；③ is_empty 在 get_notes_tree 中被合成为 ②。
    # 注：has_data=False 但 status!='not_applicable' 的章节（用户未填但保留的）
    # 仍参与编号——避免编号在填写过程中不稳定。Word 导出有独立的全空跳过逻辑
    # （should_skip_empty_section 判据④），那里跳过全空是合理的。
    if skip_empty:
        working = [
            item for item in working
            if item.get("status") != "not_applicable"
        ]

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

        # 统一连续编号：不论数字还是文本形式的章节号，过滤后一律按顺序
        # 从 1 开始连续编号。
        # 🔴 修复（2026-10-10）：原 all_numeric 分支直接取 note_section 中的
        # 原始数字（如 五、1→"1"），当中间章节被 is_deleted / scope 过滤后
        # 剩余章节编号不连续（如 1、4、5、6 跳号）。改为统一连续编号。
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
