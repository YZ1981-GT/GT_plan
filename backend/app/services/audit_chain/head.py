"""审计哈希链的唯一写入内核。

同一事务内执行稳定链锁、链尾惰性初始化、绕过检测、v2 哈希写入和
链尾推进。任何读取或校验错误都向上抛出，绝不退回创世哈希继续写。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log_models import AuditChainHead, AuditLogEntry

from .canonical import GENESIS_HASH, canonical_payload, hash_v2


class AuditChainError(RuntimeError):
    """审计链无法安全续写。"""


class AuditChainForked(AuditChainError):
    """链有零个或多个未确认链尾。"""


class AuditChainBypassed(AuditChainError):
    """链尾表之外已有写入，当前链尾已失真。"""


def chain_key_of(project_id: str | None) -> str:
    """返回按项目隔离的稳定链键。"""
    return f"project:{project_id}" if project_id else "__global__"


def _dialect_name(db: AsyncSession) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else ""

def _chain_filter(db: AsyncSession, key: str):
    """构造链键对应的项目过滤条件。"""
    if key == "__global__":
        if _dialect_name(db) == "postgresql":
            return func.coalesce(AuditLogEntry.payload["project_id"].astext, "") == ""
        return func.coalesce(
            func.json_extract(AuditLogEntry.payload, "$.project_id"), ""
        ) == ""

    if not key.startswith("project:") or not key.removeprefix("project:"):
        raise ValueError(f"无效审计链键: {key!r}")
    project_id = key.removeprefix("project:")
    if _dialect_name(db) == "postgresql":
        return AuditLogEntry.payload["project_id"].astext == project_id
    return func.json_extract(AuditLogEntry.payload, "$.project_id") == project_id


async def lock_chain(db: AsyncSession, key: str) -> None:
    """取得跨进程稳定的 PG 事务级链锁；SQLite 测试不加锁。"""
    if _dialect_name(db) == "postgresql":
        await db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended('audit_chain:' || :key, 0))"
            ),
            {"key": key},
        )


async def _dead_entry_ids(db: AsyncSession, key: str) -> set[uuid.UUID]:
    rows = (
        await db.execute(
            select(AuditLogEntry.payload).where(
                _chain_filter(db, key),
                AuditLogEntry.action_type == "audit.fork_ack",
            )
        )
    ).scalars().all()
    result: set[uuid.UUID] = set()
    for payload in rows:
        raw = (payload or {}).get("dead_entry_id")
        if raw:
            try:
                result.add(uuid.UUID(str(raw)))
            except (TypeError, ValueError):
                continue
    return result

async def read_head(db: AsyncSession, key: str) -> AuditChainHead | None:
    """读取链尾；无链尾行时按链接关系惰性初始化。

    调用方必须先取得 ``lock_chain``。空链返回 ``None``；已有条目的链必须
    恰有一个未确认链尾，否则 fail-closed。
    """
    head = await db.get(AuditChainHead, key)
    if head is not None:
        return head

    rows = (
        await db.execute(
            select(
                AuditLogEntry.id,
                AuditLogEntry.entry_hash,
                AuditLogEntry.prev_hash,
            ).where(_chain_filter(db, key))
        )
    ).all()
    if not rows:
        return None

    hashes = {row.entry_hash for row in rows}
    referenced = {row.prev_hash for row in rows if row.prev_hash in hashes}
    dead_ids = await _dead_entry_ids(db, key)
    tails = [
        row for row in rows
        if row.entry_hash not in referenced and row.id not in dead_ids
    ]
    if len(tails) != 1:
        raise AuditChainForked(
            f"链 {key} 有 {len(tails)} 个未确认链尾，拒绝继续写入"
        )

    tail = tails[0]
    head = AuditChainHead(
        chain_key=key,
        tail_entry_id=tail.id,
        tail_hash=tail.entry_hash,
        entry_count=len(rows),
    )
    db.add(head)
    await db.flush()
    return head


def _normalise_timestamp(value: datetime | str | None) -> tuple[datetime, str]:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed, parsed.isoformat(timespec="microseconds")

def _uuid_or_none(value: uuid.UUID | str | None, *, field: str) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是 UUID: {value!r}") from exc


def _resource_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    try:
        return _uuid_or_none(value, field="resource_id")
    except ValueError:
        return None


def _business_payload(payload: dict[str, Any] | None, project_id: str | None) -> dict:
    raw = dict(payload or {})
    for reserved in ("_hash_v", "_resource_id", "_year"):
        raw.pop(reserved, None)

    existing_project = raw.get("project_id")
    if project_id:
        if existing_project not in (None, "", project_id):
            raise ValueError("payload.project_id 与审计链 project_id 不一致")
        raw["project_id"] = project_id
    elif existing_project not in (None, ""):
        raise ValueError("全局审计链 payload 不得携带 project_id")
    else:
        raw.pop("project_id", None)

    normalised = canonical_payload(raw)
    if not isinstance(normalised, dict):
        raise TypeError("审计日志 payload 必须是对象")
    return normalised


async def _assert_head_not_bypassed(
    db: AsyncSession, key: str, head: AuditChainHead
) -> None:
    tail_exists = (
        await db.execute(
            select(AuditLogEntry.id).where(
                AuditLogEntry.id == head.tail_entry_id,
                AuditLogEntry.entry_hash == head.tail_hash,
                _chain_filter(db, key),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if tail_exists is None:
        raise AuditChainBypassed(f"链 {key} 的链尾记录不存在或不属于该链")

    successor = (
        await db.execute(
            select(AuditLogEntry.id).where(
                AuditLogEntry.prev_hash == head.tail_hash
            ).limit(1)
        )
    ).scalar_one_or_none()
    if successor is not None:
        raise AuditChainBypassed(
            f"链 {key} 的链尾 {head.tail_hash[:12]}… 已有未登记后继"
        )

async def append_entry(
    db: AsyncSession,
    key: str,
    *,
    action_type: str,
    object_type: str,
    user_id: uuid.UUID | str | None = None,
    session_id: str | None = None,
    resource_id: uuid.UUID | str | None = None,
    project_id: uuid.UUID | str | None = None,
    year: int | None = None,
    payload: dict[str, Any] | None = None,
    ip: str | None = None,
    ua: str | None = None,
    trace_id: str | None = None,
    ts: datetime | str | None = None,
) -> AuditLogEntry:
    """在当前事务中安全追加一条 v2 审计日志并推进链尾。"""
    project_text = str(project_id) if project_id not in (None, "") else None
    expected_key = chain_key_of(project_text)
    if key != expected_key:
        raise ValueError(f"链键 {key!r} 与 project_id 不一致，应为 {expected_key!r}")

    await lock_chain(db, key)
    head = await read_head(db, key)
    if head is not None:
        await _assert_head_not_bypassed(db, key, head)
        prev_hash = head.tail_hash
        previous_count = head.entry_count
    else:
        prev_hash = GENESIS_HASH
        previous_count = 0

    business_payload = _business_payload(payload, project_text)
    stored_payload = dict(business_payload)
    stored_payload["_hash_v"] = 2
    stored_payload["_resource_id"] = str(resource_id or "")
    if year is not None:
        stored_payload["_year"] = int(year)

    when, ts_text = _normalise_timestamp(ts)
    user_uuid = _uuid_or_none(user_id, field="user_id")
    user_text = str(user_uuid) if user_uuid else ""
    resource_text = str(resource_id or "")
    entry_hash = hash_v2(
        ts=ts_text,
        user_id=user_text,
        action_type=action_type,
        object_type=object_type,
        resource_id=resource_text,
        project_id=project_text,
        year=int(year) if year is not None else None,
        payload=business_payload,
        prev_hash=prev_hash,
    )

    entry = AuditLogEntry(
        id=uuid.uuid4(),
        ts=when,
        user_id=user_uuid,
        session_id=session_id,
        action_type=action_type,
        object_type=object_type,
        object_id=_resource_uuid(resource_id),
        payload=stored_payload,
        ip=ip,
        ua=ua,
        trace_id=trace_id,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    db.add(entry)

    if head is None:
        head = AuditChainHead(
            chain_key=key,
            tail_entry_id=entry.id,
            tail_hash=entry_hash,
            entry_count=1,
        )
        db.add(head)
    else:
        head.tail_entry_id = entry.id
        head.tail_hash = entry_hash
        head.entry_count = previous_count + 1
        head.updated_at = when

    await db.flush()
    return entry


async def append_entry_batch(
    db: AsyncSession, entries: Iterable[dict[str, Any]]
) -> list[uuid.UUID]:
    """按链键升序追加多条记录，保证多链取锁顺序稳定。"""
    ordered = sorted((dict(item) for item in entries), key=lambda item: item["chain_key"])
    result: list[uuid.UUID] = []
    for item in ordered:
        key = item.pop("chain_key")
        entry = await append_entry(db, key, **item)
        result.append(entry.id)
    return result


__all__ = [
    "AuditChainError",
    "AuditChainForked",
    "AuditChainBypassed",
    "append_entry",
    "append_entry_batch",
    "chain_key_of",
    "lock_chain",
    "read_head",
]
