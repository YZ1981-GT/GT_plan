"""交付 readiness 各权威源的稳定内容摘要。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable
from uuid import UUID


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return {"$number": format(value, ".17g")}
    if isinstance(value, Decimal):
        return {"$number": format(value, "f")}
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical(item) for item in value]
    raise TypeError(f"不支持写入交付快照摘要的值类型：{type(value).__name__}")


def content_digest(rows: Iterable[Any]) -> str:
    """按内容多重集计算 SHA-256；输入顺序不同不改变摘要。"""
    encoded_rows = [
        json.dumps(
            _canonical(row),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in rows
    ]
    encoded_rows.sort()
    payload = "[" + ",".join(encoded_rows) + "]"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["content_digest"]
