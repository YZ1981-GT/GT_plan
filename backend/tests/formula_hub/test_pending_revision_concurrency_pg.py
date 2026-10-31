"""待确认事项修订号的并发原子性（spec formula-hub-integrity-closure 需求 8.1；ADR-FHIC-11；变异 #30）。

快照库内 ``committed_project`` 真提交一个【测试】项目；两个独立会话（各自的连接与事务、真提交）在屏障后同时调生产
``upsert_pending`` 写同一（项目, 域, 公式位）的待确认项：
- 覆盖：先真提交一条 pending（修订号 1），两个会话同时覆盖 ⇒ 两次 RETURNING 的修订号集合 {2, 3}，提交后为 3，
  且留下的是后提交者的新上游；
- 新建：两个会话同时新建 ⇒ {1, 2}，提交后为 2，不抛唯一约束错误；
两种情形都只剩一条 pending。另一条：处理与覆盖并发 —— 覆盖先写入（未提交），处理在行锁上等待，覆盖提交后按新修订号
判 409（处理的核对与覆盖在库内串行，``resolve_items`` 锁内 ``FOR UPDATE`` 重读）。

交错保证（否则「先查后改」也可能碰巧串行通过）：会话写完后不立即提交，而是等到另一会话「被它阻塞」（监控连接上
``pg_blocking_pids`` 含本会话）或「已写完」才提交。于是后到者的读取一定发生在先到者提交之前：原子语句里后到者在锁上
等待、先到者提交后在新行版本上 +1；先查后改则两次都读到旧修订号（覆盖：两次都得 2）或两个都插入（新建：撞唯一约束）。
用例断言观测到恰好一次阻塞，交错没有退化成串行。生产调用方另有项目咨询锁串行，这里直调服务函数，验的是库内原子性本身。
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import text

from app.services.formula_settings import project_ops
from app.services.formula_settings.errors import SyncItemStale
from app.services.formula_settings.pending import upsert_pending

pytestmark = pytest.mark.pg_only

DOMAIN = "tb_detail"
#: 单条语句等锁上限：交错出了问题时报错收场，不挂住整轮
LOCK_TIMEOUT = "15s"
WAIT_SECONDS = 20.0
RACE_SECONDS = 60.0


def _definition(code: str) -> dict:
    return {"formula": f"TB('{code}','期末余额')", "formula_category": "auto_calc"}


@dataclass
class Actor:
    name: str
    upstream: dict = field(default_factory=dict)
    pid: int | None = None
    revision: int | None = None
    error: BaseException | None = None
    wrote: asyncio.Event = field(default_factory=asyncio.Event)


async def _write(session, project_id: uuid.UUID, slot: str, upstream: dict) -> Any:
    return await upsert_pending(session, project_id=project_id, domain=DOMAIN, slot_key=slot, slot_label="并发写入",
                                reason="conflict", base_definition=None, upstream_definition=upstream,
                                upstream_version=None, local_definition=None, publish_id=None,
                                upstream_origin="project")


async def _begin(session, me: Actor) -> None:
    """开事务、设等锁上限、记下本会话的后端进程号（监控按它判谁在等谁）。"""
    await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    me.pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()


async def _wait_until_blocked_or_wrote(monitor, *, waiter: Actor, blocker: Actor, observed: list) -> None:
    """等到 ``waiter`` 被 ``blocker`` 阻塞（记一次）或已写完；超时即失败。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAIT_SECONDS
    while not waiter.wrote.is_set():
        if waiter.pid is not None:
            blocked = (await monitor.execute(text("SELECT CAST(:b AS integer) = ANY(pg_blocking_pids(:w))"),
                                             {"w": waiter.pid, "b": blocker.pid})).scalar_one()
            if blocked:
                observed.append(f"{waiter.name}等{blocker.name}")
                return
        if loop.time() > deadline:
            raise TimeoutError(f"{waiter.name} 在 {WAIT_SECONDS:.0f} 秒内既没有被 {blocker.name} 阻塞也没有写完")
        await asyncio.sleep(0.02)


async def _racer(handle, me: Actor, other: Actor, slot: str, barrier: asyncio.Barrier, observed: list) -> None:
    monitor_engine = handle.engine.execution_options(isolation_level="AUTOCOMMIT")
    async with monitor_engine.connect() as monitor, handle.session() as session:
        await _begin(session, me)
        await barrier.wait()
        try:
            me.revision = (await _write(session, handle.project_id, slot, me.upstream)).revision
        except Exception as exc:  # noqa: BLE001 —— 记下由用例断言（先查后改在新建情形撞唯一约束）
            me.error = exc
            me.wrote.set()
            await session.rollback()
            return
        me.wrote.set()
        await _wait_until_blocked_or_wrote(monitor, waiter=other, blocker=me, observed=observed)
        await session.commit()


