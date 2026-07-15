# Feature: procedure-delegation-notification — Task 10 有序 outbox dispatcher
"""ProcedureDeliveryDispatcher 测试：Properties P29-P30 + PostgreSQL 集成。

Task 10 / 需求 10.1-10.6, 10.9, 13.2, 13.8 / Design C10、D8：

- **P29（aggregate version 有序投递）**：Requirements 10.1/10.2/10.3 —— 任意乱序 available 的同
  aggregate events，processed aggregate_version 严格单调；前一版本失败/在途时后一版本不越序。
- **P30（Notification 与 SSE 幂等收敛）**：Requirements 10.4/10.5/10.6/10.9 —— 每个 event+recipient
  最多一条 Notification；重复 event_id 的 SSE 不造成重复通知；SSE 失败可重试且最终收敛。

另含：双 dispatcher 无重复领取、lease 超时回收、dead-letter replay、开关关闭保留事件。

claim/lease/ordering/dedup 均依赖 PostgreSQL（FOR UPDATE SKIP LOCKED、部分唯一索引、
make_interval），不以 sqlite 替代；PBT 用项目 fast profile（max_examples 小）。
"""
from __future__ import annotations

import asyncio
import json
import random
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings as app_settings
from app.core.migration_runner import MigrationRunner
from app.services.procedure_delivery_dispatcher import (
    MAX_BACKOFF_SECONDS,
    ProcedureDeliveryDispatcher,
    _backoff_seconds,
)

_V105 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V105__procedure_row_tasks.sql"
)
_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")
_AGG = "procedure_row_task"


# ===========================================================================
# 纯逻辑单元测试（无 DB）
# ===========================================================================
class TestBackoffAndRules:
    def test_backoff_monotonic_capped(self):
        prev = 0.0
        for rc in range(1, 12):
            d = _backoff_seconds(rc)
            assert d >= prev or d == MAX_BACKOFF_SECONDS
            assert d <= MAX_BACKOFF_SECONDS
            prev = d
        assert _backoff_seconds(99) == MAX_BACKOFF_SECONDS

    def test_recipient_rules_cover_key_events(self):
        from app.services.procedure_delivery_dispatcher import _EVENT_RECIPIENT_RULES

        assert _EVENT_RECIPIENT_RULES["assigned"] == "assignee"
        assert _EVENT_RECIPIENT_RULES["submitted"] == "reviewer"
        assert _EVENT_RECIPIENT_RULES["changes_requested"] == "assignee"
        # 未映射类型不产生逐事件通知
        assert "acknowledged" not in _EVENT_RECIPIENT_RULES


# ===========================================================================
# PostgreSQL 集成脚手架
# ===========================================================================
async def _apply_v105(engine) -> None:
    sql = _V105.read_text(encoding="utf-8")
    for stmt in MigrationRunner._split_sql_statements(sql):
        async with engine.begin() as conn:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_ctx():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (dispatcher claim/lease/ordering/dedup)")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    await _apply_v105(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # 复用 dev 库现有 project + user；创建一个带 user_id 的 staff（通知收件人）。
    async with factory() as s:
        pid = (await s.execute(sa.text("SELECT id FROM projects LIMIT 1"))).scalar()
        uid = (await s.execute(sa.text("SELECT id FROM users LIMIT 1"))).scalar()
    if pid is None or uid is None:
        await engine.dispose()
        pytest.skip("dev 库无 project/user 可复用")

    staff_id = uuid.uuid4()
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO staff_members (id, user_id, name, source, is_deleted, created_at, updated_at) "
                "VALUES (:id, :uid, :nm, 'custom', false, now(), now())"
            ),
            {"id": staff_id, "uid": uid, "nm": "投递测试执行人"},
        )
        await s.commit()

    created_aggs: set[str] = set()

    try:
        yield {"factory": factory, "pid": pid, "uid": uid, "staff_id": staff_id, "aggs": created_aggs}
    finally:
        # 清理：删除本测试插入的 outbox 事件、通知、staff。
        async with factory() as s:
            for agg in created_aggs:
                await s.execute(
                    sa.text("DELETE FROM notifications WHERE event_id LIKE :p"),
                    {"p": f"{agg}:%"},
                )
                await s.execute(
                    sa.text("DELETE FROM task_events WHERE aggregate_id = :a"),
                    {"a": uuid.UUID(agg)},
                )
            await s.execute(sa.text("DELETE FROM staff_members WHERE id = :id"), {"id": staff_id})
            await s.commit()
        await engine.dispose()


