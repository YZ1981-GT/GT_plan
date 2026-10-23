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


def _excluded_entry(code: str, prefix: str) -> str | None:
    """参考标准里该主分类排除的清单中覆盖 ``code`` 的那一项（按族：``A17-5`` 覆盖 ``A17-5-1``）；不排除 ⇒ None。"""
    category = (_load_reference().get("categories") or {}).get(prefix) or {}
    for entry in category.get("excluded_templates") or ():
        if code == entry or code.startswith(f"{entry}-"):
            return entry
    return None


def is_template_applicable(template: dict[str, Any], category: str) -> bool:
    """判定模板是否适用于给定业务分类。

    两个来源都生效：映射条目的 ``applicable_categories`` 标注（A17 族），以及业务分类参考标准
    ``business_category_reference.json`` 里该主分类的 ``excluded_templates``（C 类排除 A 类专属底稿，
    B 类排除专委会资料 A26）。原先只看标注、无标注默认全适用 ⇒ C 类项目下 A18 / A26 / A27 / A28 /
    A1-12 / A1-16 仍判适用。

    Args:
        template: mapping 条目（含 wp_code, applicable_categories 等）
        category: 项目业务分类（如 'A1', 'B3', 'C'）
    """
    prefix = get_category_prefix(category)
    applicable = template.get("applicable_categories")
    if applicable and prefix not in applicable:
        return False
    return _excluded_entry(str(template.get("wp_code") or ""), prefix) is None


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
            cats = m.get("applicable_categories") or []
            if cats and prefix not in cats:
                reason = f"仅 {''.join(cats)} 类适用"
            else:
                entry = _excluded_entry(str(m.get("wp_code") or ""), prefix)
                reason = f"{prefix} 类不适用（业务分类参考标准排除 {entry}）"
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
