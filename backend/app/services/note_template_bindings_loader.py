"""note_template_bindings.json 模块级缓存加载器.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.3
Design: D2 模板与绑定分离 — binding json 由 disclosure_engine 按
        section_number 索引消费

设计要点
--------
1. **零副作用 import**：模块加载不读文件；首次调用 ``get_binding_for_section``
   才 lazy-load。文件不存在或解析失败 → 缓存空 dict（不抛异常 — 调用方拿
   None 即走 legacy 兼容路径）。
2. **单进程内缓存**：解析后按 ``section_number`` 写入字典缓存；后续命中
   O(1)。
3. **可重置**：``reload()`` 清缓存触发下次重读（专给测试 / 热加载用）。
4. **section_number 的 dict 顺序**：随 json.load 自然有序；调用方按
   key 直接取，不依赖顺序。

API
---
- ``get_binding_for_section(section_number) -> dict | None``
- ``get_binding_for_table(section_number, table_index) -> dict | None``
- ``is_loaded() -> bool``
- ``reload() -> None``
- ``BINDINGS_PATH`` 模块级常量（相对仓库根 ``backend/data/...``）

Validates: Requirements R1.1 验收标准 1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

# `backend/app/services/note_template_bindings_loader.py`
#  ↑ parents[0] = services / parents[1] = app / parents[2] = backend
BINDINGS_PATH: Path = (
    Path(__file__).resolve().parents[2] / "data" / "note_template_bindings.json"
)


# ---------------------------------------------------------------------------
# 模块级缓存（单进程内单例）
# ---------------------------------------------------------------------------

# Sentinel：未加载（区别 None / 空 dict 加载失败）
_NOT_LOADED: Any = object()
_cached: Any = _NOT_LOADED


def _load() -> dict[str, Any]:
    """从 disk 读 json，按 section_number 索引；失败返回空 dict（不抛异常）.

    返回 dict 形如：
        { "四、长期股权投资": {wp_code, tables: [...]}, ... }
    """
    if not BINDINGS_PATH.exists():
        logger.info(
            "note_template_bindings.json not found at %s; "
            "binding-driven path disabled (legacy fallback active)",
            BINDINGS_PATH,
        )
        return {}

    try:
        payload = json.loads(BINDINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as err:
        logger.warning(
            "failed to parse note_template_bindings.json (%s); "
            "binding-driven path disabled",
            err,
        )
        return {}

    bindings = payload.get("bindings")
    if not isinstance(bindings, dict):
        logger.warning(
            "note_template_bindings.json 'bindings' field is not dict "
            "(got %s); binding-driven path disabled",
            type(bindings).__name__,
        )
        return {}

    # 校验 value 是 dict（防止脏数据导致后续 .get 报错）
    cleaned: dict[str, Any] = {}
    for sec_num, sec_binding in bindings.items():
        if isinstance(sec_num, str) and isinstance(sec_binding, dict):
            cleaned[sec_num] = sec_binding

    return cleaned


def _ensure_loaded() -> dict[str, Any]:
    """触发 lazy-load；返回当前缓存（永远 dict）."""
    global _cached
    if _cached is _NOT_LOADED:
        _cached = _load()
    return _cached  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def is_loaded() -> bool:
    """是否已 lazy-load（仅判断「load 行为发生过」，不区分 0 章节命中）."""
    return _cached is not _NOT_LOADED


def reload() -> None:
    """清缓存；下次 get_binding_for_section 会重新 _load.

    专为单测 / 热加载 / 文件变更后强制刷新。
    """
    global _cached
    _cached = _NOT_LOADED


def get_binding_for_section(section_number: str | None) -> dict | None:
    """按 section_number 查 binding；缺失 / 类型错 / 文件不存在 → None.

    Args:
        section_number: 章节号（与 note_template_*.json 的 section_number 一致），
            形如 "四、长期股权投资" / "五、1 货币资金"。

    Returns:
        section binding dict（含 ``tables: list``）或 None。
    """
    if not isinstance(section_number, str) or not section_number:
        return None
    cache = _ensure_loaded()
    sec = cache.get(section_number)
    if isinstance(sec, dict):
        return sec
    return None


def get_binding_for_table(
    section_number: str | None, table_index: int = 0
) -> dict | None:
    """按 (section_number, table_index) 查表级 binding；缺失 → None.

    table_index 越界（≥ len(tables) 或 < 0）也返回 None。
    """
    sec = get_binding_for_section(section_number)
    if not sec:
        return None
    tables = sec.get("tables")
    if not isinstance(tables, list):
        return None
    if not isinstance(table_index, int):
        return None
    if table_index < 0 or table_index >= len(tables):
        return None
    tbl = tables[table_index]
    if isinstance(tbl, dict):
        return tbl
    return None


__all__ = [
    "BINDINGS_PATH",
    "get_binding_for_section",
    "get_binding_for_table",
    "is_loaded",
    "reload",
]