async def _insert_event(
    ctx, *, aggregate_id, version, event_type, available_at="now()", staff_id=None
):
    """插入一条 outbox event（task_events），返回 outbox id。"""
    factory = ctx["factory"]
    ctx["aggs"].add(str(aggregate_id))
    oid = uuid.uuid4()
    idem = f"{aggregate_id}:{event_type}:{version}"
    payload = {
        "event_type": event_type,
        "task_id": str(aggregate_id),
        "project_id": str(ctx["pid"]),
        "assignee_staff_id": str(staff_id) if staff_id else None,
        "reviewer_staff_id": str(staff_id) if staff_id else None,
    }
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO task_events "
                "(id, project_id, event_type, payload, status, retry_count, max_retries, trace_id, "
                " created_at, aggregate_type, aggregate_id, aggregate_version, idempotency_key, available_at) "
                "VALUES (:id, :pid, :et, CAST(:pl AS jsonb), 'queued', 0, 3, :tr, now(), "
                f" :agg, :aid, :ver, :idem, {available_at})"
            ),
            {
                "id": oid, "pid": ctx["pid"], "et": f"procedure_task.{event_type}",
                "pl": json.dumps(payload), "tr": str(oid)[:64], "agg": _AGG,
                "aid": aggregate_id, "ver": version, "idem": idem,
            },
        )
        await s.commit()
    return oid


async def _processed_versions(ctx, aggregate_id) -> list[int]:
    async with ctx["factory"]() as s:
        rows = (
            await s.execute(
                sa.text(
                    "SELECT aggregate_version FROM task_events "
                    "WHERE aggregate_id = :a AND processed_at IS NOT NULL "
                    "ORDER BY processed_at, aggregate_version"
                ),
                {"a": aggregate_id},
            )
        ).scalars().all()
    return list(rows)


async def _notif_count(ctx, aggregate_id) -> int:
    async with ctx["factory"]() as s:
        return (
            await s.execute(
                sa.text("SELECT count(*) FROM notifications WHERE event_id LIKE :p"),
                {"p": f"{aggregate_id}:%"},
            )
        ).scalar()


def _enable_dispatcher(monkeypatch):
    monkeypatch.setattr(app_settings, "PROCEDURE_TASK_DISPATCHER_ENABLED", True, raising=False)


def _dispatcher(ctx, **kwargs):
    """构造 dispatcher 并注入 per-test session 工厂（避免全局引擎连接池跨事件循环复用）。"""
    return ProcedureDeliveryDispatcher(session_factory=ctx["factory"], **kwargs)


