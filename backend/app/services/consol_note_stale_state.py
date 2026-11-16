"""合并附注 ``consol_note_data`` 的待更新状态单一写入口。

合并附注的 stale 元数据与用户内容分列存储。调用方负责事务生命周期；本模块
只修改传入 ORM 对象或返回批量 UPDATE 所需的值，不自行 commit / rollback。
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class ConsolNoteStaleSource(StrEnum):
    """合并附注待更新原因的稳定编码。"""

    CONSOL_PUSH = "consol_push"
    FORMULA_VALUE_CHANGED = "formula_value_changed"
    STANDALONE_NOTE_SAVED = "standalone_note_saved"
    FORMULA_SETTINGS = "formula_settings"
    NODE_CREATED = "node_created"
    LEGACY = "legacy"


LABELS: dict[ConsolNoteStaleSource, str] = {
    ConsolNoteStaleSource.CONSOL_PUSH: "合并推送后待按最新合并数更新",
    ConsolNoteStaleSource.FORMULA_VALUE_CHANGED: "合并数已变化，拉数数据待重新汇总",
    ConsolNoteStaleSource.STANDALONE_NOTE_SAVED: "子企业单体附注已修改",
    ConsolNoteStaleSource.FORMULA_SETTINGS: "公式设置已变化",
    ConsolNoteStaleSource.NODE_CREATED: "新建节点，尚未计算",
    ConsolNoteStaleSource.LEGACY: "历史标记，未记录原因",
}
_UNKNOWN_LABEL = "历史标记"


def _source_value(source: str | ConsolNoteStaleSource) -> str:
    try:
        normalized = source if isinstance(source, ConsolNoteStaleSource) else ConsolNoteStaleSource(str(source))
    except ValueError as exc:
        raise ValueError(f"不支持的合并附注 stale 原因：{source}") from exc
    return normalized.value


def _utc_now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def label_of(source: str | ConsolNoteStaleSource | None) -> str:
    """把存储编码转为中文；历史空值与未知编码安全降级为「历史标记」。"""
    if source is None or not str(source).strip():
        return _UNKNOWN_LABEL
    try:
        normalized = ConsolNoteStaleSource(str(source))
    except ValueError:
        return _UNKNOWN_LABEL
    return LABELS[normalized]


def stale_values(
    source: str | ConsolNoteStaleSource,
    now: datetime | None = None,
) -> dict[str, Any]:
    """返回批量置位 ``ConsolNoteData`` 所需的字段值。"""
    return {
        "is_stale": True,
        "stale_reason": _source_value(source),
        "stale_at": _utc_now(now),
    }


def clear_values() -> dict[str, Any]:
    """返回批量清除 stale 及其元数据所需的字段值。"""
    return {"is_stale": False, "stale_reason": None, "stale_at": None}


def mark_stale(
    record: Any,
    source: str | ConsolNoteStaleSource,
    *,
    now: datetime | None = None,
) -> Any:
    """在当前事务内把一条合并附注行置为待更新。"""
    for key, value in stale_values(source, now).items():
        setattr(record, key, value)
    return record


def clear_stale(record: Any) -> Any:
    """在当前事务内清除一条合并附注行的待更新状态及原因时间。"""
    for key, value in clear_values().items():
        setattr(record, key, value)
    return record


def inherit_values(source_record: Any) -> dict[str, Any]:
    """复制节点/兼容行时完整继承 stale 状态，不把原因或时间静默丢掉。"""
    is_stale = bool(getattr(source_record, "is_stale", False))
    return {
        "is_stale": is_stale,
        "stale_reason": getattr(source_record, "stale_reason", None) if is_stale else None,
        "stale_at": getattr(source_record, "stale_at", None) if is_stale else None,
    }


__all__ = [
    "ConsolNoteStaleSource",
    "LABELS",
    "clear_stale",
    "clear_values",
    "inherit_values",
    "label_of",
    "mark_stale",
    "stale_values",
]
