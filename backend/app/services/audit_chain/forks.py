"""审计哈希链 — 分叉扫描与确认

ADR-ALC-03: 分叉确认先于 fail-closed。
- scan_forks: 只读扫描，识别 prev_hash 有多个后继的分叉点
- append_fork_ack: 在链锁内验证后写入确认条目
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log_models import AuditLogEntry

from .canonical import GENESIS_HASH, hash_v1
from .head import chain_key_of, lock_chain


async def _unconfirmed_tails(db: AsyncSession, chain_key: str) -> set[uuid.UUID]:
    """该链未确认的链尾条目 ID 集合。

    链尾 = 自己的 entry_hash 不在任何其他条目的 prev_hash 里。
    减去已被 fork_ack 点名为 dead 的条目。
    """
    ALE = AuditLogEntry

    # 构建链过滤条件
    if chain_key == "__global__":
        # 全局链：payload 里没有 project_id 或 project_id 为 null
        try:
            from app.core.config import settings
            is_pg = settings.DATABASE_URL.startswith("postgresql")
        except Exception:
            is_pg = db.bind.dialect.name == "postgresql" if db.bind else False

        if is_pg:
            chain_filter = (
                func.coalesce(ALE.payload["project_id"].astext, "") == ""
            )
        else:
            from sqlalchemy import literal_column
            chain_filter = (
                func.coalesce(
                    literal_column("json_extract(payload, '$.project_id')"), ""
                ) == ""
            )
    else:
        project_id = chain_key.removeprefix("project:")
        try:
            from app.core.config import settings
            is_pg = settings.DATABASE_URL.startswith("postgresql")
        except Exception:
            is_pg = db.bind.dialect.name == "postgresql" if db.bind else False

        if is_pg:
            chain_filter = ALE.payload["project_id"].astext == project_id
        else:
            from sqlalchemy import literal_column
            chain_filter = (
                literal_column("json_extract(payload, '$.project_id')") == project_id
            )

    # 该链所有条目
    all_stmt = select(ALE.id, ALE.entry_hash).where(chain_filter)
    all_rows = (await db.execute(all_stmt)).all()
    all_hashes = {row.entry_hash for row in all_rows}
    all_ids_by_hash = {row.entry_hash: row.id for row in all_rows}

    # 所有被引用为 prev_hash 的哈希（同链内）
    prev_stmt = select(ALE.prev_hash).where(chain_filter).where(
        ALE.prev_hash.in_(all_hashes)
    )
    referenced = {row[0] for row in (await db.execute(prev_stmt)).all()}

    # 链尾 = entry_hash 不在 referenced 里的条目
    tail_ids = set()
    for row in all_rows:
        if row.entry_hash not in referenced:
            tail_ids.add(row.id)

    # 减去已确认为 dead 的
    ack_stmt = select(ALE.payload).where(
        chain_filter, ALE.action_type == "audit.fork_ack"
    )
    ack_rows = (await db.execute(ack_stmt)).all()
    dead_ids: set[uuid.UUID] = set()
    for row in ack_rows:
        payload = row[0] or {}
        dead_str = payload.get("dead_entry_id")
        if dead_str:
            try:
                dead_ids.add(uuid.UUID(str(dead_str)))
            except (ValueError, TypeError):
                pass

    return tail_ids - dead_ids


async def scan_forks(
    db: AsyncSession, *, chain_key: str | None = None
) -> list[dict]:
    """只读扫描：找出 prev_hash 有多个后继的分叉点。

    返回 [{chain_key, forked_at_hash, survivors, dead_acknowledged, dead_unacknowledged}]
    """
    ALE = AuditLogEntry

    # 找 prev_hash 有多于 1 个后继的
    count_stmt = (
        select(ALE.prev_hash, func.count(ALE.id).label("cnt"))
        .group_by(ALE.prev_hash)
        .having(func.count(ALE.id) > 1)
    )
    fork_rows = (await db.execute(count_stmt)).all()

    if not fork_rows:
        return []

    fork_hashes = {row.prev_hash for row in fork_rows}

    # 收集所有 fork_ack 的 dead_entry_id
    ack_stmt = select(ALE.payload).where(ALE.action_type == "audit.fork_ack")
    ack_rows = (await db.execute(ack_stmt)).all()
    ack_dead_ids: set[str] = set()
    for row in ack_rows:
        payload = row[0] or {}
        dead_str = payload.get("dead_entry_id")
        if dead_str:
            ack_dead_ids.add(str(dead_str))

    results = []
    for fh in fork_hashes:
        # 该 prev_hash 的所有后继
        succ_stmt = select(ALE.id, ALE.payload).where(ALE.prev_hash == fh)
        succ_rows = (await db.execute(succ_stmt)).all()

        survivors = []
        dead_ack = []
        dead_unack = []

        for sr in succ_rows:
            sid = str(sr.id)
            if sid in ack_dead_ids:
                dead_ack.append(sid)
            else:
                survivors.append(sid)

        # 确定链键
        if chain_key:
            ck = chain_key
        else:
            # 按 forked_at_hash 找原条目判链键
            origin_stmt = select(ALE.payload).where(ALE.entry_hash == fh).limit(1)
            origin_row = (await db.execute(origin_stmt)).scalar_one_or_none()
            origin_payload = origin_row or {}
            pid = origin_payload.get("project_id") if isinstance(origin_payload, dict) else None
            ck = chain_key_of(pid)

        # 只要存活后继仍 >1 就是未确认分叉
        if len(survivors) > 1:
            results.append({
                "chain_key": ck,
                "forked_at_hash": fh,
                "survivors": survivors,
                "dead_acknowledged": dead_ack,
                "dead_unacknowledged": [],
            })
        elif dead_ack:
            # 已完全确认
            results.append({
                "chain_key": ck,
                "forked_at_hash": fh,
                "survivors": survivors,
                "dead_acknowledged": dead_ack,
                "dead_unacknowledged": [],
            })

    # 若指定 chain_key 则过滤
    if chain_key:
        results = [r for r in results if r["chain_key"] == chain_key]

    return results


async def append_fork_ack(
    db: AsyncSession,
    *,
    chain_key: str,
    survivor_entry_id: uuid.UUID,
    dead_entry_id: uuid.UUID,
    operator_id: uuid.UUID,
    reason: str,
) -> AuditLogEntry:
    """写入分叉确认条目。在链锁内校验链尾集合后插入。"""
    await lock_chain(db, chain_key)

    # 校验：该链未确认链尾恰为 {survivor, dead}
    tails = await _unconfirmed_tails(db, chain_key)
    expected = {survivor_entry_id, dead_entry_id}
    if tails != expected:
        raise ValueError(
            f"链 {chain_key} 未确认链尾不匹配。"
            f"期望: {sorted(str(x) for x in expected)}, "
            f"实际: {sorted(str(x) for x in tails)}"
        )

    # 取 survivor 的 entry_hash 作为 prev_hash
    ALE = AuditLogEntry
    surv_stmt = select(ALE.entry_hash).where(ALE.id == survivor_entry_id)
    surv_hash = (await db.execute(surv_stmt)).scalar_one()

    now = datetime.now(timezone.utc)
    ts_str = now.isoformat(timespec="microseconds")
    action_type = "audit.fork_ack"
    object_type = "audit_log_entry"
    payload = {
        "survivor_entry_id": str(survivor_entry_id),
        "dead_entry_id": str(dead_entry_id),
        "reason": reason,
        "operator_id": str(operator_id),
    }
    payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)

    entry_hash = hash_v1(
        ts_str, str(operator_id), action_type, "", payload_json, surv_hash
    )

    entry = AuditLogEntry(
        id=uuid.uuid4(),
        ts=now,
        user_id=operator_id,
        action_type=action_type,
        object_type=object_type,
        payload=payload,
        prev_hash=surv_hash,
        entry_hash=entry_hash,
    )
    db.add(entry)
    await db.flush()
    return entry