# ===========================================================================
# P29：aggregate version 有序投递
# Validates: Requirements 10.1, 10.2, 10.3
# ===========================================================================
@pytest.mark.asyncio
class TestP29OrderedDelivery:
    @given(perm=st.permutations(list(range(1, 6))))
    @settings(max_examples=5, deadline=None)
    async def test_processed_versions_strictly_monotonic(self, perm, monkeypatch, pg_ctx):
        """任意乱序 available 的同 aggregate events，processed 版本始终是 1..N 的连续前缀。"""
        _enable_dispatcher(monkeypatch)
        ctx = pg_ctx
        agg = uuid.uuid4()
        # 乱序 available（用 event_type=acknowledged 免通知依赖），版本 1..5。
        for v in perm:
            await _insert_event(ctx, aggregate_id=agg, version=v, event_type="acknowledged")

        dispatcher = _dispatcher(ctx, batch_size=10)
        # 反复投递直到 backlog 清空；每轮后 processed 集合必须是 1..k 前缀（无越序）。
        for _ in range(20):
            processed = await _processed_versions(ctx, agg)
            assert processed == sorted(processed), "processed 顺序必须单调"
            assert processed == list(range(1, len(processed) + 1)), "processed 必须是 1..k 连续前缀（不越序）"
            res = await dispatcher.run_once()
            if res["claimed"] == 0:
                break
        final = await _processed_versions(ctx, agg)
        assert final == [1, 2, 3, 4, 5]

    async def test_predecessor_failure_blocks_successor(self, monkeypatch, pg_ctx):
        """前一版本失败（在途重试）时，后一版本不得越序被领取/投递。"""
        _enable_dispatcher(monkeypatch)
        ctx = pg_ctx
        agg = uuid.uuid4()
        await _insert_event(ctx, aggregate_id=agg, version=1, event_type="acknowledged")
        await _insert_event(ctx, aggregate_id=agg, version=2, event_type="acknowledged")

        dispatcher = _dispatcher(ctx, batch_size=10)
        # 让 version 1 的 SSE 投递失败 → v1 退避重试（仍未 processed），v2 被阻塞。
        def boom(event):
            raise RuntimeError("sse down")
        dispatcher._broadcast_sse = boom

        res = await dispatcher.run_once()
        assert res["claimed"] == 1  # 只领到 v1（v2 被 NOT EXISTS 前序未完成阻塞）
        assert res["failed"] == 1
        assert await _processed_versions(ctx, agg) == []  # v1 失败未 processed

        # v2 仍未 processed 且未被领取（lease 为空、available 未到期无关——关键是没被越序处理）
        async with ctx["factory"]() as s:
            v2 = (
                await s.execute(
                    sa.text(
                        "SELECT processed_at FROM task_events "
                        "WHERE aggregate_id=:a AND aggregate_version=2"
                    ),
                    {"a": agg},
                )
            ).scalar()
        assert v2 is None

        # 恢复 SSE + 让 v1 可立即重试 → 顺序 1,2 处理完成。
        dispatcher2 = _dispatcher(ctx, batch_size=10)
        async with ctx["factory"]() as s:
            await s.execute(
                sa.text("UPDATE task_events SET available_at = now() WHERE aggregate_id=:a"),
                {"a": agg},
            )
            await s.commit()
        for _ in range(10):
            if await dispatcher2.run_once() == {"claimed": 0, "processed": 0, "failed": 0, "dead_letter": 0}:
                break
        assert await _processed_versions(ctx, agg) == [1, 2]


# ===========================================================================
# P30：Notification 与 SSE 幂等收敛
# Validates: Requirements 10.4, 10.5, 10.6, 10.9
# ===========================================================================
@pytest.mark.asyncio
class TestP30IdempotentConvergence:
    async def test_one_notification_per_event_recipient(self, monkeypatch, pg_ctx):
        _enable_dispatcher(monkeypatch)
        ctx = pg_ctx
        agg = uuid.uuid4()
        await _insert_event(
            ctx, aggregate_id=agg, version=1, event_type="assigned", staff_id=ctx["staff_id"]
        )
        dispatcher = _dispatcher(ctx)
        res = await dispatcher.run_once()
        assert res["processed"] == 1
        assert await _notif_count(ctx, agg) == 1

    async def test_redelivery_no_duplicate_notification(self, monkeypatch, pg_ctx):
        """重复投递同一 event（重置 processed_at 模拟重放）→ dedup 保证仍只有 1 条通知。"""
        _enable_dispatcher(monkeypatch)
        ctx = pg_ctx
        agg = uuid.uuid4()
        await _insert_event(
            ctx, aggregate_id=agg, version=1, event_type="assigned", staff_id=ctx["staff_id"]
        )
        dispatcher = _dispatcher(ctx)
        await dispatcher.run_once()
        assert await _notif_count(ctx, agg) == 1
        # 模拟 at-least-once 重放：重置 processed_at + available_at，再投递一次。
        async with ctx["factory"]() as s:
            await s.execute(
                sa.text(
                    "UPDATE task_events SET processed_at=NULL, status='queued', "
                    "available_at=now(), lease_expires_at=NULL, claimed_by=NULL "
                    "WHERE aggregate_id=:a"
                ),
                {"a": agg},
            )
            await s.commit()
        await dispatcher.run_once()
        assert await _notif_count(ctx, agg) == 1  # dedup 阻止重复

    async def test_sse_failure_retries_without_duplicate(self, monkeypatch, pg_ctx):
        """SSE 首次失败：通知已提交、event 未 processed；重试成功后仍只有 1 条通知。"""
        _enable_dispatcher(monkeypatch)
        ctx = pg_ctx
        agg = uuid.uuid4()
        await _insert_event(
            ctx, aggregate_id=agg, version=1, event_type="assigned", staff_id=ctx["staff_id"]
        )
        dispatcher = _dispatcher(ctx)

        calls = {"n": 0}
        real = dispatcher._broadcast_sse

        def flaky(event):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("sse down once")
            return real(event)

        dispatcher._broadcast_sse = flaky
        res = await dispatcher.run_once()
        assert res["failed"] == 1
        # 通知已在独立事务提交（领域/通知不因 SSE 失败回滚，Req 10.9）
        assert await _notif_count(ctx, agg) == 1
        assert await _processed_versions(ctx, agg) == []  # 未 processed → 可重试

        # 让其可立即重试并成功
        async with ctx["factory"]() as s:
            await s.execute(
                sa.text("UPDATE task_events SET available_at=now() WHERE aggregate_id=:a"),
                {"a": agg},
            )
            await s.commit()
        res2 = await dispatcher.run_once()
        assert res2["processed"] == 1
        assert await _notif_count(ctx, agg) == 1  # 重试不产生重复通知
        assert await _processed_versions(ctx, agg) == [1]


