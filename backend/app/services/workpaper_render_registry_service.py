"""底稿类型注册表加载服务

单例加载 backend/data/workpaper_render_registry.json，
提供 lookup / list_by_type / get_all 查询。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "workpaper_render_registry.json"


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
    """懒加载注册表 JSON（进程内单例）"""
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_entries() -> dict[str, Any]:
    """返回所有 entries {wp_code: entry_dict}"""
    return _load_registry()["entries"]


def get_render_types() -> list[str]:
    """返回合法 render_type 列表"""
    return _load_registry()["render_types"]


def lookup(wp_code: str) -> dict[str, Any] | None:
    """按 wp_code 查找注册表条目"""
    return get_all_entries().get(wp_code)


def list_by_render_type(render_type: str) -> dict[str, Any]:
    """按 render_type 过滤返回 {wp_code: entry}"""
    return {
        code: entry
        for code, entry in get_all_entries().items()
        if entry.get("render_type") == render_type
    }


def list_by_module(module: str) -> dict[str, Any]:
    """按 module 过滤返回 {wp_code: entry}"""
    return {
        code: entry
        for code, entry in get_all_entries().items()
        if entry.get("module") == module
    }


def invalidate_cache() -> None:
    """清除缓存（测试/热更新用）"""
    _load_registry.cache_clear()
