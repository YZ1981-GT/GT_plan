# Feature: procedure-delegation-notification — Task 11 通知聚合 / metadata / 深链刷新
"""AggregatingNotificationProjection 测试：Property P31 + N task/M recipient 聚合 + 重复 SSE 幂等。

Task 11 / 需求 10.4-10.9, 14.2-14.3 / Design C10、D8、F4：

- **P31（批量通知聚合不损失审计）**：Requirements 10.7/10.8 —— N 个 task 委派始终产生 N 组
  task history/outbox（由 TransitionService 逐事件保证，见 transition 测试）；每个
  recipient/batch **至多一条** 摘要通知，摘要 task_count == 其相关任务数。
- **P30 补充（Notification 与 SSE 幂等收敛）**：Requirements 10.4-10.6/10.9 —— at-least-once
  重投递下摘要计数幂等（underlying task_event_ids 去重），不重复计数、不重复通知。
- **metadata 驱动跳转（10.8）**：摘要 metadata 含 event_id/batch_id/project/task_count/
  task_ids/filter，不从中文 content 解析路由。

聚合 UPSERT 依赖 PostgreSQL（jsonb_set/jsonb_exists/部分唯一索引 ON CONFLICT），不以 sqlite
替代；PBT 用项目 fast profile（max_examples 小）。
"""
from __future__ import annotations

import json
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
    AGG_MESSAGE_TYPE,
    AggregatingNotificationProjection,
    ProcedureDeliveryDispatcher,
)

_V105 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V105__procedure_row_tasks.sql"
)
_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")
_AGG = "procedure_row_task"


async def _apply_v105(engine) -> None:
    sql = _V105.read_text(encoding="utf-8")
    for stmt in MigrationRunner._split_sql_statements(sql):
        async with engine.begin() as conn:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_ctx():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (aggregation upsert / jsonb / partial unique)")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    await _apply_v105(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        pid = (await s.execute(sa.text("SELECT id FROM projects LIMIT 1"))).scalar()
        user_ids = (
            (await s.execute(sa.text("SELECT id FROM users LIMIT 4"))).scalars().all()
        )
    if pid is None or not user_ids:
        await engine.dispose()
        pytest.skip("dev 库无 project/user 可复用")

    # 为每个 user 建一个带 user_id 的 staff（通知收件人）。
    staff_by_user: dict = {}
    async with factory() as s:
        for uid in user_ids:
            sid = uuid.uuid4()
            await s.execute(
                sa.text(
                    "INSERT INTO staff_members (id, user_id, name, source, is_deleted, "
                    "created_at, updated_at) "
                    "VALUES (:id, :uid, :nm, 'custom', false, now(), now())"
                ),
                {"id": sid, "uid": uid, "nm": f"聚合测试执行人{str(sid)[:6]}"},
            )
            staff_by_user[uid] = sid
        await s.commit()

    created_batches: set[str] = set()
    created_aggs: set[str] = set()

    try:
        yield {
            "factory": factory,
            "pid": pid,
            "user_ids": list(user_ids),
            "staff_by_user": staff_by_user,
            "batches": created_batches,
            "aggs": created_aggs,
        }
    finally:
        async with factory() as s:
            for bid in created_batches:
                await s.execute(
                    sa.text("DELETE FROM notifications WHERE event_id = :e"),
                    {"e": f"batch:{bid}"},
                )
                await s.execute(
                    sa.text("DELETE FROM task_events WHERE delegation_batch_id = :b"),
                    {"b": uuid.UUID(bid)},
                )
            for agg in created_aggs:
                await s.execute(
                    sa.text("DELETE FROM notifications WHERE event_id LIKE :p"),
                    {"p": f"{agg}:%"},
                )
                await s.execute(
                    sa.text("DELETE FROM task_events WHERE aggregate_id = :a"),
                    {"a": uuid.UUID(agg)},
                )
            for sid in staff_by_user.values():
                await s.execute(
                    sa.text("DELETE FROM staff_members WHERE id = :id"), {"id": sid}
                )
            await s.commit()
        await engine.dispose()