# ===========================================================================
# 双 dispatcher 无重复领取 + lease 超时回收
# ===========================================================================
@pytest.mark.asyncio
class TestConcurrencyAndLease:
    async def test_dual_dispatcher_no_double_claim(self, monkeypatch, pg_ctx):
        """两个 dispatcher 并发投递：每个 event 恰好一条通知、全部 processed，无重复。"""
        _enable_dispatcher(monkeypatch)
        ctx = pg_ctx
        # 多个不同 aggregate（都可领取），每个一条 assigned 事件。
        aggs = [uuid.uuid4() for _ in range(6)]
        for agg in aggs:
            await _insert_event(
                ctx, aggregate_id=agg, version=1, event_type="assigned", staff_id=ctx["staff_id"]
            )
        d1 = _dispatcher(ctx, worker_id="w1", batch_size=10)
        d2 = _dispatcher(ctx, worker_id="w2", batch_size=10)
        # 并发跑几轮直到清空
        for _ in range(6):
            r = await asyncio.gather(d1.run_once(), d2.run_once())
            if all(x["claimed"] == 0 for x in r):
                break
        # 每个 aggregate 恰好 1 条通知 + 1 条 processed
        for agg in aggs:
            assert await _notif_count(ctx, agg) == 1
            assert await _processed_versions(ctx, agg) == [1]

    async def test_expired_lease_reclaimed(self, monkeypatch, pg_ctx):
        """lease 过期的在途 event 可被回收并投递完成。"""
        _enable_dispatcher(monkeypatch)
        ctx = pg_ctx
        agg = uuid.uuid4()
        oid = await _insert_event(
            ctx, aggregate_id=agg, version=1, event_type="assigned", staff_id=ctx["staff_id"]
        )
        # 模拟另一 dispatcher 领取后崩溃：lease 已过期，processed_at 仍 NULL。
        async with ctx["factory"]() as s:
            await s.execute(
                sa.text(
                    "UPDATE task_events SET claimed_by='dead-worker', "
                    "lease_expires_at = now() - interval '10 seconds' WHERE id=:id"
                ),
                {"id": oid},
            )
            await s.commit()
        dispatcher = _dispatcher(ctx, worker_id="reclaimer")
        res = await dispatcher.run_once()
        assert res["claimed"] == 1 and res["processed"] == 1
        assert await _processed_versions(ctx, agg) == [1]


