"""附注 ``disclosure_notes.template_lineage`` 统一读写（dict 约定）。

全平台写入方都按 **dict** 读写，且对非 dict 一律当空：
- 程序裁剪 ``procedure_trim_not_applicable`` / 自动裁剪 ``deletion_reason``；
- 国企↔上市转换 ``archived_sections`` / ``conversions`` / ``legacy_*``（快照只存 dict）；
- 附注内容模板引用 ``content_templates``。

集团基线曾单独写 **list** ⇒ 被上述任一方后写时静默抹掉（自动裁剪 ``dict(list)`` 直接
ValueError），AC-11.2「两类 lineage 可共存」只在一个方向成立。现收进 ``group_baselines``
键；历史 list 形态只读兼容（升级为 dict 时原样保留条目）。真库 1029 行全 NULL，无需迁移。

所有函数返回**新对象**：JSONB 未声明 MutableDict，原地改写不标脏、不落库（R-06）。
"""

from __future__ import annotations

import copy
from typing import Any

__all__ = [
    "CONTENT_TEMPLATES_KEY",
    "GROUP_BASELINES_KEY",
    "append_lineage_entry",
    "group_baseline_entries",
    "lineage_as_dict",
]

GROUP_BASELINES_KEY = "group_baselines"
CONTENT_TEMPLATES_KEY = "content_templates"


def lineage_as_dict(existing: Any) -> dict[str, Any]:
    """深拷贝为 dict；历史集团基线 list 升级为 ``{group_baselines: [...]}``，其余非 dict 当空。"""
    if isinstance(existing, dict):
        return copy.deepcopy(existing)
    if isinstance(existing, list):
        return {GROUP_BASELINES_KEY: copy.deepcopy(existing)}
    return {}


def append_lineage_entry(existing: Any, key: str, entry: dict[str, Any]) -> dict[str, Any]:
    """在 ``key`` 列表末尾追加 ``entry``，保留其余全部键；不修改入参。"""
    base = lineage_as_dict(existing)
    history = base.get(key)
    base[key] = [*(history if isinstance(history, list) else []), dict(entry)]
    return base


def group_baseline_entries(lineage: Any) -> list[dict[str, Any]]:
    """集团基线条目（兼容历史 list 形态）。"""
    if isinstance(lineage, dict):
        items = lineage.get(GROUP_BASELINES_KEY)
    else:
        items = lineage
    if not isinstance(items, list):
        return []
    return [e for e in items if isinstance(e, dict)]