async def _race(handle, slot: str) -> tuple[list[Actor], list[str]]:
    actors = [Actor("甲", _definition("1001")), Actor("乙", _definition("1002"))]
    barrier, observed = asyncio.Barrier(2), []
    await asyncio.wait_for(asyncio.gather(
        _racer(handle, actors[0], actors[1], slot, barrier, observed),
        _racer(handle, actors[1], actors[0], slot, barrier, observed)), timeout=RACE_SECONDS)
    return actors, observed


async def _rows_and_track(handle, slot: str) -> list[dict[str, Any]]:
    """另开连接读已提交的行，并登记给 committed_project 结束时删除。"""
    async with handle.engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, status, revision, upstream_definition FROM formula_sync_item "
            "WHERE project_id = :pid AND domain = :domain AND slot_key = :slot ORDER BY revision"),
            {"pid": handle.project_id, "domain": DOMAIN, "slot": slot})).mappings().all()
    for row in rows:
        handle.track("formula_sync_item", id=row["id"])
    return [dict(row) for row in rows]


def _slot() -> str:
    return f"fh_t6_race:{uuid.uuid4().hex[:8]}"


async def test_concurrent_overwrite_returns_two_and_three(committed_project) -> None:
    handle, slot = committed_project, _slot()
    try:
        async with handle.session() as session:
            assert (await _write(session, handle.project_id, slot, _definition("1000"))).revision == 1
            await session.commit()
        actors, observed = await _race(handle, slot)
    finally:
        rows = await _rows_and_track(handle, slot)
    assert [a.error for a in actors] == [None, None], [repr(a.error) for a in actors]
    assert sorted(a.revision for a in actors) == [2, 3], [(a.name, a.revision) for a in actors]
    assert len(observed) == 1, f"交错退化成了串行（没有观测到阻塞）：{observed}"
    last = max(actors, key=lambda a: a.revision)
    assert [(r["status"], r["revision"], r["upstream_definition"]) for r in rows] == [
        ("pending", 3, last.upstream)], rows


async def test_concurrent_create_returns_one_and_two(committed_project) -> None:
    handle, slot = committed_project, _slot()
    try:
        actors, observed = await _race(handle, slot)
    finally:
        rows = await _rows_and_track(handle, slot)
    assert [a.error for a in actors] == [None, None], [repr(a.error) for a in actors]
    assert sorted(a.revision for a in actors) == [1, 2], [(a.name, a.revision) for a in actors]
    assert len(observed) == 1, f"交错退化成了串行（没有观测到阻塞）：{observed}"
    last = max(actors, key=lambda a: a.revision)
    assert [(r["status"], r["revision"], r["upstream_definition"]) for r in rows] == [
        ("pending", 2, last.upstream)], rows


async def test_resolve_waits_for_concurrent_overwrite_then_409(committed_project) -> None:
    """覆盖先写入（未提交）：处理在行锁上等待，覆盖提交后读到修订号 2 ⇒ 409；处理的会话不提交任何东西。"""
    handle, slot = committed_project, _slot()
    writer, resolver, observed = Actor("覆盖", _definition("1002")), Actor("处理"), []
    try:
        async with handle.session() as session:
            item = await _write(session, handle.project_id, slot, _definition("1001"))
            item_id, seen_revision = item.id, item.revision
            await session.commit()

        async def overwrite() -> None:
            monitor_engine = handle.engine.execution_options(isolation_level="AUTOCOMMIT")
            async with monitor_engine.connect() as monitor, handle.session() as session:
                await _begin(session, writer)
                writer.revision = (await _write(session, handle.project_id, slot, writer.upstream)).revision
                writer.wrote.set()
                await _wait_until_blocked_or_wrote(monitor, waiter=resolver, blocker=writer, observed=observed)
                await session.commit()

        async def resolve() -> None:
            async with handle.session() as session:
                await _begin(session, resolver)
                await writer.wrote.wait()
                try:
                    await project_ops.resolve_items(session, project_id=handle.project_id, user_id=None, resolutions=[
                        {"item_id": str(item_id), "choice": "keep", "revision": seen_revision}])
                except Exception as exc:  # noqa: BLE001 —— 由用例断言
                    resolver.error = exc
                finally:
                    resolver.wrote.set()
                    await session.rollback()

        await asyncio.wait_for(asyncio.gather(overwrite(), resolve()), timeout=RACE_SECONDS)
    finally:
        rows = await _rows_and_track(handle, slot)
    assert (seen_revision, writer.revision) == (1, 2)
    assert observed == ["处理等覆盖"], f"处理没有在覆盖的行锁上等待：{observed}"
    assert isinstance(resolver.error, SyncItemStale), repr(resolver.error)
    assert (resolver.error.detail["revision"], resolver.error.detail["expected_revision"]) == (2, 1)
    assert [(r["status"], r["revision"], r["upstream_definition"]) for r in rows] == [
        ("pending", 2, writer.upstream)], rows
