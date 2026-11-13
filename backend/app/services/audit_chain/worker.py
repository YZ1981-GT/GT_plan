"""审计日志 worker 的逐链事务、Redis 隔离区与死信列表。

- 隔离区（``audit:log:quarantine:<链键>``）：链暂时写不进去（如分叉待确认）时整组保存，约每分钟重放。
- 死信（``audit:log:deadletter:<链键>``）：条目本身不合法（与写链内核同一套校验，如 user_id 不是 UUID），
  永远写不进去。逐条分拣进死信并记原因、不丢弃，同链其余合法条目照常写入，不再整组卡在隔离区
  （spec enterprise-embedding-rerank-closure R9）。
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import head as head_mod

logger = logging.getLogger("audit_log_writer")

QUARANTINE_PREFIX = "audit:log:quarantine:"
DEAD_LETTER_PREFIX = "audit:log:deadletter:"


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


def entry_problem(entry: Any) -> str | None:
    """条目不能写入的原因（与 ``head.append_entry`` 同一组函数校验）；None = 可写。"""
    if not isinstance(entry, dict):
        return "条目不是对象"
    try:
        project_id = entry.get("project_id")
        project_text = str(project_id) if project_id not in (None, "") else None
        head_mod._uuid_or_none(entry.get("user_id"), field="user_id")
        _year_of(entry)
        head_mod._normalise_timestamp(entry.get("ts"))
        head_mod._business_payload(entry.get("payload") or {}, project_text)
    except Exception as exc:  # noqa: BLE001 - 原因原样记进死信
        return f"{type(exc).__name__}: {exc}"
    return None


def _dead_letter_record(entry: dict[str, Any], reason: str) -> str:
    record = dict(entry)
    record["_dead_letter_reason"] = reason
    record["_dead_lettered_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return json.dumps(record, ensure_ascii=False, default=str)


def _dead_letter_raw_record(raw: Any, reason: str) -> str:
    """无法 JSON 解析 / 不是对象的隔离区原始值也要进死信，不能永久卡住整个队列。"""
    value = raw.decode() if isinstance(raw, bytes) else str(raw)
    return json.dumps({
        "_dead_letter_raw": value,
        "_dead_letter_reason": reason,
        "_dead_lettered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False)


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


async def dead_letter_entries(
    redis_client: Any,
    key: str,
    bad: list[tuple[dict[str, Any], str]],
) -> None:
    """不合法条目进死信（带原因与时间，不丢弃）。"""
    if bad:
        await redis_client.rpush(
            f"{DEAD_LETTER_PREFIX}{key}", *[_dead_letter_record(e, r) for e, r in bad]
        )


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
    """逐链提交；一条链失败只隔离该链，不回滚已成功的其他链；不合法条目逐条进死信。"""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for original in entries:
        entry = dict(original)
        if mask_payload is not None:
            entry["payload"] = mask_payload(dict(entry.get("payload") or {}))
        key = _chain_key(entry)
        groups[key].append(entry)

    written = 0
    for key in sorted(groups):
        group: list[dict[str, Any]] = []
        bad: list[tuple[dict[str, Any], str]] = []
        for entry in groups[key]:
            reason = entry_problem(entry)
            if reason is None:
                group.append(entry)
            else:
                bad.append((entry, reason))
        if bad:
            logger.error(
                "[audit_log_writer] chain %s: %d invalid entries moved to dead letter: %s",
                key, len(bad), bad[0][1],
            )
            await dead_letter_entries(redis_client, key, bad)
        if not group:
            continue
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


async def _load_queue(
    redis_client: Any, queue_key: str
) -> tuple[list[Any], list[dict[str, Any] | None], list[str | None]]:
    """读出隔离队列：(原始值, 解析条目或 None, 解析失败原因)。

    解析失败的原始值同样要移到死信，不能因为一个坏字节永久挡住同一链的合法条目。
    """
    raw_entries = await redis_client.lrange(queue_key, 0, -1)
    entries: list[dict[str, Any] | None] = []
    problems: list[str | None] = []
    for raw in raw_entries:
        text_value = raw.decode() if isinstance(raw, bytes) else str(raw)
        try:
            item = json.loads(text_value)
        except json.JSONDecodeError as exc:
            entries.append(None)
            problems.append(f"JSONDecodeError: {exc.msg}")
            continue
        if not isinstance(item, dict):
            entries.append(None)
            problems.append("条目不是对象")
            continue
        entries.append(item)
        problems.append(entry_problem(item))
    return raw_entries, entries, problems


async def _move_invalid_to_dead_letter(
    redis_client: Any,
    key: str,
    queue_key: str,
    raw_entries: list[Any],
    entries: list[dict[str, Any] | None],
    problems: list[str | None],
) -> int:
    """隔离区的不合法条目在同一个 Redis 事务里移到死信（不重复、不丢失）；返回移动条数。"""
    bad = [
        (raw, entry, reason)
        for raw, entry, reason in zip(raw_entries, entries, problems)
        if reason is not None
    ]
    if not bad:
        return 0
    pipe = redis_client.pipeline(transaction=True)
    records = [
        _dead_letter_record(entry, reason) if entry is not None else _dead_letter_raw_record(raw, reason)
        for raw, entry, reason in bad
    ]
    pipe.rpush(f"{DEAD_LETTER_PREFIX}{key}", *records)
    for raw, _, _ in bad:
        pipe.lrem(queue_key, 1, raw)
    await pipe.execute()
    logger.error(
        "[audit_log_writer] chain %s: %d invalid quarantined entries moved to dead letter: %s",
        key, len(bad), bad[0][2],
    )
    return len(bad)


async def replay_quarantine(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Any,
) -> int:
    """每个非空隔离队列尝试一次；整链提交成功后才删除队列。不合法条目先移到死信。"""
    replayed = 0
    async for raw_key in redis_client.scan_iter(match=f"{QUARANTINE_PREFIX}*"):
        queue_key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
        key = queue_key.removeprefix(QUARANTINE_PREFIX)
        raw_entries, parsed, problems = await _load_queue(redis_client, queue_key)
        if not raw_entries:
            continue
        moved = await _move_invalid_to_dead_letter(redis_client, key, queue_key, raw_entries, parsed, problems)
        if moved:
            raw_entries, parsed, problems = await _load_queue(redis_client, queue_key)
        entries = [entry for entry, reason in zip(parsed, problems) if entry is not None and reason is None]
        if not entries:
            if not raw_entries:
                await redis_client.delete(queue_key)
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


async def _count_prefix(redis_client: Any, prefix: str) -> int:
    total = 0
    async for raw_key in redis_client.scan_iter(match=f"{prefix}*"):
        total += int(await redis_client.llen(raw_key))
    return total


async def quarantine_count(redis_client: Any) -> int:
    """统计所有隔离队列条目数。"""
    return await _count_prefix(redis_client, QUARANTINE_PREFIX)


async def dead_letter_count(redis_client: Any) -> int:
    """统计所有死信条目数。"""
    return await _count_prefix(redis_client, DEAD_LETTER_PREFIX)


__all__ = [
    "DEAD_LETTER_PREFIX",
    "QUARANTINE_PREFIX",
    "dead_letter_count",
    "dead_letter_entries",
    "entry_problem",
    "quarantine_count",
    "quarantine_entries",
    "quarantine_entries_by_chain",
    "replay_quarantine",
    "write_batch",
]
