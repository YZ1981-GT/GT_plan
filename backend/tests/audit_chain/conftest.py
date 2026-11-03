"""审计链测试 — 共享夹具

提供 build_v2_chain 辅助函数与一次性 PG 库上下文管理器（FEAT-002 用）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.services.audit_chain.canonical import GENESIS_HASH, hash_v2


def build_v2_chain(entries_data: list[dict]) -> list[dict]:
    """接受原始条目数据，计算正确的 v2 哈希链。

    每个 entry_data 须含: id, ts, user_id, action_type, object_type, payload
    可选: resource_id, project_id, year
    返回带正确 prev_hash / entry_hash / payload._hash_v 的 dict 列表。
    """
    prev = GENESIS_HASH
    result = []
    for raw in entries_data:
        eid = raw.get("id", str(uuid.uuid4()))
        ts = raw.get("ts", datetime.now(timezone.utc).isoformat(timespec="microseconds"))
        user_id = raw.get("user_id", "")
        action_type = raw.get("action_type", "test.action")
        object_type = raw.get("object_type", "test_object")
        resource_id = raw.get("resource_id", "")
        project_id = raw.get("project_id", None)
        year = raw.get("year", None)
        payload = dict(raw.get("payload", {}))

        entry_hash = hash_v2(
            ts=ts,
            user_id=user_id,
            action_type=action_type,
            object_type=object_type,
            resource_id=resource_id,
            project_id=project_id,
            year=year,
            payload=payload,
            prev_hash=prev,
        )

        # 落库载荷带保留键
        full_payload = dict(payload)
        full_payload["_hash_v"] = 2
        full_payload["_resource_id"] = resource_id
        if year is not None:
            full_payload["_year"] = year
        if project_id:
            full_payload["project_id"] = project_id

        entry = {
            "id": eid,
            "entry_hash": entry_hash,
            "prev_hash": prev,
            "ts": ts,
            "user_id": user_id,
            "action_type": action_type,
            "object_type": object_type,
            "object_id": "",
            "payload": full_payload,
            "payload_json": "",  # v2 不需要此字段做校验
            "resource_id": resource_id,
            "project_id": project_id,
            "year": year,
        }
        result.append(entry)
        prev = entry_hash

    return result
