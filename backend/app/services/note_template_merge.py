"""附注模板基线 + 自定义 union 算法（Sprint 3 Task 3.3）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.3
Design: D3 模板基线 + 项目自定义 union 算法

设计要点
--------
1. **纯函数（无 IO）**：仅接收 baseline / custom 两个 list[dict]，返回合并后的
   list[dict]；不读文件、不查 DB；便于单测。
2. **冲突解决**：``section_number`` 相同 → custom 覆盖 baseline；不同 → 按
   ``sort_order`` 插入到合并集。
3. **`_custom: True` 标记**：仅 custom 独有的章节（baseline 没有同
   section_number 的）会被打 ``_custom: True``；与 baseline 同 section_number
   的 override 章节是否被打标记，取决于 custom 自身是否带；规约保留 custom
   原始字段不二次写。
4. **sort_order 缺失**：缺 sort_order 视为 ``0``。
5. **稳定排序**：两章节 sort_order 相同时保持插入顺序（baseline 在前，custom
   在后）。

Validates: Requirements R4.3 验收 36（自定义 union 不冲突）
"""

from __future__ import annotations

from typing import Any


def merge_templates(
    baseline_sections: list[dict[str, Any]] | None,
    custom_sections: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """合并基线模板 + 项目自定义模板的 sections.

    冲突规则：
    - section_number 相同 → custom 覆盖 baseline（整个 dict 替换）。
    - section_number 仅 custom 有 → 标记 ``_custom = True`` 后插入。
    - section_number 仅 baseline 有 → 直接保留。
    - 缺失 section_number 的 dict 按位忽略（防脏数据）。

    Args:
        baseline_sections: 基线模板 sections 数组（None / 空 list 视为无基线）。
        custom_sections:  项目自定义 sections 数组（None / 空 list 视为无自定义）。

    Returns:
        合并并按 sort_order 升序的 sections list。

    Examples:
        >>> merge_templates(
        ...     [{"section_number": "五、1", "section_title": "货币资金", "sort_order": 10}],
        ...     [{"section_number": "五、X1", "section_title": "递延收益", "sort_order": 5}],
        ... )
        [
            {"section_number": "五、X1", ..., "_custom": True, "sort_order": 5},
            {"section_number": "五、1", ..., "sort_order": 10},
        ]
    """
    base_list: list[dict[str, Any]] = list(baseline_sections or [])
    custom_list: list[dict[str, Any]] = list(custom_sections or [])

    # 用 dict 保序索引（dict 自 Python 3.7+ 保持插入顺序）
    baseline_map: dict[str, dict[str, Any]] = {}
    for s in base_list:
        if not isinstance(s, dict):
            continue
        sn = s.get("section_number")
        if not isinstance(sn, str) or not sn:
            continue
        baseline_map[sn] = s

    custom_map: dict[str, dict[str, Any]] = {}
    for s in custom_list:
        if not isinstance(s, dict):
            continue
        sn = s.get("section_number")
        if not isinstance(sn, str) or not sn:
            continue
        custom_map[sn] = s

    # 1. 起步：baseline 全量入合并集（保留原顺序）
    merged_map: dict[str, dict[str, Any]] = dict(baseline_map)

    # 2. custom 覆盖 / 新增（保持 custom 顺序追加新章节）
    for sn, custom_section in custom_map.items():
        if sn in baseline_map:
            # 覆盖：custom 整个 dict 替换 baseline；不强加 _custom 标记
            merged_map[sn] = custom_section
        else:
            # 新增：标记 _custom: True（不修改原对象，浅拷贝）
            tagged = dict(custom_section)
            tagged["_custom"] = True
            merged_map[sn] = tagged

    # 3. 按 sort_order 升序输出，缺失视为 0；同分按插入顺序（Python 排序稳定）
    return sorted(
        merged_map.values(),
        key=lambda s: s.get("sort_order", 0) if isinstance(s.get("sort_order", 0), (int, float)) else 0,
    )


__all__ = ["merge_templates"]
