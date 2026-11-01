"""审计日志 worker 的逐链事务与 Redis 隔离区。"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import head as head_mod

logger = logging.getLogger("audit_log_writer")

QUARANTINE_PREFIX = "audit:log:quarantine:"


def _chain_key(entry: dict[str, Any]) -> str:
    project_id = entry.get("project_id")
    return head_mod.chain_key_of(str(project_id) if project_id else None)


def _year_of(entry: dict[str, Any]) -> int | None:
    payload = entry.get("payload") or {}
    raw = entry.get("year", payload.get("_year", payload.get("year")))
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"审计日志 year 无效: {raw!r}")


async def _append_group(
    session_factory: async_sessionmaker[AsyncSession],
    key: str,
    entries: list[dict[str, Any]],
) -> int:
    """在一个独立事务中顺序写完一条链。"""
    async with session_factory() as db:
        try:
            for entry in entries:
                await head_mod.append_entry(
                    db,
                    key,
                    user_id=entry.get("user_id"),
                    session_id=entry.get("session_id"),
                    action_type=entry.get("action_type", "unknown"),
                    object_type=entry.get("object_type", "unknown"),
                    resource_id=entry.get("object_id"),
                    project_id=entry.get("project_id"),
                    year=_year_of(entry),
                    payload=entry.get("payload") or {},
                    ip=entry.get("ip"),
                    ua=entry.get("ua"),
                    trace_id=entry.get("trace_id"),
                    ts=entry.get("ts"),
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return len(entries)


async def quarantine_entries(
    redis_client: Any,
    key: str,
    entries: list[dict[str, Any]],
) -> None:
    """原样保存失败链；只有 Redis 全部写入成功才返回。"""
    queue_key = f"{QUARANTINE_PREFIX}{key}"
    encoded = [
        json.dumps(entry, ensure_ascii=False, default=str)
        for entry in entries
    ]
    if encoded:
        await redis_client.rpush(queue_key, *encoded)


async def quarantine_entries_by_chain(
    redis_client: Any,
    entries: list[dict[str, Any]],
) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        groups[_chain_key(entry)].append(entry)
    for key in sorted(groups):
        await quarantine_entries(redis_client, key, groups[key])


async def write_batch(
    entries: list[dict[str, Any]],
    *,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Any,
    mask_payload: Callable[[dict], dict] | None = None,
) -> int:
    """逐链提交；一条链失败只隔离该链，不回滚已成功的其他链。"""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for original in entries:
        entry = dict(original)
        if mask_payload is not None:
            entry["payload"] = mask_payload(dict(entry.get("payload") or {}))
        key = _chain_key(entry)
        groups[key].append(entry)

    written = 0
    for key in sorted(groups):
        group = groups[key]
        try:
            written += await _append_group(session_factory, key, group)
        except Exception as exc:
            logger.error(
                "[audit_log_writer] chain %s failed; quarantining %d entries: %s",
                key,
                len(group),
                exc,
            )
            await quarantine_entries(redis_client, key, group)
    return written


async def replay_quarantine(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Any,
) -> int:
    """每个非空隔离队列尝试一次；整链提交成功后才删除队列。"""
    replayed = 0
    async for raw_key in redis_client.scan_iter(match=f"{QUARANTINE_PREFIX}*"):
        queue_key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
        key = queue_key.removeprefix(QUARANTINE_PREFIX)
        raw_entries = await redis_client.lrange(queue_key, 0, -1)
        entries: list[dict[str, Any]] = []
        malformed = False
        for raw in raw_entries:
            text_value = raw.decode() if isinstance(raw, bytes) else str(raw)
            try:
                item = json.loads(text_value)
            except json.JSONDecodeError:
                malformed = True
                logger.error(
                    "[audit_log_writer] malformed quarantine item retained: %s",
                    queue_key,
                )
                break
            if not isinstance(item, dict):
                malformed = True
                break
            entries.append(item)
        if malformed or not entries:
            continue

        try:
            await _append_group(session_factory, key, entries)
        except Exception as exc:
            logger.warning(
                "[audit_log_writer] quarantine replay still blocked for %s: %s",
                key,
                exc,
            )
            continue

        # 成功提交后再按原始内容比较删除，避免覆盖并发新入队项。
        current = await redis_client.lrange(queue_key, 0, len(raw_entries) - 1)
        if current == raw_entries:
            await redis_client.ltrim(queue_key, len(raw_entries), -1)
            if await redis_client.llen(queue_key) == 0:
                await redis_client.delete(queue_key)
            replayed += len(entries)
        else:
            logger.error(
                "[audit_log_writer] quarantine changed during replay; retained %s",
                queue_key,
            )
    return replayed


async def quarantine_count(redis_client: Any) -> int:
    """统计所有隔离队列条目数。"""
    total = 0
    async for raw_key in redis_client.scan_iter(match=f"{QUARANTINE_PREFIX}*"):
        total += int(await redis_client.llen(raw_key))
    return total


__all__ = [
    "QUARANTINE_PREFIX",
    "quarantine_count",
    "quarantine_entries",
    "quarantine_entries_by_chain",
    "replay_quarantine",
    "write_batch",
]
