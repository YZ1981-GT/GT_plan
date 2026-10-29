"""审计哈希链 — 按链接关系校验

ADR-ALC-05: 从创世条目沿链走，识别 fork / orphan / missing_prefix / content_mismatch。
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from .canonical import GENESIS_HASH, hash_v1, hash_v2

logger = logging.getLogger(__name__)

_RESERVED_PAYLOAD_KEYS = frozenset({"_hash_v", "_resource_id", "_year"})


@dataclass
class VerifyResult:
    valid: bool
    entries_checked: int
    broken_at_entry_id: str | None = None
    message: str = ""
    problems: list[dict] = field(default_factory=list)
    legacy_verified: int = 0
    legacy_unverifiable: int = 0
    anchor: dict | None = None


def _strip_reserved(payload: dict | None) -> dict:
    if not payload:
        return {}
    return {k: v for k, v in payload.items() if k not in _RESERVED_PAYLOAD_KEYS}


def _uuid_variants(raw: str) -> set[str]:
    """返回 UUID 字符串的带连字符与无连字符变体集合。"""
    variants = {raw}
    if "-" in raw:
        variants.add(raw.replace("-", ""))
    elif len(raw) == 32:
        try:
            variants.add(str(UUID(raw)))
        except (ValueError, TypeError):
            pass
    return variants


def _try_hash_v1(entry: dict) -> bool:
    """v1 公式重算，对 object_id / user_id 试两种 UUID 写法。"""
    ts = entry.get("ts", "")
    action_type = entry.get("action_type", "")
    payload_json = entry.get("payload_json", "")
    prev_hash = entry.get("prev_hash", "")
    stored_hash = entry.get("entry_hash", "")

    for uid in _uuid_variants(entry.get("user_id", "") or ""):
        for oid in _uuid_variants(entry.get("object_id", "") or ""):
            if hash_v1(ts, uid, action_type, oid, payload_json, prev_hash) == stored_hash:
                return True
    return False


def verify_entries(
    entries: list[dict],
    *,
    fork_ack_dead_ids: set[str] | None = None,
) -> VerifyResult:
    """同步核心：按链接关系校验条目列表。"""
    if not entries:
        return VerifyResult(valid=True, entries_checked=0)

    dead_ids = fork_ack_dead_ids or set()

    hash_to_entry: dict[str, dict] = {}
    successors: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        hash_to_entry[e["entry_hash"]] = e
        successors[e["prev_hash"]].append(e)

    problems: list[dict] = []
    legacy_verified = 0
    legacy_unverifiable = 0

    genesis_entries = successors.get(GENESIS_HASH, [])
    if not genesis_entries and entries:
        problems.append({
            "type": "missing_prefix",
            "message": "链内没有创世条目（prev_hash == GENESIS_HASH）",
        })

    # BFS 沿链走
    visited: set[str] = set()
    queue: list[dict] = list(genesis_entries)

    while queue:
        entry = queue.pop(0)
        eh = entry["entry_hash"]
        if eh in visited:
            continue
        visited.add(eh)

        succs = successors.get(eh, [])
        live_succs = [s for s in succs if s["id"] not in dead_ids]
        if len(live_succs) > 1:
            problems.append({
                "type": "fork", "entry_hash": eh,
                "successor_count": len(live_succs),
                "message": f"哈希 {eh[:12]}… 有 {len(live_succs)} 个未确认后继",
            })

        payload = entry.get("payload") or {}
        if payload.get("_hash_v") == 2:
            computed = hash_v2(
                ts=entry.get("ts", ""), user_id=entry.get("user_id", ""),
                action_type=entry.get("action_type", ""),
                object_type=entry.get("object_type", ""),
                resource_id=payload.get("_resource_id", "") or "",
                project_id=payload.get("project_id") or None,
                year=payload.get("_year") or None,
                payload=_strip_reserved(payload), prev_hash=entry["prev_hash"],
            )
            if computed != eh:
                problems.append({
                    "type": "content_mismatch", "entry_id": entry["id"],
                    "entry_hash": eh, "computed_hash": computed,
                    "message": f"v2 条目 {entry['id']} 重算哈希不匹配",
                })
        else:
            if _try_hash_v1(entry):
                legacy_verified += 1
            else:
                legacy_unverifiable += 1

        for s in succs:
            if s["entry_hash"] not in visited:
                queue.append(s)

    # 孤立条目
    for e in entries:
        if e["entry_hash"] not in visited:
            ph = e["prev_hash"]
            if ph != GENESIS_HASH and ph not in hash_to_entry:
                problems.append({
                    "type": "orphan", "entry_id": e["id"], "prev_hash": ph,
                    "message": f"条目 {e['id']} 的 prev_hash 在链内找不到",
                })

    valid = len(problems) == 0
    first = problems[0] if problems else {}
    return VerifyResult(
        valid=valid, entries_checked=len(entries),
        broken_at_entry_id=first.get("entry_id"),
        message=first.get("message", ""),
        problems=problems,
        legacy_verified=legacy_verified,
        legacy_unverifiable=legacy_unverifiable,
    )


async def verify_chain(
    db: "AsyncSession",
    *,
    project_id: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> VerifyResult:
    """异步入口：查 DB 后调 verify_entries。"""
    from datetime import datetime as dt
    from sqlalchemy import asc, select
    from app.models.audit_log_models import AuditLogEntry

    try:
        from app.core.config import settings
        is_postgres = settings.DATABASE_URL.startswith("postgresql")
    except Exception:
        is_postgres = False

    stmt = select(AuditLogEntry).order_by(asc(AuditLogEntry.ts), asc(AuditLogEntry.id))

    if project_id:
        if is_postgres:
            stmt = stmt.where(AuditLogEntry.payload["project_id"].astext == project_id)
        else:
            from sqlalchemy import literal_column
            stmt = stmt.where(
                literal_column("json_extract(payload, '$.project_id')") == project_id
            )
    if from_time:
        try:
            stmt = stmt.where(AuditLogEntry.ts >= dt.fromisoformat(from_time))
        except ValueError:
            pass
    if to_time:
        try:
            stmt = stmt.where(AuditLogEntry.ts <= dt.fromisoformat(to_time))
        except ValueError:
            pass

    result = await db.execute(stmt)
    rows = result.scalars().all()

    entries_dicts: list[dict] = []
    fork_ack_dead_ids: set[str] = set()

    for row in rows:
        payload = row.payload or {}
        entries_dicts.append({
            "id": str(row.id), "entry_hash": row.entry_hash,
            "prev_hash": row.prev_hash,
            "ts": row.ts.isoformat() if row.ts else "",
            "user_id": str(row.user_id) if row.user_id else "",
            "action_type": row.action_type or "",
            "object_type": row.object_type or "",
            "object_id": str(row.object_id) if row.object_id else "",
            "payload": payload,
            "payload_json": json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str),
        })
        if row.action_type == "audit.fork_ack":
            dead_id = payload.get("dead_entry_id")
            if dead_id:
                fork_ack_dead_ids.add(str(dead_id))

    vr = verify_entries(entries_dicts, fork_ack_dead_ids=fork_ack_dead_ids)

    # 时间片锚点
    if from_time and entries_dicts:
        first = entries_dicts[0]
        if first["prev_hash"] != GENESIS_HASH:
            anchor_stmt = (
                select(AuditLogEntry)
                .where(AuditLogEntry.entry_hash == first["prev_hash"])
                .limit(1)
            )
            anchor_row = (await db.execute(anchor_stmt)).scalar_one_or_none()
            if anchor_row:
                vr.anchor = {
                    "entry_id": str(anchor_row.id),
                    "entry_hash": anchor_row.entry_hash,
                    "ts": anchor_row.ts.isoformat() if anchor_row.ts else "",
                }

    return vr
