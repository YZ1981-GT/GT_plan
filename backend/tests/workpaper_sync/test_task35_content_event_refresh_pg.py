# -*- coding: utf-8 -*-
"""Task 35 真实 PostgreSQL 守卫：content event 的提交边界、重放幂等与"零新 revision"。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 35
Requirements: 11.9, 13.1, 13.2, 13.3, 13.4
Properties: P52（rollback 无事件 / commit 后恰一个完整 payload 事件 / 重放不重复副作用）
            P53（真实总线派发出的 typed event 与 outbox 行逐项相等）
            P54（派发失败落 failed/pending 并可重放成功，不静默丢失）

═══ 为什么必须真库 ═══

Task 35 正文有一条无法用 mock 证明的承诺："event/刷新失败……**不产生新 revision**"。
它的判据是 ``working_paper.content_revision`` 在**整条事件链**（入队 → 提交 → 发布 →
失败 → 重放 → 再发布）前后一个数都没动。mock session 里没有行、没有事务、也没有
``UPDATE``，这条断言必然空转。同理：

* "rollback 时无事件"要求入队在调用方事务内、发布在其之外 —— 回滚这件事只有真库才有；
* "恰一个事件"靠 ``import_event_outbox.status`` 的单向迁移（PG enum）；
* "重复投递不重复副作用"就是 ``import_event_consumptions`` 的**唯一索引**；
* "失败可重放"要求行能被 ``replay_pending`` 的 ``FOR UPDATE SKIP LOCKED`` 重新选出。

═══ 隔离与采集 ═══

scratch schema（``tmp_task35_content_event_*``），``search_path`` 只含它；四张事件表由
**ORM metadata** 建（不手抄 DDL）；结束 ``DROP SCHEMA CASCADE``。``DATABASE_URL`` 非
PostgreSQL 时**直接失败不 skip**。全部场景由**一次 ``asyncio.run``** 跑完并落进快照 ——
每个测试各自开 async 会污染共享连接池（第二个起 ``NoneType has no attribute send``）。
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"

if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

if str(Path(__file__).parent) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).parent))

_SCHEMA_PREFIX = "tmp_task35_content_event_"

_STUB_DDL = """
CREATE TABLE projects (id UUID PRIMARY KEY, name VARCHAR(200) NOT NULL DEFAULT 'stub');
CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(100) NOT NULL DEFAULT 'stub');
"""

#: V065 给 enum 加过 'processing'，Python 侧 ``OutboxStatus`` 只有三个成员。
_EXTRA_ENUM_LABELS = {"import_event_outbox_status": ("processing",)}


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _fk_free_copy(table: sa.Table) -> sa.Table:
    """同列、同类型、无外键、无索引的 scratch 表定义（列必须从 ORM 派生）。"""
    return sa.Table(
        table.name,
        sa.MetaData(),
        *[
            sa.Column(
                column.name,
                column.type,
                primary_key=column.primary_key,
                nullable=column.nullable,
                server_default=column.server_default,
            )
            for column in table.columns
        ],
    )


def _enum_ddl(tables: list[sa.Table]) -> list[str]:
    seen: dict[str, tuple[str, ...]] = {}
    for table in tables:
        for column in table.columns:
            if isinstance(column.type, sa.Enum) and column.type.name:
                labels = tuple(column.type.enums) + _EXTRA_ENUM_LABELS.get(column.type.name, ())
                seen.setdefault(column.type.name, labels)
    return [
        "CREATE TYPE {name} AS ENUM ({labels})".format(
            name=name, labels=", ".join(f"'{label}'" for label in labels)
        )
        for name, labels in sorted(seen.items())
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部跨事务场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.models.audit_platform_schemas import EventPayload, EventType
    from app.models.core import Log
    from app.models.dataset_models import (
        EventOutboxDLQ,
        ImportEventConsumption,
        ImportEventOutbox,
    )
    from app.models.workpaper_models import WorkingPaper
    from app.services import event_bus as event_bus_module
    from app.services.workpaper_sync.content_events import (
        content_update_dedupe_key,
        replay_entry_projection,
    )
    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    from test_task35_content_event_refresh import _standard_payload  # noqa: PLC0415

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 35 的 P52/P54 与『零新 revision』判据是跨事务可见性与行状态迁移，"
            f"必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "rollback": {},
        "commit_then_publish": {},
        "replay_is_noop": {},
        "dispatch_failure_then_replay": {},
        "sse_envelope": {},
    }
    engine = None

    # 真实订阅一个收集器，而不是 patch publish —— 判据是"事件真的被派发了几次"。
    captured: list[EventPayload] = []

    async def _collector(payload: EventPayload) -> None:
        captured.append(payload)

    bus = event_bus_module.event_bus
    bus.subscribe(EventType.WORKPAPER_CONTENT_UPDATED, _collector)
    previous_redis_flag = bus._redis_available
    bus._redis_available = False  # 不让 xadd 抖动引入随机失败

    async def _flaky(payload):
        _flaky.calls += 1
        raise RuntimeError("injected dispatch outage")

    _flaky.calls = 0

    def _inject_dispatch_failure() -> None:
        bus.publish_immediate = _flaky

    def _restore_dispatch() -> None:
        # 删实例属性而不是回写绑定方法：回写会在实例上留一个属性，
        # 后续变异检验读到的形态就和生产不一样了。
        bus.__dict__.pop("publish_immediate", None)

    async def _outbox_rows(session) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                sa.select(ImportEventOutbox).order_by(ImportEventOutbox.created_at)
            )
        ).scalars().all()
        return [
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "payload": dict(row.payload or {}),
                "status": row.status.value,
                "attempt_count": int(row.attempt_count or 0),
                "published_at_set": row.published_at is not None,
                "last_error_present": bool(row.last_error),
            }
            for row in rows
        ]

    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

        engine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        Session = async_sessionmaker(engine, expire_on_commit=False)

        orm_tables = [
            Log.__table__,
            ImportEventOutbox.__table__,
            EventOutboxDLQ.__table__,
            ImportEventConsumption.__table__,
        ]
        wp_table = _fk_free_copy(WorkingPaper.__table__)
        async with engine.begin() as conn:
            for stmt in [s.strip() for s in _STUB_DDL.strip().split(";") if s.strip()]:
                await conn.exec_driver_sql(stmt)
            for stmt in _enum_ddl(orm_tables + [WorkingPaper.__table__]):
                await conn.exec_driver_sql(stmt)
            await conn.run_sync(
                lambda sync_conn: ImportEventOutbox.metadata.create_all(
                    sync_conn, tables=orm_tables, checkfirst=True
                )
            )
            await conn.run_sync(
                lambda sync_conn: wp_table.metadata.create_all(sync_conn, checkfirst=True)
            )

        project = uuid.uuid4()
        user = uuid.uuid4()
        wp_id = uuid.uuid4()
        source_type_label = WorkingPaper.__table__.c.source_type.type.enums[0]
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{user}')")
            await conn.exec_driver_sql(
                "INSERT INTO working_paper "
                "(id, project_id, wp_index_id, file_path, source_type, file_version, "
                "content_revision) "
                f"VALUES ('{wp_id}', '{project}', '{uuid.uuid4()}', 'stub.xlsx', "
                f"'{source_type_label}', 4, 12)"
            )

        async def _revision(session) -> int:
            return int(
                (
                    await session.execute(
                        sa.select(WorkingPaper.content_revision).where(WorkingPaper.id == wp_id)
                    )
                ).scalar_one()
            )

        def _payload(revision: int) -> dict[str, Any]:
            """一份真实的 content event payload，只把身份对齐到本 scratch 行。"""
            payload = _standard_payload()
            payload["wp_id"] = str(wp_id)
            payload["project_id"] = str(project)
            payload["revision"] = revision
            return payload

        # ── 场景 A：入队后回滚 → 无耐久行、无事件（Property 52 前半）────────────
        captured.clear()
        async with Session() as db:
            handle = await DurableEventOutboxService.enqueue(
                db,
                event_type=EventType.WORKPAPER_CONTENT_UPDATED,
                project_id=project,
                year=2025,
                payload=_payload(13),
            )
            inside = len(await _outbox_rows(db))
            await db.rollback()
            report = await DurableEventOutboxService.publish_pending(db, [handle])
            async with Session() as verify:
                rows = await _outbox_rows(verify)
                revision_after = await _revision(verify)
        snap["rollback"] = {
            "visible_inside_transaction": inside,
            "outbox_rows_after_rollback": len(rows),
            "events_dispatched": len(captured),
            "report": report.as_dict(),
            "content_revision": revision_after,
        }

        # ── 场景 B：提交后发布 → 恰一个完整 payload 事件（Property 52 后半 / P53）──
        captured.clear()
        published_payload = _payload(13)
        async with Session() as db:
            revision_before_commit = await _revision(db)
            handle = await DurableEventOutboxService.enqueue(
                db,
                event_type=EventType.WORKPAPER_CONTENT_UPDATED,
                project_id=project,
                year=2025,
                payload=published_payload,
            )
            events_before_commit = len(captured)
            await db.commit()
            events_after_commit_before_publish = len(captured)
            report = await DurableEventOutboxService.publish_pending(db)
            remembered_after = len(DurableEventOutboxService.remembered(db))
        async with Session() as verify:
            rows = await _outbox_rows(verify)
            revision_after_publish = await _revision(verify)
        row = rows[0] if len(rows) == 1 else {}
        dispatched = [
            {
                "event_type": item.event_type.value,
                "project_id": str(item.project_id),
                "year": item.year,
                "extra": dict(item.extra),
            }
            for item in captured
        ]
        snap["commit_then_publish"] = {
            "events_before_commit": events_before_commit,
            "events_after_commit_before_publish": events_after_commit_before_publish,
            "outbox_rows": len(rows),
            "row": row,
            "report": report.as_dict(),
            "remembered_after_publish": remembered_after,
            "dispatched": dispatched,
            "enqueued_payload": published_payload,
            "revision_before_commit": revision_before_commit,
            "revision_after_publish": revision_after_publish,
            "dedupe_key_from_dispatched": (
                content_update_dedupe_key({"extra": dispatched[0]["extra"]})
                if dispatched
                else None
            ),
        }
        published_outbox_id = uuid.UUID(row["id"]) if row else None

        # ── 场景 C：重复发布 / worker 重放不再派发第二次（Property 52 幂等）──────
        #
        # 🔴 必须先把行**打回 failed**，否则 `replay_pending` 一条都选不到，
        # "重放不重复副作用"这条判据就跑在一个空集上（永久 GREEN）。打回 failed 是真实
        # 形态：发布状态那次 commit 失败、进程被 kill、或 worker 抢到一条上一轮标错的行。
        async with Session() as db:
            explicit = await DurableEventOutboxService.publish_pending(db, [handle])
            await db.commit()
        async with Session() as forced:
            await forced.execute(
                sa.update(ImportEventOutbox)
                .where(ImportEventOutbox.id == published_outbox_id)
                .values(status="failed", published_at=None, last_error="forced back for replay")
            )
            await forced.commit()
        async with Session() as db:
            worker = await DurableEventOutboxService.replay_pending(db, limit=50)
            await db.commit()
        async with Session() as verify:
            rows_after_replay = await _outbox_rows(verify)
            revision_after_replay = await _revision(verify)
        snap["replay_is_noop"] = {
            "explicit_report": explicit.as_dict(),
            "worker_read_count": worker["read_count"],
            "worker_published_count": worker["published_count"],
            "worker_deduplicated_fanout_count": worker["deduplicated_fanout_count"],
            "events_total_after_all": len(captured),
            "rows": rows_after_replay,
            "content_revision": revision_after_replay,
        }

        async with Session() as verify:
            consumptions = (
                await verify.execute(sa.select(ImportEventConsumption))
            ).scalars().all()
        snap["replay_is_noop"]["consumption_rows"] = [
            {"event_id": item.event_id, "handler_name": item.handler_name}
            for item in consumptions
        ]
        snap["replay_is_noop"]["published_outbox_id"] = (
            str(published_outbox_id) if published_outbox_id else None
        )

        # ── 场景 D：派发失败 → failed 可重放成功（Property 54）────────────────
        captured.clear()
        _flaky.calls = 0
        raised_to_caller = None
        async with Session() as db:
            revision_before_failure = await _revision(db)
            await DurableEventOutboxService.enqueue(
                db,
                event_type=EventType.WORKPAPER_CONTENT_UPDATED,
                project_id=project,
                year=2025,
                payload=_payload(14),
            )
            await db.commit()
            _inject_dispatch_failure()
            try:
                failed_report = await DurableEventOutboxService.publish_pending(db)
            except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言"不该抛"
                raised_to_caller = type(exc).__name__
                failed_report = None
            finally:
                _restore_dispatch()
            async with Session() as verify:
                not_published = [
                    item for item in await _outbox_rows(verify) if item["status"] != "published"
                ]
                revision_after_failure = await _revision(verify)
            replay_report = await DurableEventOutboxService.replay_pending(db, limit=50)
            await db.commit()
        async with Session() as verify:
            rows_final = await _outbox_rows(verify)
            revision_final = await _revision(verify)
            dlq_count = int(
                (
                    await verify.execute(sa.select(sa.func.count()).select_from(EventOutboxDLQ))
                ).scalar_one()
                or 0
            )
        snap["dispatch_failure_then_replay"] = {
            "raised_to_caller": raised_to_caller,
            "failed_report": failed_report.as_dict() if failed_report else None,
            "injected_calls": _flaky.calls,
            "rows_not_published_after_failure": not_published,
            "replay_report": {
                "read_count": replay_report["read_count"],
                "published_count": replay_report["published_count"],
                "failed_count": replay_report["failed_count"],
                "deduplicated_fanout_count": replay_report["deduplicated_fanout_count"],
            },
            "rows_final": rows_final,
            "dlq_count": dlq_count,
            "events_dispatched_after_replay": len(captured),
            "revision_before_failure": revision_before_failure,
            "revision_after_failure": revision_after_failure,
            "revision_final": revision_final,
        }

        # ── 场景 E：真实派发出来的 typed event 走 Stream 序列化 → replay 投影 ────
        stream_payload = snap["commit_then_publish"]["dispatched"][0]["extra"]
        rebuilt = EventPayload(
            event_type=EventType.WORKPAPER_CONTENT_UPDATED,
            project_id=project,
            year=2025,
            extra=dict(stream_payload),
        )
        item = replay_entry_projection(
            "1755300000000-0",
            {"payload_json": event_bus_module.serialize_payload_for_stream(rebuilt)},
        )
        snap["sse_envelope"] = {
            "replay_item": item,
            "dedupe_key": content_update_dedupe_key(item) if item else None,
        }
        return snap
    finally:
        try:
            if EventType.WORKPAPER_CONTENT_UPDATED in bus._handlers:
                bus._handlers[EventType.WORKPAPER_CONTENT_UPDATED] = [
                    handler
                    for handler in bus._handlers[EventType.WORKPAPER_CONTENT_UPDATED]
                    if handler is not _collector
                ]
            bus._redis_available = previous_redis_flag
            _restore_dispatch()
        finally:
            if engine is not None:
                await engine.dispose()
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.dispose()


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# Property 52：rollback 无事件 / commit 后恰一个完整事件 / 重放不重复副作用
# ═══════════════════════════════════════════════════════════════════════════


def test_rollback_leaves_no_durable_row_and_no_event(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.1**

    Property 52 前半：入队在调用方事务内 ⇒ 回滚后没有耐久事实，也就发不出事件。
    ``rolled_back`` 是这条的直接判据（发布阶段读不到行，因此不发、也不当失败重试）。
    """
    fact = snap["rollback"]
    assert fact["visible_inside_transaction"] == 1, "入队没有落在调用方事务里"
    assert fact["outbox_rows_after_rollback"] == 0, "回滚后仍有耐久行 ⇒ 入队自己 commit 了"
    assert fact["events_dispatched"] == 0, "回滚后仍派发了事件 ⇒ 下游按不存在的版本刷新"
    assert fact["report"]["published"] == 0
    assert fact["report"]["rolled_back"] == 1
    assert fact["report"]["failed"] == 0, "回滚不是失败：没有可发布的耐久事实"
    # 一次回滚不得动业务 revision
    assert fact["content_revision"] == 12


