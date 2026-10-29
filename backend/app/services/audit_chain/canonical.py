"""审计哈希链 — 规范化载荷与哈希计算

ADR-ALC-04: v2 可重放哈希；v1 旧行兼容校验。
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

# 创世哈希 — 链首条目的 prev_hash
GENESIS_HASH = "0" * 64


class AuditPayloadError(Exception):
    """载荷含不可规范化的值（NaN / Inf）。"""


def canonical_payload(obj: Any) -> Any:
    """递归规范化载荷，保证 JSON 往返后哈希不变。

    - float → Decimal(repr(x)) → format(_, 'f')，拒绝 NaN / Inf
    - Decimal → format(x, 'f')
    - UUID → str
    - datetime → UTC ISO 微秒
    - dict / list → 递归
    - 其余 → 直接返回
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise AuditPayloadError(f"不可规范化的浮点值: {obj}")
        return format(Decimal(repr(obj)), "f")
    if isinstance(obj, Decimal):
        return format(obj, "f")
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.astimezone(timezone.utc).isoformat(timespec="microseconds")
    if isinstance(obj, dict):
        return {k: canonical_payload(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [canonical_payload(v) for v in obj]
    return obj


def hash_v2(
    *,
    ts: str,
    user_id: str,
    action_type: str,
    object_type: str,
    resource_id: str,
    project_id: str | None,
    year: int | None,
    payload: Any,
    prev_hash: str,
) -> str:
    """计算 v2 哈希 — 字段集见 ADR-ALC-04。"""
    data = {
        "v": 2,
        "ts": ts,
        "user_id": user_id,
        "action_type": action_type,
        "object_type": object_type,
        "resource_id": resource_id,
        "project_id": project_id,
        "year": year,
        "payload": canonical_payload(payload),
        "prev_hash": prev_hash,
    }
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_v1(
    ts: str,
    user_id: str,
    action_type: str,
    object_id: str | None,
    payload_json: str,
    prev_hash: str,
) -> str:
    """计算 v1 旧格式哈希（与 helper / worker / router 三份副本一致，含 ``or ''``）。"""
    raw = f"{ts}|{user_id or ''}|{action_type}|{object_id or ''}|{payload_json}|{prev_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