async def _insert_batch_event(ctx, *, batch_id, task_id, staff_id, event_type="assigned"):
    """插入一条批量委派 outbox event（每个 task 一个独立 aggregate_id=task_id）。"""
    factory = ctx["factory"]
    ctx["batches"].add(str(batch_id))
    ctx["aggs"].add(str(task_id))
    oid = uuid.uuid4()
    idem = f"{task_id}:{event_type}:1"
    payload = {
        "event_type": event_type,
        "task_id": str(task_id),
        "project_id": str(ctx["pid"]),
        "assignee_staff_id": str(staff_id),
        "reviewer_staff_id": None,
    }
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO task_events "
                "(id, project_id, event_type, payload, status, retry_count, max_retries, "
                " trace_id, created_at, aggregate_type, aggregate_id, aggregate_version, "
                " idempotency_key, delegation_batch_id, available_at) "
                "VALUES (:id, :pid, :et, CAST(:pl AS jsonb), 'queued', 0, 3, :tr, now(), "
                " :agg, :aid, 1, :idem, :bid, now())"
            ),
            {
                "id": oid, "pid": ctx["pid"], "et": f"procedure_task.{event_type}",
                "pl": json.dumps(payload), "tr": str(oid)[:64], "agg": _AGG,
                "aid": task_id, "idem": idem, "bid": batch_id,
            },
        )
        await s.commit()
    return oid


async def _summary_rows(ctx, batch_id):
    async with ctx["factory"]() as s:
        rows = (
            await s.execute(
                sa.text(
                    "SELECT recipient_user_id, message_type, metadata, is_read "
                    "FROM notifications WHERE event_id = :e"
                ),
                {"e": f"batch:{batch_id}"},
            )
        ).mappings().all()
    return [dict(r) for r in rows]


def _enable(monkeypatch):
    monkeypatch.setattr(app_settings, "PROCEDURE_TASK_DISPATCHER_ENABLED", True, raising=False)


def _dispatcher(ctx, **kw):
    return ProcedureDeliveryDispatcher(session_factory=ctx["factory"], **kw)


# ===========================================================================
# 默认投影 = 聚合投影
# ===========================================================================
def test_dispatcher_default_projection_is_aggregating():
    d = ProcedureDeliveryDispatcher()
    assert isinstance(d.projection, AggregatingNotificationProjection)


# ===========================================================================
# P31：N task 委派 → 1 条摘要通知，count == N
# Validates: Requirements 10.7, 10.8
# ===========================================================================
@pytest.mark.asyncio
class TestP31Aggregation:
    @given(n_tasks=st.integers(min_value=1, max_value=6))
    @settings(max_examples=5, deadline=None)
    async def test_single_recipient_summary_count_equals_tasks(self, n_tasks, monkeypatch, pg_ctx):
        _enable(monkeypatch)
        ctx = pg_ctx
        recipient_uid = ctx["user_ids"][0]
        staff_id = ctx["staff_by_user"][recipient_uid]
        batch_id = uuid.uuid4()
        task_ids = [uuid.uuid4() for _ in range(n_tasks)]
        for tid in task_ids:
            await _insert_batch_event(ctx, batch_id=batch_id, task_id=tid, staff_id=staff_id)

        dispatcher = _dispatcher(ctx, batch_size=50)
        for _ in range(n_tasks + 3):
            if (await dispatcher.run_once())["claimed"] == 0:
                break

        rows = await _summary_rows(ctx, batch_id)
        assert len(rows) == 1, "每个 recipient/batch 至多一条摘要通知"
        meta = rows[0]["metadata"]
        assert rows[0]["message_type"] == AGG_MESSAGE_TYPE
        assert meta["task_count"] == n_tasks, "摘要计数须等于其相关任务数"
        assert len(meta["task_ids"]) == n_tasks
        assert set(meta["task_ids"]) == {str(t) for t in task_ids}
        # metadata 驱动跳转字段（不解析中文 content）
        assert meta["batch_id"] == str(batch_id)
        assert meta["event_id"] == f"batch:{batch_id}"
        assert meta["project_id"] == str(ctx["pid"])
        assert meta["filter"]["delegation_batch_id"] == str(batch_id)

    async def test_multi_recipient_each_own_summary(self, monkeypatch, pg_ctx):
        """N task / M recipient：每 recipient 一条摘要，count == 该 recipient 的任务数。"""
        _enable(monkeypatch)
        ctx = pg_ctx
        if len(ctx["user_ids"]) < 2:
            pytest.skip("需要至少 2 个 user 做多收件人聚合")
        batch_id = uuid.uuid4()
        # recipient A 分 3 个 task，recipient B 分 2 个 task
        uid_a, uid_b = ctx["user_ids"][0], ctx["user_ids"][1]
        staff_a, staff_b = ctx["staff_by_user"][uid_a], ctx["staff_by_user"][uid_b]
        a_tasks = [uuid.uuid4() for _ in range(3)]
        b_tasks = [uuid.uuid4() for _ in range(2)]
        for tid in a_tasks:
            await _insert_batch_event(ctx, batch_id=batch_id, task_id=tid, staff_id=staff_a)
        for tid in b_tasks:
            await _insert_batch_event(ctx, batch_id=batch_id, task_id=tid, staff_id=staff_b)

        dispatcher = _dispatcher(ctx, batch_size=50)
        for _ in range(10):
            if (await dispatcher.run_once())["claimed"] == 0:
                break

        rows = await _summary_rows(ctx, batch_id)
        by_uid = {r["recipient_user_id"]: r for r in rows}
        assert len(rows) == 2, "两个 recipient 各一条摘要"
        assert by_uid[uid_a]["metadata"]["task_count"] == 3
        assert by_uid[uid_b]["metadata"]["task_count"] == 2
        assert set(by_uid[uid_a]["metadata"]["task_ids"]) == {str(t) for t in a_tasks}
        assert set(by_uid[uid_b]["metadata"]["task_ids"]) == {str(t) for t in b_tasks}


