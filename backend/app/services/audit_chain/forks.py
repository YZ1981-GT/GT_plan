"""审计哈希链 — 分叉扫描与确认

ADR-ALC-03: 分叉确认先于 fail-closed。
- scan_forks: 只读扫描，识别 prev_hash 有多个后继的分叉点
- blocked_chains / plan_chain_forks: 只读，列出未确认链尾 ≠ 1 的链与处理计划（建议主链尾、各死端侧枝）
- append_fork_acks: 在链锁内校验后，一次确认一条链上的多个死端（spec enterprise-embedding-rerank-closure R8）
- append_fork_ack: 单死端的薄封装（签名与返回值不变）

「已确认」的读者（head._dead_entry_ids、_unconfirmed_tails、scan_forks、verify.verify_chain）都只读确认条目载荷里的
标量 ``dead_entry_id``；多死端按「每条确认条目点名一个条目、从主链尾起首尾相接」写入，读者不用改。
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log_models import AuditChainHead, AuditLogEntry

from .canonical import GENESIS_HASH, hash_v2
from .head import (
    AuditChainForked,
    _business_payload,
    _chain_filter,
    _dead_entry_ids,
    _normalise_timestamp,
    chain_key_of,
    lock_chain,
    read_head,
)

FORK_ACK_ACTION = "audit.fork_ack"
FORK_ACK_OBJECT = "audit_log_entry"


@dataclass(frozen=True)
class ChainRow:
    id: uuid.UUID
    entry_hash: str
    prev_hash: str
    ts: datetime | None
    action_type: str


@dataclass(frozen=True)
class DeadBranch:
    """主链之外的一支：从侧枝根（父条目在主链上）到死端链尾。"""

    tail_id: uuid.UUID
    root_id: uuid.UUID
    entry_ids: tuple[uuid.UUID, ...]  # 根 → 尾
    first_ts: datetime | None
    last_ts: datetime | None
    actions: tuple[str, ...]


@dataclass(frozen=True)
class ForkPlan:
    chain_key: str
    entry_count: int
    tails: tuple[uuid.UUID, ...]          # 未确认链尾（按时间、id 排序）
    survivor_id: uuid.UUID | None         # 主链尾（建议：时间最新且唯一的链尾）
    branches: tuple[DeadBranch, ...]      # 其余链尾各自的侧枝
    ack_ids: tuple[uuid.UUID, ...]        # 要写确认条目的条目：死端 ∪ 分叉点上的侧枝根（含侧枝内再分叉）


def _sort_key(row: ChainRow) -> tuple[str, str]:
    return (row.ts.isoformat() if row.ts else "", str(row.id))


async def _chain_rows(db: AsyncSession, chain_key: str) -> list[ChainRow]:
    ale = AuditLogEntry
    rows = (
        await db.execute(
            select(ale.id, ale.entry_hash, ale.prev_hash, ale.ts, ale.action_type).where(
                _chain_filter(db, chain_key)
            )
        )
    ).all()
    return [ChainRow(r.id, r.entry_hash, r.prev_hash, r.ts, r.action_type) for r in rows]


def _tail_ids(rows: Sequence[ChainRow], dead_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """与 ``head.read_head`` 同一定义：同链内没有后继、且未被确认为死端的条目。"""
    hashes = {row.entry_hash for row in rows}
    referenced = {row.prev_hash for row in rows if row.prev_hash in hashes}
    return {row.id for row in rows if row.entry_hash not in referenced} - set(dead_ids)


async def _unconfirmed_tails(db: AsyncSession, chain_key: str) -> set[uuid.UUID]:
    """该链未确认的链尾条目 ID 集合（一次查询、按会话方言；不按哈希逐个绑定参数）。"""
    rows = await _chain_rows(db, chain_key)
    return _tail_ids(rows, await _dead_entry_ids(db, chain_key))


def build_fork_plan(
    chain_key: str,
    rows: Sequence[ChainRow],
    dead_ids: Iterable[uuid.UUID],
    *,
    survivor_id: uuid.UUID | None = None,
) -> ForkPlan:
    """纯函数：按链接关系求主链尾、各死端侧枝与要写的确认集合。"""
    by_id = {row.id: row for row in rows}
    by_hash = {row.entry_hash: row for row in rows}
    children: dict[str, int] = defaultdict(int)
    for row in rows:
        children[row.prev_hash] += 1
    tails = sorted((by_id[i] for i in _tail_ids(rows, dead_ids)), key=_sort_key)
    if survivor_id is None and tails:
        newest = tails[-1]
        if len(tails) == 1 or (newest.ts is not None and tails[-2].ts != newest.ts):
            survivor_id = newest.id
    if survivor_id is None or survivor_id not in by_id:
        return ForkPlan(chain_key, len(rows), tuple(t.id for t in tails), None, (), ())

    ancestors: set[uuid.UUID] = set()
    cur: ChainRow | None = by_id[survivor_id]
    while cur is not None and cur.id not in ancestors:
        ancestors.add(cur.id)
        cur = by_hash.get(cur.prev_hash)

    branches: list[DeadBranch] = []
    acked: dict[uuid.UUID, ChainRow] = {}
    for tail in tails:
        if tail.id == survivor_id:
            continue
        path: list[ChainRow] = []
        seen: set[uuid.UUID] = set()
        node: ChainRow | None = tail
        while node is not None and node.id not in ancestors and node.id not in seen:
            seen.add(node.id)
            path.append(node)
            node = by_hash.get(node.prev_hash)
        path.reverse()  # 根 → 尾
        for item in path:
            if item.id == tail.id or children[item.prev_hash] >= 2:
                acked[item.id] = item
        branches.append(DeadBranch(
            tail_id=tail.id,
            root_id=path[0].id,
            entry_ids=tuple(p.id for p in path),
            first_ts=path[0].ts,
            last_ts=path[-1].ts,
            actions=tuple(dict.fromkeys(p.action_type for p in path)),
        ))
    ordered = tuple(row.id for row in sorted(acked.values(), key=_sort_key))
    return ForkPlan(
        chain_key, len(rows), tuple(t.id for t in tails), survivor_id, tuple(branches), ordered
    )


async def plan_chain_forks(
    db: AsyncSession, chain_key: str, *, survivor_id: uuid.UUID | None = None
) -> ForkPlan:
    """只读：该链的处理计划（不加锁，执行时 ``append_fork_acks`` 会在锁内重算并校验）。"""
    rows = await _chain_rows(db, chain_key)
    return build_fork_plan(
        chain_key, rows, await _dead_entry_ids(db, chain_key), survivor_id=survivor_id
    )


async def blocked_chains(db: AsyncSession) -> list[tuple[str, int, int]]:
    """只读：未确认链尾数 ≠ 1 的链 ``[(链键, 条目数, 未确认链尾数)]``（与写链内核同一定义）。"""
    ale = AuditLogEntry
    rows = (await db.execute(select(ale.id, ale.entry_hash, ale.prev_hash, ale.action_type, ale.payload))).all()
    grouped: dict[str, list[ChainRow]] = defaultdict(list)
    dead: dict[str, set[uuid.UUID]] = defaultdict(set)
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        key = chain_key_of(payload.get("project_id") or None)
        grouped[key].append(ChainRow(row.id, row.entry_hash, row.prev_hash, None, row.action_type))
        raw = payload.get("dead_entry_id") if row.action_type == FORK_ACK_ACTION else None
        if raw:
            try:
                dead[key].add(uuid.UUID(str(raw)))
            except (TypeError, ValueError):
                continue
    result = []
    for key, items in grouped.items():
        count = len(_tail_ids(items, dead[key]))
        if count != 1:
            result.append((key, len(items), count))
    return sorted(result, key=lambda item: (-item[1], item[0]))


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
        # 每条独立链都从同一个创世哈希开始；它们不是彼此的分叉。
        .where(ALE.prev_hash != GENESIS_HASH)
        .group_by(ALE.prev_hash)
        .having(func.count(ALE.id) > 1)
    )
    fork_rows = (await db.execute(count_stmt)).all()

    if not fork_rows:
        return []

    fork_hashes = {row.prev_hash for row in fork_rows}

    # 收集所有 fork_ack 的 dead_entry_id
    ack_stmt = select(ALE.payload).where(ALE.action_type == FORK_ACK_ACTION)
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

        for sr in succ_rows:
            sid = str(sr.id)
            if sid in ack_dead_ids:
                dead_ack.append(sid)
            else:
                survivors.append(sid)

        # 链键一律按分叉点所在条目推导；指定 chain_key 时最后再过滤
        # （原实现直接把每条结果标成传入值，过滤恒真，只读演示的 --chain-key 不起作用）。
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

    if chain_key:
        results = [r for r in results if r["chain_key"] == chain_key]

    return results


def _ack_entry(
    *,
    chain_key: str,
    prev_hash: str,
    survivor_id: uuid.UUID,
    target: ChainRow,
    role: str,
    reason: str,
    operator_id: uuid.UUID,
    batch_id: uuid.UUID,
    index: int,
    size: int,
) -> AuditLogEntry:
    """一条确认条目：与 ``head.append_entry`` 同一套 v2 规范化与哈希（链校验可重算）。"""
    project_text = None if chain_key == "__global__" else chain_key.removeprefix("project:")
    business = _business_payload(
        {
            "survivor_entry_id": str(survivor_id),
            "dead_entry_id": str(target.id),
            "dead_role": role,
            "dead_prev_hash": target.prev_hash,
            "reason": reason,
            "operator_id": str(operator_id),
            "batch_id": str(batch_id),
            "batch_index": index,
            "batch_size": size,
        },
        project_text,
    )
    when, ts_text = _normalise_timestamp(None)
    entry_hash = hash_v2(
        ts=ts_text,
        user_id=str(operator_id),
        action_type=FORK_ACK_ACTION,
        object_type=FORK_ACK_OBJECT,
        resource_id=str(target.id),
        project_id=project_text,
        year=None,
        payload=business,
        prev_hash=prev_hash,
    )
    stored = dict(business)
    stored["_hash_v"] = 2
    stored["_resource_id"] = str(target.id)
    return AuditLogEntry(
        id=uuid.uuid4(),
        ts=when,
        user_id=operator_id,
        action_type=FORK_ACK_ACTION,
        object_type=FORK_ACK_OBJECT,
        object_id=target.id,
        payload=stored,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )


async def append_fork_acks(
    db: AsyncSession,
    *,
    chain_key: str,
    survivor_entry_id: uuid.UUID,
    dead_entry_ids: Sequence[uuid.UUID],
    operator_id: uuid.UUID,
    reason: str,
) -> list[AuditLogEntry]:
    """在链锁内一次确认多个死端；写后该链必须恰好剩一个未确认链尾（最后一条确认条目），否则抛错由调用方回滚。"""
    deads = list(dict.fromkeys(dead_entry_ids))
    if not deads:
        raise ValueError("至少点名一个死端链尾")
    if survivor_entry_id in deads:
        raise ValueError("主链尾不能同时点名为死端")
    if not str(reason or "").strip():
        raise ValueError("确认原因不能为空")

    await lock_chain(db, chain_key)
    rows = await _chain_rows(db, chain_key)
    already_dead = await _dead_entry_ids(db, chain_key)
    tails = _tail_ids(rows, already_dead)
    expected = {survivor_entry_id, *deads}
    if tails != expected:
        raise ValueError(
            f"链 {chain_key} 未确认链尾不匹配。"
            f"期望: {sorted(str(x) for x in expected)}, "
            f"实际: {sorted(str(x) for x in tails)}"
        )

    plan = build_fork_plan(chain_key, rows, already_dead, survivor_id=survivor_entry_id)
    by_id = {row.id: row for row in rows}
    targets = [by_id[i] for i in plan.ack_ids if i not in already_dead]
    prev_hash = by_id[survivor_entry_id].entry_hash
    batch_id = uuid.uuid4()
    written: list[AuditLogEntry] = []
    for index, target in enumerate(targets, 1):
        is_tail = target.id in deads
        is_root = any(branch.root_id == target.id for branch in plan.branches)
        role = "tail_and_root" if is_tail and is_root else "tail" if is_tail else "branch_root"
        entry = _ack_entry(
            chain_key=chain_key, prev_hash=prev_hash, survivor_id=survivor_entry_id,
            target=target, role=role, reason=reason, operator_id=operator_id,
            batch_id=batch_id, index=index, size=len(targets),
        )
        db.add(entry)
        written.append(entry)
        prev_hash = entry.entry_hash

    # 旧链尾表可能仍指向分叉前的分支：删除后在同一事务里按确认记录重新惰性初始化，并核对结果。
    existing_head = await db.get(AuditChainHead, chain_key)
    if existing_head is not None:
        await db.delete(existing_head)
    await db.flush()
    head = await read_head(db, chain_key)
    if head is None or head.tail_entry_id != written[-1].id:
        raise AuditChainForked(f"链 {chain_key} 确认后链尾不是最后一条确认条目，已拒绝")
    return written


async def append_fork_ack(
    db: AsyncSession,
    *,
    chain_key: str,
    survivor_entry_id: uuid.UUID,
    dead_entry_id: uuid.UUID,
    operator_id: uuid.UUID,
    reason: str,
) -> AuditLogEntry:
    """写入分叉确认条目（单死端）。在链锁内校验链尾集合后插入，返回最后一条确认条目。"""
    written = await append_fork_acks(
        db,
        chain_key=chain_key,
        survivor_entry_id=survivor_entry_id,
        dead_entry_ids=[dead_entry_id],
        operator_id=operator_id,
        reason=reason,
    )
    return written[-1]


__all__ = [
    "ChainRow",
    "DeadBranch",
    "FORK_ACK_ACTION",
    "ForkPlan",
    "append_fork_ack",
    "append_fork_acks",
    "blocked_chains",
    "build_fork_plan",
    "plan_chain_forks",
    "scan_forks",
]
