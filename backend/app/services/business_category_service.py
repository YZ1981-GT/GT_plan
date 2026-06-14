"""业务分类裁剪服务

根据项目业务分类(A/B/C)判定底稿模板是否适用。
依赖 wp_account_mapping.json 中的 applicable_categories 字段。

Requirements: 4.1, 4.2, 4.3
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_MAPPING_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"
_REFERENCE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "business_category_reference.json"


@lru_cache(maxsize=1)
def _load_mapping() -> list[dict[str, Any]]:
    """加载 wp_account_mapping.json 的 mappings 列表"""
    with open(_MAPPING_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", [])


@lru_cache(maxsize=1)
def _load_reference() -> dict[str, Any]:
    """加载业务分类参考数据"""
    with open(_REFERENCE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_category_prefix(category: str) -> str:
    """提取主分类前缀：'A3' → 'A', 'B1' → 'B', 'C' → 'C'"""
    if not category:
        return "C"
    return category[0].upper()


def is_template_applicable(template: dict[str, Any], category: str) -> bool:
    """判定模板是否适用于给定业务分类。

    逻辑：
    - template.applicable_categories 存在时直接匹配主分类前缀
    - 不存在时默认适用（向后兼容）

    Args:
        template: mapping 条目（含 wp_code, applicable_categories 等）
        category: 项目业务分类（如 'A1', 'B3', 'C'）

    Returns:
        True 如果模板适用于该分类
    """
    applicable = template.get("applicable_categories")
    if not applicable:
        # 无标注 → 默认全适用
        return True

    prefix = get_category_prefix(category)
    return prefix in applicable


def get_applicable_templates(category: str) -> list[dict[str, Any]]:
    """返回指定业务分类下所有适用的模板列表"""
    mappings = _load_mapping()
    return [m for m in mappings if is_template_applicable(m, category)]


def get_template_list_with_applicability(category: str) -> list[dict[str, Any]]:
    """返回全部模板列表，每项标注 applicable 状态。

    返回：原始 mapping 条目 + 'applicable': bool + 'applicable_reason': str
    """
    mappings = _load_mapping()
    prefix = get_category_prefix(category)
    result = []
    for m in mappings:
        applicable = is_template_applicable(m, category)
        reason = ""
        if not applicable:
            cats = m.get("applicable_categories", [])
            reason = f"仅 {''.join(cats)} 类适用"
        result.append({
            **m,
            "applicable": applicable,
            "applicable_reason": reason,
        })
    return result


def get_reference_data() -> dict[str, Any]:
    """返回业务分类参考数据（前端展示用）"""
    return _load_reference()


def invalidate_cache() -> None:
    """清除缓存（测试用）"""
    _load_mapping.cache_clear()
    _load_reference.cache_clear()