# ===========================================================================
# P30 补充：重复投递（at-least-once）不膨胀摘要计数
# Validates: Requirements 10.4, 10.5, 10.6, 10.9
# ===========================================================================
@pytest.mark.asyncio
class TestAggregationIdempotency:
    async def test_redelivery_does_not_inflate_count(self, monkeypatch, pg_ctx):
        _enable(monkeypatch)
        ctx = pg_ctx
        recipient_uid = ctx["user_ids"][0]
        staff_id = ctx["staff_by_user"][recipient_uid]
        batch_id = uuid.uuid4()
        task_ids = [uuid.uuid4() for _ in range(3)]
        for tid in task_ids:
            await _insert_batch_event(ctx, batch_id=batch_id, task_id=tid, staff_id=staff_id)

        dispatcher = _dispatcher(ctx, batch_size=50)
        for _ in range(6):
            if (await dispatcher.run_once())["claimed"] == 0:
                break
        rows = await _summary_rows(ctx, batch_id)
        assert rows[0]["metadata"]["task_count"] == 3

        # 模拟 at-least-once 重放：重置全部 batch 事件的 processed_at，再投递一轮
        async with ctx["factory"]() as s:
            await s.execute(
                sa.text(
                    "UPDATE task_events SET processed_at=NULL, status='queued', "
                    "available_at=now(), lease_expires_at=NULL, claimed_by=NULL "
                    "WHERE delegation_batch_id=:b"
                ),
                {"b": batch_id},
            )
            await s.commit()
        for _ in range(6):
            if (await dispatcher.run_once())["claimed"] == 0:
                break

        rows2 = await _summary_rows(ctx, batch_id)
        assert len(rows2) == 1, "重投递不产生第二条摘要"
        assert rows2[0]["metadata"]["task_count"] == 3, "重投递不膨胀计数（underlying event_ids 去重）"
        assert len(rows2[0]["metadata"]["task_ids"]) == 3


# ===========================================================================
# 非批量事件回退逐事件通知（聚合投影不吞掉单个转换通知）
# ===========================================================================
@pytest.mark.asyncio
class TestNonBatchFallback:
    async def test_non_batch_event_falls_back_to_per_event(self, monkeypatch, pg_ctx):
        _enable(monkeypatch)
        ctx = pg_ctx
        recipient_uid = ctx["user_ids"][0]
        staff_id = ctx["staff_by_user"][recipient_uid]
        task_id = uuid.uuid4()
        ctx["aggs"].add(str(task_id))
        # 无 delegation_batch_id 的 submitted 事件 → 逐事件通知（recipient=reviewer）
        oid = uuid.uuid4()
        payload = {
            "event_type": "submitted", "task_id": str(task_id),
            "project_id": str(ctx["pid"]),
            "assignee_staff_id": None, "reviewer_staff_id": str(staff_id),
        }
        async with ctx["factory"]() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO task_events "
                    "(id, project_id, event_type, payload, status, retry_count, max_retries, "
                    " trace_id, created_at, aggregate_type, aggregate_id, aggregate_version, "
                    " idempotency_key, available_at) "
                    "VALUES (:id, :pid, :et, CAST(:pl AS jsonb), 'queued', 0, 3, :tr, now(), "
                    " :agg, :aid, 1, :idem, now())"
                ),
                {
                    "id": oid, "pid": ctx["pid"], "et": "procedure_task.submitted",
                    "pl": json.dumps(payload), "tr": str(oid)[:64], "agg": _AGG,
                    "aid": task_id, "idem": f"{task_id}:submitted:1",
                },
            )
            await s.commit()

        dispatcher = _dispatcher(ctx)
        await dispatcher.run_once()
        async with ctx["factory"]() as s:
            cnt = (
                await s.execute(
                    sa.text("SELECT count(*) FROM notifications WHERE event_id LIKE :p"),
                    {"p": f"{task_id}:%"},
                )
            ).scalar()
        assert cnt == 1, "非批量事件回退逐事件通知（message_type=procedure_task.submitted）"