# ===========================================================================
# dead-letter + replay + 开关关闭保留事件
# ===========================================================================
@pytest.mark.asyncio
class TestDeadLetterReplayAndFlag:
    async def test_dead_letter_then_replay(self, monkeypatch, pg_ctx):
        """持续 SSE 失败 → 超过 max_retries 进 dead-letter；replay 后可重新投递成功。"""
        _enable_dispatcher(monkeypatch)
        ctx = pg_ctx
        agg = uuid.uuid4()
        await _insert_event(
            ctx, aggregate_id=agg, version=1, event_type="assigned", staff_id=ctx["staff_id"]
        )
        dispatcher = _dispatcher(ctx, max_retries=2)

        def boom(event):
            raise RuntimeError("sse permanently down")
        dispatcher._broadcast_sse = boom

        # 反复投递（每轮把 available_at 拨到现在以立即重试）直到 dead-letter。
        for _ in range(6):
            async with ctx["factory"]() as s:
                await s.execute(
                    sa.text("UPDATE task_events SET available_at=now() WHERE aggregate_id=:a"),
                    {"a": agg},
                )
                await s.commit()
            await dispatcher.run_once()

        # 用真实 session 查 dead-letter
        async with ctx["factory"]() as s:
            items = await ProcedureDeliveryDispatcher().list_dead_letters(s, ctx["pid"])
        dl_ids = [i["id"] for i in items if i["aggregate_id"] == str(agg)]
        assert len(dl_ids) == 1, "event 应进入 dead-letter"

        # replay → requeued
        async with ctx["factory"]() as s:
            healthy = ProcedureDeliveryDispatcher()
            result = await healthy.replay(s, ctx["pid"], uuid.UUID(dl_ids[0]))
            await s.commit()
        assert result["status"] == "requeued"

        # 正常 dispatcher 投递成功
        ok = _dispatcher(ctx)
        for _ in range(4):
            if (await ok.run_once())["claimed"] == 0:
                break
        assert await _processed_versions(ctx, agg) == [1]

    async def test_replay_non_dead_letter_conflict(self, monkeypatch, pg_ctx):
        """replay 未 dead-letter 的 event → 409。"""
        from fastapi import HTTPException

        ctx = pg_ctx
        agg = uuid.uuid4()
        oid = await _insert_event(ctx, aggregate_id=agg, version=1, event_type="acknowledged")
        async with ctx["factory"]() as s:
            with pytest.raises(HTTPException) as ei:
                await ProcedureDeliveryDispatcher().replay(s, ctx["pid"], oid)
            await s.rollback()
        assert ei.value.status_code == 409

    async def test_flag_disabled_keeps_events(self, monkeypatch, pg_ctx):
        """PROCEDURE_TASK_DISPATCHER_ENABLED=false 时不 claim，事件保留。"""
        monkeypatch.setattr(app_settings, "PROCEDURE_TASK_DISPATCHER_ENABLED", False, raising=False)
        ctx = pg_ctx
        agg = uuid.uuid4()
        await _insert_event(ctx, aggregate_id=agg, version=1, event_type="acknowledged")
        res = await _dispatcher(ctx).run_once()
        assert res.get("skipped") is True
        assert res["claimed"] == 0
        assert await _processed_versions(ctx, agg) == []  # 事件保留、未处理


# ===========================================================================
# 指标
# ===========================================================================
@pytest.mark.asyncio
class TestMetrics:
    async def test_metrics_reports_backlog_and_processed(self, monkeypatch, pg_ctx):
        _enable_dispatcher(monkeypatch)
        ctx = pg_ctx
        agg = uuid.uuid4()
        await _insert_event(ctx, aggregate_id=agg, version=1, event_type="acknowledged")
        await _insert_event(ctx, aggregate_id=agg, version=2, event_type="acknowledged")
        dispatcher = _dispatcher(ctx)
        async with ctx["factory"]() as s:
            m0 = await dispatcher.metrics(s)
        assert m0["backlog"] >= 2
        assert m0["oldest_age_seconds"] >= 0.0
        # 处理一轮后 backlog 下降、processed 上升
        await dispatcher.run_once()
        await dispatcher.run_once()
        async with ctx["factory"]() as s:
            m1 = await dispatcher.metrics(s)
        assert m1["processed"] >= 2