def test_no_event_before_commit_and_exactly_one_after_publish(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.1**

    Property 52 后半："commit 后恰有一个 payload 完整事件"。三个时点各自断言：
    commit 前 0、commit 后未发布仍 0、发布后恰 1。
    """
    fact = snap["commit_then_publish"]
    assert fact["events_before_commit"] == 0
    assert fact["events_after_commit_before_publish"] == 0, (
        "commit 本身不得派发事件 —— 发布必须是调用方在 commit 之后的显式动作"
    )
    assert fact["outbox_rows"] == 1
    assert fact["row"]["event_type"] == "workpaper.content.updated"
    assert fact["row"]["status"] == "published"
    assert fact["row"]["published_at_set"] is True
    assert fact["row"]["last_error_present"] is False
    assert fact["report"] == {
        "attempted": 1,
        "published": 1,
        "failed": 0,
        "already_published": 0,
        "rolled_back": 0,
        "last_error": None,
        "published_event_ids": [fact["row"]["id"]],
    }
    assert fact["remembered_after_publish"] == 0, "发布后待发布清单必须清空（否则会重发）"
    assert len(fact["dispatched"]) == 1


def test_republish_and_worker_replay_do_not_duplicate_side_effects(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 13.3**

    Property 52 末句"重放不重复副作用"。两条路径都试：显式重发 + worker 重放。
    """
    fact = snap["replay_is_noop"]
    # 路径一：显式重发同一个句柄 —— 已 published 的行只计数不重发
    assert fact["explicit_report"]["already_published"] == 1
    assert fact["explicit_report"]["published"] == 0
    # 路径二：worker 重放。行被打回 failed，因此**必须**真的被选到一条 ——
    # 选不到就说明这条判据跑在空集上（永久 GREEN）。
    assert fact["worker_read_count"] == 1, (
        f"worker 一条都没选到 ⇒ 判据跑在空集上：{fact}"
    )
    assert fact["worker_published_count"] == 1
    assert fact["worker_deduplicated_fanout_count"] == 1, (
        "重放没有命中 fan-out 闸门 ⇒ 整片副作用被跑了第二遍"
    )
    # 事件总数仍是 1（场景 B 派发的那一条）
    assert fact["events_total_after_all"] == 1, "重放又派发了一次 ⇒ 下游被刷两遍"
    assert [item["status"] for item in fact["rows"]] == ["published"]
    # fan-out 闸门留下的消费记录：一条耐久行一条
    keys = {(item["event_id"], item["handler_name"]) for item in fact["consumption_rows"]}
    assert (fact["published_outbox_id"], "workpaper_sync.durable_outbox.fanout@v1") in keys


def test_the_whole_event_chain_never_advances_content_revision(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 2.12, 13.3, 13.4**

    Task 35 正文："不产生新 revision"。判据是**真实调用后查库**：入队 → 提交 → 发布 →
    派发失败 → 重放成功，整条链走完 ``working_paper.content_revision`` 一个数都没动。

    🔴 这条不能靠"代码里没有 UPDATE"来证：revision 推进可以经 repository、经 helper、
    经另一个 service 发生。只有把数据库里那个数在链条前后各读一次才是判据。
    """
    assert snap["rollback"]["content_revision"] == 12
    commit = snap["commit_then_publish"]
    assert commit["revision_before_commit"] == 12
    assert commit["revision_after_publish"] == 12, "发布事件推进了业务 revision"
    assert snap["replay_is_noop"]["content_revision"] == 12, "重放推进了业务 revision"
    failure = snap["dispatch_failure_then_replay"]
    assert failure["revision_before_failure"] == 12
    assert failure["revision_after_failure"] == 12, "派发失败推进了业务 revision"
    assert failure["revision_final"] == 12, "失败后的重放推进了业务 revision"


# ═══════════════════════════════════════════════════════════════════════════
# Property 53：真实派发出的 typed event 与 outbox 行逐项相等
# ═══════════════════════════════════════════════════════════════════════════


def test_dispatched_typed_event_equals_the_outbox_row_item_by_item(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 13.2**

    Property 53：``Redis typed event 中 wp_id/revision/operation/source/adapter 与 outbox
    逐项相等``。这里比对的是**真实总线派发出来的** `EventPayload.extra` 与库里那行的
    `payload`，而不是两个都由测试自己造的字典。
    """
    fact = snap["commit_then_publish"]
    row_payload = fact["row"]["payload"]
    dispatched_extra = fact["dispatched"][0]["extra"]
    enqueued = fact["enqueued_payload"]

    # 库里那行 == 入队时给的那份（外加 publish 注入的耐久行 id）
    assert set(row_payload) == set(enqueued), "outbox 行的 payload 键集与入队时不同"
    for key, value in enqueued.items():
        assert row_payload[key] == value, f"outbox 行的 {key} 漂移"

    # 派发出去的 extra == 库里那行 + `__event_id`
    assert set(dispatched_extra) == set(row_payload) | {"__event_id"}
    for key, value in row_payload.items():
        assert dispatched_extra[key] == value, f"派发出去的 {key} 与 outbox 行不等"
    assert dispatched_extra["__event_id"] == fact["row"]["id"]

    # design 点名的六个业务字段逐项复核
    for key in ("wp_id", "revision", "operation_id", "source", "adapter_id", "file_sha256"):
        assert dispatched_extra[key] == enqueued[key]

    # AC 11.9 的去重键在真实派发结果上算得出来
    assert fact["dedupe_key_from_dispatched"] == f"{enqueued['wp_id']}|{enqueued['revision']}"


def test_stream_round_trip_of_the_real_dispatched_event(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.2**

    真实派发出来的那份 payload 走完 Stream 序列化 → 反序列化 → replay 投影后，
    ``extra`` 仍然逐键相等（断线补拉拿到的必须与 SSE 当时那条是同一份事实）。
    """
    item = snap["sse_envelope"]["replay_item"]
    assert item is not None
    dispatched_extra = snap["commit_then_publish"]["dispatched"][0]["extra"]
    assert item["event_type"] == "workpaper.content.updated"
    assert sorted(item["extra"]) == sorted(dispatched_extra)
    for key, value in dispatched_extra.items():
        assert item["extra"][key] == value, f"Stream 往返后 {key} 漂移"
    assert snap["sse_envelope"]["dedupe_key"] == (
        f"{dispatched_extra['wp_id']}|{dispatched_extra['revision']}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 54：派发失败落 failed 并可重放成功
# ═══════════════════════════════════════════════════════════════════════════


def test_dispatch_failure_lands_failed_and_is_replayable(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.4**

    Property 54：``after-save handler 注入失败后 outbox 为 failed/pending 并可重放成功，
    不静默丢失``。

    四条同时成立才算：①发布**不向上抛**（业务已提交，不能因为副作用失败而 500）
    ②行落 ``failed`` + ``attempt_count`` + ``last_error`` ③重放后落 ``published``
    ④重放真的派发了一次（不是只把状态改绿）。
    """
    fact = snap["dispatch_failure_then_replay"]
    assert fact["raised_to_caller"] is None, (
        "发布失败向上抛了 —— 业务已提交，异常会把一次成功的保存显示成失败"
    )
    assert fact["failed_report"]["failed"] == 1
    assert fact["failed_report"]["published"] == 0
    assert fact["injected_calls"] == 1, "注入的失败没有真的被调用 ⇒ 场景根本没跑到"

    not_published = fact["rows_not_published_after_failure"]
    assert len(not_published) == 1, not_published
    assert not_published[0]["status"] == "failed"
    assert not_published[0]["attempt_count"] >= 1
    assert not_published[0]["last_error_present"] is True, "失败没有留下 last_error ⇒ 不可诊断"

    assert fact["replay_report"]["published_count"] >= 1
    assert fact["replay_report"]["failed_count"] == 0
    assert [item["status"] for item in fact["rows_final"]] == ["published", "published"]
    assert fact["dlq_count"] == 0, "一次可重放的失败不该直接进 DLQ"
    # 重放真的派发了一次（失败那次没派发出去，所以总数恰好 1）
    assert fact["events_dispatched_after_replay"] == 1, (
        "重放没有真的派发 ⇒ 事件被静默丢失（只把行改成了 published）"
    )


def test_failed_row_keeps_the_full_payload_for_replay(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.2, 13.4**

    失败行的 payload 必须完整保留，否则重放出去的是一份缺字段的事件 —— 那等于
    "没有静默丢失"这句话只在行数上成立。
    """
    rows = snap["dispatch_failure_then_replay"]["rows_final"]
    replayed = rows[-1]["payload"]
    assert replayed["revision"] == 14
    for key in ("wp_id", "project_id", "operation_id", "source", "adapter_id", "file_sha256"):
        assert key in replayed, f"重放行的 payload 缺 {key}"
    assert replayed["content_revision_advanced"] is True
