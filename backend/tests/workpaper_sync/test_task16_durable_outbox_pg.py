# -*- coding: utf-8 -*-
"""Task 16 真实 PostgreSQL 守卫：耐久 outbox 的提交边界、可重放性与 handler 幂等。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 16
Requirements: 2.12, 13.1, 13.2, 13.3, 13.4
Properties: P52（outbox 仅 commit 后发布）/ P53（replay 保留完整 payload，DB 侧）/
            P54（after-save 失败可重试）

═══ 为什么必须真库 ═══

这三条 Property 的判据全部是**跨事务可见性**与**行状态迁移**，mock 一律观测不到：

* P52 的"事务 rollback 时无事件"要求"入队在调用方事务内、发布在其之外"。用 mock
  session 时"入队"只是往列表里 append，回滚这件事根本不存在，断言必然空转。
* P52 的"commit 后恰有一个事件"靠 ``import_event_outbox.status`` 的单向迁移保证幂等；
  status 是 PG enum，mock 不会拒绝非法值。
* P54 要求失败后行落 ``failed`` + ``attempt_count``，能被 ``replay_pending`` 的
  ``FOR UPDATE SKIP LOCKED`` 重新选出、耗尽后进 ``event_outbox_dlq``（真外键）。
* Requirement 13.3 的幂等闸门就是 ``import_event_consumptions`` 的**唯一索引**；没有
  真索引，``claim_consumption`` 第二次一样会"成功"。

═══ 隔离 ═══

scratch schema（``tmp_task16_outbox_*``），``search_path`` 只含它（不含 public），
``projects/users/working_paper`` 建桩表，四张事件/日志表由 **ORM metadata** 建（不手抄
DDL —— 手抄一份就是第二真源，列改名时守卫会假绿）。结束 ``DROP SCHEMA CASCADE``。
``DATABASE_URL`` 非 PostgreSQL 时**直接失败不 skip**。

═══ 采集写法 ═══

全部场景由**一次 ``asyncio.run``** 跑完并落进快照（module fixture）。不给每个测试各自
开 async —— 共享连接池会被污染，第二个测试起 ``NoneType has no attribute send``。
校验读一律走 **ORM select**：``exec_driver_sql`` 拿 PG enum / jsonb 时由 asyncpg 直接
返回 str，类型形态取决于驱动而不是模型，断言会建立在不稳定的表象上。
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

_SCHEMA_PREFIX = "tmp_task16_outbox_"

_STUB_DDL = """
CREATE TABLE projects (id UUID PRIMARY KEY, name VARCHAR(200) NOT NULL DEFAULT 'stub');
CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(100) NOT NULL DEFAULT 'stub');
"""

#: V065 给 enum 加过 'processing'，Python 侧 ``OutboxStatus`` 只有三个成员。守卫不能跑
#: 在一个比生产更窄的类型上，所以按真实数据库形态补齐这一个标签。
_EXTRA_ENUM_LABELS = {"import_event_outbox_status": ("processing",)}


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _fk_free_copy(table: sa.Table) -> sa.Table:
    """把 ORM 表复制成"同列、同类型、无外键、无索引"的 scratch 表定义。

    ``working_paper`` 的外键指向 ``wp_index`` / ``ledger_datasets`` / ``users`` 一整片
    图，全建出来等于把半个 schema 搬进 scratch。但列**必须**从 ORM 派生：手抄一份
    DDL 就是第二真源，模型加列时守卫只会莫名 error 或悄悄跑在旧形状上。
    """
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
    """为 ``create_type=False`` 的 PG enum 列派生 ``CREATE TYPE`` 语句（去重）。"""
    seen: dict[str, tuple[str, ...]] = {}
    for table in tables:
        for column in table.columns:
            if isinstance(column.type, sa.Enum) and column.type.name:
                labels = tuple(column.type.enums) + _EXTRA_ENUM_LABELS.get(
                    column.type.name, ()
                )
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
        OutboxStatus,
    )
    from app.models.workpaper_models import WorkingPaper
    from app.services import event_bus as event_bus_module
    from app.services.workpaper_save_orchestrator import (
        SIDE_EFFECT_HANDLER_NAME,
        SIDE_EFFECT_HANDLER_VERSION,
        orchestrator,
    )
    from app.services.workpaper_sync.outbox import (
        EVENT_ID_PAYLOAD_KEY,
        FANOUT_HANDLER_NAME,
        FANOUT_HANDLER_VERSION,
        PENDING_SESSION_KEY,
        DurableEventOutboxService,
        DurableOutboxError,
        PendingPublication,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 16 的 P52/P54 判据是跨事务可见性与行状态迁移，必须真实 PostgreSQL；"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "server_version": None,
        "handler_name": SIDE_EFFECT_HANDLER_NAME,
        "handler_version": SIDE_EFFECT_HANDLER_VERSION,
        "same_transaction": {},
        "rollback": {},
        "commit_then_publish": {},
        "republish_is_noop": {},
        "publish_failure_then_replay": {},
        "dlq_escalation": {},
        "consumption_idempotency": {},
        "missing_project_id": {},
        "stream_roundtrip": {},
    }
    engine = None
    # 捕获真实 event_bus 派发到的 payload。订阅自己的收集器而不是 patch publish —— 判
    # 据是"事件真的被派发了几次"，patch 掉发布函数只能证明"函数被调用"。
    captured: list[EventPayload] = []

    async def _collector(payload: EventPayload) -> None:
        captured.append(payload)

    # 导入域事件的收集器：场景 L 用它证明 fan-out 闸门**没有**扩张到 ledger-import 的
    # 重放语义上（那边归 ledger-import spec，Task 16 不改它的行为）。
    ledger_captured: list[EventPayload] = []

    async def _ledger_collector(payload: EventPayload) -> None:
        ledger_captured.append(payload)

    bus = event_bus_module.event_bus
    bus.subscribe(EventType.WORKPAPER_SAVED, _collector)
    bus.subscribe(EventType.LEDGER_DATASET_ACTIVATED, _ledger_collector)
    # Redis 不参与本文件判定（P53 的 Stream 形态在下面用纯函数直接判）：置 False 让
    # _persist_to_stream 立刻返回，避免 xadd 抖动引入随机失败。
    previous_redis_flag = bus._redis_available
    bus._redis_available = False

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
                "project_id": str(row.project_id),
                "year": row.year,
                "payload": dict(row.payload or {}),
                "status": row.status.value,
                "attempt_count": int(row.attempt_count or 0),
                "published_at_set": row.published_at is not None,
                "last_error_present": bool(row.last_error),
            }
            for row in rows
        ]

    async def _flaky(payload):
        _flaky.calls += 1
        raise RuntimeError("injected redis outage")

    _flaky.calls = 0

    def _inject_publish_failure() -> None:
        bus.publish_immediate = _flaky

    def _restore_publish() -> None:
        # 删实例属性而不是回写绑定方法：回写会在实例上留一个属性，后续 patch 检测/
        # 变异检验读到的形态就和生产不一样了。
        bus.__dict__.pop("publish_immediate", None)

    try:
        async with admin.connect() as conn:
            snap["server_version"] = (
                await conn.exec_driver_sql("SELECT version()")
            ).scalar_one()
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
        # source_type / wp_index_id / file_path 是 NOT NULL 无默认；枚举字面量从 ORM 取，
        # 不写死在测试里。
        source_type_label = WorkingPaper.__table__.c.source_type.type.enums[0]
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{user}')")
            await conn.exec_driver_sql(
                "INSERT INTO working_paper "
                "(id, project_id, wp_index_id, file_path, source_type, file_version) "
                f"VALUES ('{wp_id}', '{project}', '{uuid.uuid4()}', 'stub.xlsx', "
                f"'{source_type_label}', 4)"
            )

        class _User:
            id = user

        async def _load_wp(session):
            return (
                await session.execute(
                    sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
                )
            ).scalar_one()

        # ── 场景 A：同事务可见性（Requirement 13.1 前半）────────────────────────
        async with Session() as db:
            wp = await _load_wp(db)
            await orchestrator.after_save(
                db, wp, _User(), trigger="html_save",
                extra={"sheet_name": "Sheet1", "year": 2025},
            )
            inside = len(await _outbox_rows(db))
            async with Session() as other:  # 独立事务：未提交的行对它不可见
                outside = len(await _outbox_rows(other))
            snap["same_transaction"] = {
                "visible_inside_same_transaction": inside,
                "visible_to_other_transaction": outside,
                "remembered_count": len(DurableEventOutboxService.remembered(db)),
                "session_info_key_present": PENDING_SESSION_KEY in db.info,
                "events_dispatched_before_commit": len(captured),
            }
            await db.rollback()

        # ── 场景 B：回滚 → 无耐久行、无事件（Property 52 前半）────────────────
        captured.clear()
        async with Session() as db:
            wp = await _load_wp(db)
            await orchestrator.after_save(
                db, wp, _User(), trigger="html_save", extra={"year": 2025}
            )
            handles = list(DurableEventOutboxService.remembered(db))
            await db.rollback()
            report = await DurableEventOutboxService.publish_pending(db, handles)
            async with Session() as verify:
                rows = await _outbox_rows(verify)
                logs = len(
                    (await verify.execute(sa.select(Log))).scalars().all()
                )
                version = (await _load_wp(verify)).file_version
            snap["rollback"] = {
                "outbox_rows": len(rows),
                "log_rows": logs,
                "file_version": version,
                "events_dispatched": len(captured),
                "report": report.as_dict(),
            }

        # ── 场景 C：提交后发布 → 恰一个完整 payload 事件（Property 52 后半）────
        captured.clear()
        async with Session() as db:
            wp = await _load_wp(db)
            await orchestrator.after_save(
                db, wp, _User(), trigger="univer_save",
                extra={"content_hash": "a" * 64, "sheets": 3, "cells": 42, "year": 2025},
                # 🔴 Task 18：handler 不再自己算版本，业务 revision 由调用方（本次业务
                #    提交的所有者 `ContentMutationService`）算好传进来，handler 只读。
                content_revision=5,
            )
            events_before_commit = len(captured)
            await db.commit()
            events_after_commit_before_publish = len(captured)
            report = await DurableEventOutboxService.publish_pending(db)
            remembered_after = len(DurableEventOutboxService.remembered(db))

        async with Session() as verify:
            rows = await _outbox_rows(verify)
            log_rows = (await verify.execute(sa.select(Log))).scalars().all()
        first = rows[0] if len(rows) == 1 else {}
        snap["commit_then_publish"] = {
            "events_before_commit": events_before_commit,
            "events_after_commit_before_publish": events_after_commit_before_publish,
            "outbox_rows": len(rows),
            "row": first,
            "report": report.as_dict(),
            "remembered_after_publish": remembered_after,
            "dispatched": [
                {
                    "event_type": item.event_type.value,
                    "project_id": str(item.project_id),
                    "year": item.year,
                    "extra": dict(item.extra),
                }
                for item in captured
            ],
            "log_action_types": [row.action_type for row in log_rows],
            "log_new_values": [dict(row.new_value or {}) for row in log_rows],
            "event_id_payload_key": EVENT_ID_PAYLOAD_KEY,
        }
        published_outbox_id = uuid.UUID(first["id"]) if first else None

        # ── 场景 D：重复发布 / worker 重放不再派发第二次（Property 52 幂等）────
        async with Session() as db:
            empty_call = await DurableEventOutboxService.publish_pending(db)
            explicit = await DurableEventOutboxService.publish_pending(
                db,
                [
                    PendingPublication(
                        outbox_id=published_outbox_id,
                        event_type=EventType.WORKPAPER_SAVED,
                        project_id=project,
                        year=2025,
                    )
                ],
            )
            worker = await DurableEventOutboxService.replay_pending(db, limit=50)
            await db.commit()
        snap["republish_is_noop"] = {
            "empty_call": empty_call.as_dict(),
            "explicit_call": explicit.as_dict(),
            "worker_read_count": worker["read_count"],
            "worker_published_count": worker["published_count"],
            "events_total_after_all": len(captured),
        }

        # ── 场景 E：发布失败 → failed 可重放（Property 54）────────────────────
        captured.clear()
        _flaky.calls = 0
        raised_to_caller = None
        async with Session() as db:
            wp = await _load_wp(db)
            await orchestrator.after_save(
                db, wp, _User(), trigger="onlyoffice_callback",
                extra={"doc_key": "k1", "year": 2025},
                content_revision=6,
            )
            await db.commit()
            _inject_publish_failure()
            try:
                failed_report = await DurableEventOutboxService.publish_pending(db)
            except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言"不该抛"
                raised_to_caller = type(exc).__name__
                failed_report = None
            finally:
                _restore_publish()
            async with Session() as verify:
                after_failure = [
                    row for row in await _outbox_rows(verify) if row["status"] != "published"
                ]
            replay_report = await DurableEventOutboxService.replay_pending(db, limit=50)
            await db.commit()
            async with Session() as verify:
                after_replay = await _outbox_rows(verify)
                version_now = (await _load_wp(verify)).file_version
        snap["publish_failure_then_replay"] = {
            "raised_to_caller": raised_to_caller,
            "failed_report": failed_report.as_dict() if failed_report else None,
            "rows_not_published_after_failure": after_failure,
            "replay_report": {
                "read_count": replay_report["read_count"],
                "published_count": replay_report["published_count"],
                "failed_count": replay_report["failed_count"],
            },
            "statuses_after_replay": [row["status"] for row in after_replay],
            "events_dispatched": len(captured),
            "injected_failures": _flaky.calls,
            "file_version_after_replay": version_now,
        }

        # ── 场景 F：持续失败 → DLQ（Requirement 13.4 的 "进 DLQ" 分支）────────
        async with Session() as db:
            wp = await _load_wp(db)
            await orchestrator.after_save(
                db, wp, _User(), trigger="custom_query_writeback", extra={"year": 2025}
            )
            await db.commit()
            _inject_publish_failure()
            try:
                exhausted = await DurableEventOutboxService.replay_pending(
                    db, limit=50, max_attempts=1
                )
            finally:
                _restore_publish()
            await db.commit()
            async with Session() as verify:
                dlq = (
                    await verify.execute(sa.select(EventOutboxDLQ))
                ).scalars().all()
        snap["dlq_escalation"] = {
            "moved_to_dlq_count": exhausted.get("moved_to_dlq_count", 0),
            "dlq_rows": [
                {
                    "event_type": row.event_type,
                    "attempt_count": int(row.attempt_count or 0),
                    "failure_reason_present": bool(row.failure_reason),
                    "original_event_id_present": row.original_event_id is not None,
                    "payload_wp_id_present": bool((row.payload or {}).get("wp_id")),
                }
                for row in dlq
            ],
        }

        # ── 场景 G：handler 幂等闸门（Requirement 13.3）────────────────────────
        async with Session() as db:
            event_id = str(uuid.uuid4())
            other_event_id = str(uuid.uuid4())
            first_claim = await DurableEventOutboxService.claim_consumption(
                db, event_id=event_id, handler_name=SIDE_EFFECT_HANDLER_NAME,
                handler_version=SIDE_EFFECT_HANDLER_VERSION, project_id=project, year=2025,
            )
            second_claim = await DurableEventOutboxService.claim_consumption(
                db, event_id=event_id, handler_name=SIDE_EFFECT_HANDLER_NAME,
                handler_version=SIDE_EFFECT_HANDLER_VERSION, project_id=project, year=2025,
            )
            bumped_version_claim = await DurableEventOutboxService.claim_consumption(
                db, event_id=event_id, handler_name=SIDE_EFFECT_HANDLER_NAME,
                handler_version=SIDE_EFFECT_HANDLER_VERSION + 1,
                project_id=project, year=2025,
            )
            other_event_claim = await DurableEventOutboxService.claim_consumption(
                db, event_id=other_event_id, handler_name=SIDE_EFFECT_HANDLER_NAME,
                handler_version=SIDE_EFFECT_HANDLER_VERSION,
                project_id=project, year=2025,
            )
            await db.commit()
            async with Session() as verify:
                # 只取本场景手工塞的那两个 event_id：场景 C/E/F 的真实发布也会留下
                # fan-out 消费行（Requirement 13.3 的派发口记账），把它们混进来会让
                # 这条断言变成"总行数"判据 —— 与 handler 版本语义无关且互相耦合。
                keys = sorted(
                    row.handler_name
                    for row in (
                        await verify.execute(
                            sa.select(ImportEventConsumption).where(
                                ImportEventConsumption.event_id.in_(
                                    [event_id, other_event_id]
                                )
                            )
                        )
                    ).scalars().all()
                )
        snap["consumption_idempotency"] = {
            "first_claim": first_claim,
            "second_claim": second_claim,
            "bumped_version_claim": bumped_version_claim,
            "other_event_claim": other_event_claim,
            "handler_keys": keys,
        }

        # ── 场景 H：缺 project_id → fail closed（不再吞成 warning）──────────────
        async with Session() as db:
            wp = await _load_wp(db)
            wp.project_id = None
            raised = None
            try:
                await orchestrator.after_save(
                    db, wp, _User(), trigger="html_save", extra={"year": 2025}
                )
            except Exception as exc:  # noqa: BLE001 - 记录类型供守卫断言
                raised = type(exc).__name__
            await db.rollback()
            snap["missing_project_id"] = {
                "raised": raised,
                "expected": DurableOutboxError.__name__,
            }

        # ── 场景 J/K/L 前置：把前面场景留下的行收敛掉 ──────────────────────────
        # E/F 各留了一条 failed 行（F 那条还进了 DLQ）。`replay_pending` 选的正是
        # pending/failed，不收敛的话下面三个场景的"派发了几次"会被它们污染。DLQ 有 FK
        # 指向 outbox，所以是置 published 而不是删行；consumption 行必须清空 —— 场景 G
        # 手工塞过同名 handler 的记录。
        async with Session() as db:
            await db.execute(
                sa.update(ImportEventOutbox).values(status=OutboxStatus.published)
            )
            await db.execute(sa.delete(ImportEventConsumption))
            await db.commit()

        fanout_key = DurableEventOutboxService.handler_key(
            FANOUT_HANDLER_NAME, FANOUT_HANDLER_VERSION
        )

        async def _force_failed(outbox_id: uuid.UUID) -> None:
            """把行打回 ``failed``：模拟"副作用已派发、但后续步骤失败"的重放场景。

            这是真实形态 —— 发布状态那次 commit 失败、进程被 kill、或 worker 抢到一条
            上一轮标错的行。旧实现在这种重放里会把整片 handler 再跑一遍。
            """
            async with Session() as session:
                await session.execute(
                    sa.update(ImportEventOutbox)
                    .where(ImportEventOutbox.id == outbox_id)
                    .values(
                        status=OutboxStatus.failed,
                        published_at=None,
                        last_error="forced back to failed for replay",
                    )
                )
                await session.commit()

        async def _consumption_keys(session, only: uuid.UUID | None = None) -> list[str]:
            """``event_id|handler@vN`` 清单；``only`` 限定到某一条耐久事件。

            必须能限定：J/K/L 三个场景共用一张表，用"全表"当判据会让 K 读到 J 留下的
            那一行（首轮实测就是这么红的），断言从"这条事件的派发权还在不在"退化成
            "表里有没有行"。
            """
            stmt = sa.select(
                ImportEventConsumption.event_id,
                ImportEventConsumption.handler_name,
            )
            if only is not None:
                stmt = stmt.where(ImportEventConsumption.event_id == str(only))
            rows = (await session.execute(stmt)).all()
            return sorted(f"{event_id}|{handler}" for event_id, handler in rows)

        async def _status_of(session, outbox_id: uuid.UUID) -> str:
            row = (
                await session.execute(
                    sa.select(ImportEventOutbox).where(ImportEventOutbox.id == outbox_id)
                )
            ).scalar_one()
            return row.status.value

        # ── 场景 J：fan-out at-most-once（Requirement 13.3）───────────────────
        captured.clear()
        async with Session() as db:
            handle_j = await DurableEventOutboxService.enqueue(
                db,
                event_type=EventType.WORKPAPER_SAVED,
                project_id=project,
                year=2025,
                payload={"wp_id": str(wp_id), "trigger": "html_save"},
            )
            await db.commit()
            first_publish = await DurableEventOutboxService.publish_pending(db)
        dispatched_after_first = len(captured)
        async with Session() as verify:
            keys_after_first = await _consumption_keys(verify, handle_j.outbox_id)

        await _force_failed(handle_j.outbox_id)
        async with Session() as db:
            worker_j = await DurableEventOutboxService.replay_pending(db, limit=50)
            await db.commit()
        async with Session() as verify:
            snap["fanout_at_most_once"] = {
                "fanout_key": fanout_key,
                "outbox_id": str(handle_j.outbox_id),
                "first_publish": first_publish.as_dict(),
                "dispatched_after_first": dispatched_after_first,
                "keys_after_first": keys_after_first,
                "worker_read_count": worker_j["read_count"],
                "worker_published_count": worker_j["published_count"],
                "worker_deduplicated": worker_j.get("deduplicated_fanout_count"),
                "worker_failed_count": worker_j["failed_count"],
                "dispatched_after_replay": len(captured),
                "status_after_replay": await _status_of(verify, handle_j.outbox_id),
                "keys_after_replay": await _consumption_keys(verify, handle_j.outbox_id),
            }

        # ── 场景 K：派发失败必须归还派发权（Property 54 与闸门不能互相打架）────
        captured.clear()
        _flaky.calls = 0
        async with Session() as db:
            handle_k = await DurableEventOutboxService.enqueue(
                db,
                event_type=EventType.WORKPAPER_SAVED,
                project_id=project,
                year=2025,
                payload={"wp_id": str(wp_id), "trigger": "onlyoffice_callback"},
            )
            await db.commit()
            _inject_publish_failure()
            try:
                failed_publish = await DurableEventOutboxService.publish_pending(db)
            finally:
                _restore_publish()
        # 🔴 派发次数必须在**这一刻**取值：下面的 worker 重放会把 captured 推到 1，
        # 若等到组装快照时再读 len(captured)，"失败时零派发"与"重放后一次派发"会读到
        # 同一个数，判据当场退化（首轮实测就是这么红的）。
        dispatched_after_failure = len(captured)
        async with Session() as verify:
            keys_after_failure = await _consumption_keys(verify, handle_k.outbox_id)
            status_after_failure = await _status_of(verify, handle_k.outbox_id)
        async with Session() as db:
            worker_k = await DurableEventOutboxService.replay_pending(db, limit=50)
            await db.commit()
        async with Session() as verify:
            snap["fanout_failure_releases_the_claim"] = {
                "outbox_id": str(handle_k.outbox_id),
                "injected_failures": _flaky.calls,
                "failed_publish": failed_publish.as_dict(),
                "keys_after_failure": keys_after_failure,
                "status_after_failure": status_after_failure,
                "dispatched_after_failure": dispatched_after_failure,
                "worker_read_count": worker_k["read_count"],
                "worker_published_count": worker_k["published_count"],
                "worker_deduplicated": worker_k.get("deduplicated_fanout_count"),
                "dispatched_after_replay": len(captured),
                "status_after_replay": await _status_of(verify, handle_k.outbox_id),
                "keys_after_replay": await _consumption_keys(verify, handle_k.outbox_id),
            }

        # ── 场景 L：导入域不受闸门管辖（闸门范围必须可双向 falsify）────────────
        ledger_captured.clear()
        async with Session() as db:
            handle_l = await DurableEventOutboxService.enqueue(
                db,
                event_type=EventType.LEDGER_DATASET_ACTIVATED,
                project_id=project,
                year=2025,
                payload={"dataset_id": str(uuid.uuid4())},
            )
            await db.commit()
            await DurableEventOutboxService.publish_pending(db)
        ledger_after_first = len(ledger_captured)
        await _force_failed(handle_l.outbox_id)
        async with Session() as db:
            worker_l = await DurableEventOutboxService.replay_pending(db, limit=50)
            await db.commit()
        async with Session() as verify:
            ledger_keys = await _consumption_keys(verify, handle_l.outbox_id)
        snap["import_domain_is_not_gated"] = {
            "outbox_id": str(handle_l.outbox_id),
            "dispatched_after_first": ledger_after_first,
            "dispatched_after_replay": len(ledger_captured),
            "worker_read_count": worker_l["read_count"],
            "worker_deduplicated": worker_l.get("deduplicated_fanout_count"),
            "keys_for_this_event": ledger_keys,
        }

        # ── 场景 I：outbox payload → Stream 条目 → replay 逐项相等（Property 53）─
        import json

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=project,
            year=2025,
            account_codes=["1001", "1002"],
            batch_id=uuid.uuid4(),
            extra={
                "wp_id": str(wp_id),
                "revision": 12,
                "operation_id": str(uuid.uuid4()),
                "source": "onlyoffice",
                "adapter_id": "g7.disclosure.listed",
                "artifact_sha256": "b" * 64,
                EVENT_ID_PAYLOAD_KEY: str(uuid.uuid4()),
            },
        )
        entry = {
            "event_type": payload.event_type.value,
            "project_id": str(payload.project_id),
            "year": str(payload.year),
            "account_codes": json.dumps(payload.account_codes),
            event_bus_module._STREAM_PAYLOAD_FIELD:
                event_bus_module.serialize_payload_for_stream(payload),
        }
        restored = event_bus_module.deserialize_payload_from_stream(entry)
        legacy_entry = {
            key: value
            for key, value in entry.items()
            if key != event_bus_module._STREAM_PAYLOAD_FIELD
        }
        legacy_restored = event_bus_module.deserialize_payload_from_stream(legacy_entry)
        snap["stream_roundtrip"] = {
            "stream_fields": sorted(entry.keys()),
            "payload_field_name": event_bus_module._STREAM_PAYLOAD_FIELD,
            "restored_extra": dict(restored.extra),
            "source_extra": dict(payload.extra),
            "restored_batch_id": str(restored.batch_id),
            "source_batch_id": str(payload.batch_id),
            "restored_account_codes": list(restored.account_codes or []),
            "restored_year": restored.year,
            "restored_project_id": str(restored.project_id),
            "legacy_restored_extra": dict(legacy_restored.extra),
        }
        return snap
    finally:
        _restore_publish()
        bus._redis_available = previous_redis_flag
        try:
            bus._handlers[EventType.WORKPAPER_SAVED].remove(_collector)
        except (KeyError, ValueError):  # pragma: no cover
            pass
        try:
            bus._handlers[EventType.LEDGER_DATASET_ACTIVATED].remove(_ledger_collector)
        except (KeyError, ValueError):  # pragma: no cover
            pass
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.dispose()


#: 采集必须产出的场景键。缺任一即判"采集没跑完"，由 `test_harness_collected_every_scenario`
#: 打红。空列表/空 dict 也算缺 —— 见下。
_REQUIRED_SCENARIOS = (
    "same_transaction",
    "rollback",
    "commit_then_publish",
    "republish_is_noop",
    "publish_failure_then_replay",
    "dlq_escalation",
    "consumption_idempotency",
    "missing_project_id",
    "stream_roundtrip",
    "fanout_at_most_once",
    "fanout_failure_releases_the_claim",
    "import_domain_is_not_gated",
)


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    """一次采集喂全部守卫；采集自身失败**不抛**，而是落进 ``harness_error``。

    Task 15 收口实测的教训：module 级 fixture 直接抛异常时，本文件全部用例只报
    ``ERROR``，而 pytest 的 ``-rf`` 摘要**不含 error**，于是变异四态判定看到"没有新增
    失败"就判 GREEN（读作"守卫没锁住"），实际是采集被写坏了。把异常收进快照并留一条
    专门断言它为空的守卫，才能既不 fail-open 又能被差集看见。
    """
    try:
        return asyncio.run(_collect())
    except BaseException as exc:  # noqa: BLE001 - 故意兜底：让它变成"打红"而不是"报错"
        return {"harness_error": f"{type(exc).__name__}: {exc}"}


def test_harness_collected_every_scenario(snap: dict[str, Any]) -> None:
    """采集完整性：fail-closed 到"打红"，不是"报错"。"""
    assert snap.get("harness_error") is None, snap.get("harness_error")
    missing = [name for name in _REQUIRED_SCENARIOS if not snap.get(name)]
    assert missing == [], f"采集没跑完，缺场景: {missing}"


# ═══════════════════════════════════════════════════════════════════════════
# Property 52：outbox 仅 commit 后发布
# ═══════════════════════════════════════════════════════════════════════════


def test_enqueue_happens_inside_the_caller_transaction(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.1**

    Property 52 的前置：耐久行必须与内容写在**同一个事务**里。判据是跨事务可见性 ——
    同 session 能看到（已 flush），另一个 session 看不到（未提交）。
    """
    fact = snap["same_transaction"]
    assert fact["visible_inside_same_transaction"] == 1
    assert fact["visible_to_other_transaction"] == 0
    assert fact["remembered_count"] == 1
    assert fact["session_info_key_present"] is True
    assert fact["events_dispatched_before_commit"] == 0, "事务内一个事件都不许派发"


def test_rollback_leaves_no_event_and_no_durable_row(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.1**

    Property 52「事务 rollback 时无事件」。旧实现在事务内直接 publish，回滚后事件已经
    发出去了 —— 下游按一个不存在的内容版本去刷新。
    """
    fact = snap["rollback"]
    assert fact["outbox_rows"] == 0
    assert fact["log_rows"] == 0
    assert fact["events_dispatched"] == 0
    assert fact["file_version"] == 4, "回滚后版本也没动"
    # publish 阶段把"行不存在"识别为 rolled_back，而不是当成失败去无限重试。
    assert fact["report"]["rolled_back"] == 1
    assert fact["report"]["published"] == 0
    assert fact["report"]["failed"] == 0


def test_commit_then_publish_emits_exactly_one_complete_event(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.1, 13.2**

    Property 52「commit 后恰有一个 payload 完整事件」。
    """
    fact = snap["commit_then_publish"]
    assert fact["events_before_commit"] == 0
    assert fact["events_after_commit_before_publish"] == 0
    assert fact["outbox_rows"] == 1
    row = fact["row"]
    assert row["status"] == "published"
    assert row["published_at_set"] is True
    assert row["event_type"] == "workpaper.saved"
    assert row["year"] == 2025
    assert fact["report"]["published"] == 1
    assert fact["report"]["failed"] == 0
    assert len(fact["dispatched"]) == 1

    dispatched = fact["dispatched"][0]
    assert dispatched["event_type"] == "workpaper.saved"
    assert dispatched["project_id"] == row["project_id"]
    assert dispatched["year"] == row["year"]

    stored = row["payload"]
    assert stored["trigger"] == "univer_save"
    assert stored["content_hash"] == "a" * 64
    assert stored["sheets"] == 3 and stored["cells"] == 42
    assert stored["wp_id"]
    # 🔴 Task 18：耐久 payload 携带的是**业务内容版本**。旧断言读的是 `file_version`，
    #    也就是"下游按哪个版本刷新"与"审计日志里记的版本"是两个不同计数器的形态。
    assert stored["content_revision"] == 5
    assert "file_version" not in stored, (
        "file_version 是文件生命周期版本，不得再充当跨通道同步版本（Requirement 2.1）"
    )
    # 逐项相等：派发出去的 extra 是耐久 payload 的超集，且只多一个 __event_id。
    for key, value in stored.items():
        assert dispatched["extra"][key] == value, f"payload 字段 {key} 在派发时被改写"
    event_id_key = fact["event_id_payload_key"]
    assert set(dispatched["extra"]) - set(stored) == {event_id_key}
    assert dispatched["extra"][event_id_key] == row["id"]
    # year 是路由列，不进 payload，避免同一语义两处真源。
    assert "year" not in stored

    # 审计日志与耐久事件在同一个事务里落地，一次保存恰一条。
    assert fact["log_action_types"] == ["workpaper_univer_save"]
    audited = fact["log_new_values"][0]
    assert audited["content_revision"] == 5
    for legacy in ("old_version", "new_version"):
        assert legacy not in audited, (
            f"审计日志又开始记 {legacy}（file_version 域）—— 与 payload/下游刷新用的版本"
            "不是同一个计数器（Requirement 2.1）"
        )

    # 发布完把句柄从 session 摘掉，二次调用不会再发。
    assert fact["remembered_after_publish"] == 0


def test_republish_and_worker_replay_do_not_duplicate_the_event(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.1, 13.3**

    Property 52「重放不重复副作用」。已 published 的行既不再派发，也不被 worker 选中。
    """
    fact = snap["republish_is_noop"]
    assert fact["empty_call"]["attempted"] == 0
    assert fact["explicit_call"]["already_published"] == 1
    assert fact["explicit_call"]["published"] == 0
    assert fact["worker_read_count"] == 0, "replay_pending 只选 pending/failed"
    assert fact["worker_published_count"] == 0
    assert fact["events_total_after_all"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# Property 54：after-save 失败可重试
# ═══════════════════════════════════════════════════════════════════════════


def test_publish_failure_is_durable_and_replayable(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.4**

    Property 54：注入失败后 outbox 为 failed/pending 并可重放成功，不静默丢失。
    """
    fact = snap["publish_failure_then_replay"]
    # 发布失败不向调用方抛：请求已经提交成功，抛异常只会让保存看起来失败。
    assert fact["raised_to_caller"] is None
    assert fact["injected_failures"] >= 1
    assert fact["failed_report"]["failed"] == 1
    assert fact["failed_report"]["published"] == 0
    assert fact["failed_report"]["last_error"], "失败原因必须落库并回报"

    rows = fact["rows_not_published_after_failure"]
    assert len(rows) == 1
    assert rows[0]["status"] in {"failed", "pending"}
    assert rows[0]["attempt_count"] >= 1
    assert rows[0]["last_error_present"] is True

    # 去掉注入后 worker 重放成功，事件最终恰发一次。
    assert fact["replay_report"]["published_count"] == 1
    assert fact["replay_report"]["failed_count"] == 0
    assert set(fact["statuses_after_replay"]) == {"published"}
    assert fact["events_dispatched"] == 1


def test_replay_never_moves_a_version_field(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 2.12**

    "handler 重试不得再次递增 content revision"。

    ═══ Task 18 把这条判据从"递增两次后不再动"改成"一次都没动" ═══

    Task 16 时 `after_save` 自己 `file_version += 1`，所以场景 C 与场景 E 各推一次
    （4→6），判据只能是"重放之后不是 7"。那个形态有一个盲点：**递增本身**是不是该
    发生，它不判。

    Task 18 把 `file_version` 的所有权交给三条真正写文件的路径后，`after_save` 一个
    版本字段都不写，于是判据变成绝对值：种子 4，经过场景 C（成功发布）+ 场景 E（失败
    发布 + worker 重放）之后仍然是 4。这比原判据强 —— 任何一次意外递增都会被看到，
    而不只是"重放时的那一次"。
    """
    fact = snap["publish_failure_then_replay"]
    assert fact["file_version_after_replay"] == 4, (
        "after_save 是共享且可重放的副作用 handler，一次都不该动 file_version："
        "种子是 4，场景 C/E 两次调用 + 一次 worker 重放之后必须还是 4"
    )


def test_exhausted_retries_escalate_to_dlq(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.4**

    "失败进入 pending/failed/DLQ"的 DLQ 分支由既有 `_move_to_dlq` 承担（facade 只委托、
    不复制这段逻辑）。
    """
    fact = snap["dlq_escalation"]
    assert fact["moved_to_dlq_count"] == 1
    assert len(fact["dlq_rows"]) == 1
    row = fact["dlq_rows"][0]
    assert row["event_type"] == "workpaper.saved"
    assert row["failure_reason_present"] is True
    assert row["original_event_id_present"] is True
    assert row["payload_wp_id_present"] is True, "DLQ 快照必须带完整 payload 便于手工重投"


# ═══════════════════════════════════════════════════════════════════════════
# Requirement 13.3：consumer 幂等
# ═══════════════════════════════════════════════════════════════════════════


def test_consumption_is_idempotent_per_event_and_handler_version(
    snap: dict[str, Any]
) -> None:
    """**Validates: Requirements 13.3**"""
    fact = snap["consumption_idempotency"]
    assert fact["first_claim"] is True
    assert fact["second_claim"] is False, "同 event_id + 同 handler 版本必须被唯一索引拦下"
    assert fact["bumped_version_claim"] is True, "handler 版本 +1 后允许按新语义重跑一次"
    assert fact["other_event_claim"] is True
    # savepoint 生效：冲突后事务仍可继续写，三条成功的记录都在。
    name = snap["handler_name"]
    version = snap["handler_version"]
    assert fact["handler_keys"] == sorted(
        [f"{name}@v{version}", f"{name}@v{version}", f"{name}@v{version + 1}"]
    )


# ═══════════════════════════════════════════════════════════════════════════
# fail-closed 与 Property 53（payload 保真）
# ═══════════════════════════════════════════════════════════════════════════


def test_missing_project_id_fails_closed(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.4**

    旧实现把 `EventPayload(project_id=None)` 的校验异常吞成 warning，结果是"保存成功但
    下游联动永久静默"。现在必须抛。
    """
    fact = snap["missing_project_id"]
    assert fact["raised"] == fact["expected"]


def test_stream_entry_preserves_every_payload_field(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.2**

    Property 53：Redis typed event 中 wp_id / revision / operation / source / adapter
    与 outbox 逐项相等。修点在**写入侧** —— 旧实现只往 Stream 写四个扁平字段。
    """
    fact = snap["stream_roundtrip"]
    assert fact["payload_field_name"] in fact["stream_fields"]
    assert fact["restored_extra"] == fact["source_extra"]
    for key in (
        "wp_id",
        "revision",
        "operation_id",
        "source",
        "adapter_id",
        "artifact_sha256",
    ):
        assert fact["restored_extra"][key] == fact["source_extra"][key]
    assert fact["restored_batch_id"] == fact["source_batch_id"]
    assert fact["restored_account_codes"] == ["1001", "1002"]
    assert fact["restored_year"] == 2025

    # 反向自检：去掉 payload_json 后 extra 必然为空 —— 证明是这个字段在承载 payload，
    # 而不是断言恰好被别的路径满足（否则守卫改一字也不会红）。
    assert fact["legacy_restored_extra"] == {}


# ═══════════════════════════════════════════════════════════════════════════
# Requirement 13.3：重复投递不重复副作用（fan-out 闸门的行为判据）
# ═══════════════════════════════════════════════════════════════════════════


def test_replayed_event_does_not_fan_out_its_side_effects_twice(
    snap: dict[str, Any]
) -> None:
    """**Validates: Requirements 13.3**

    "重复投递不得重复刷新、重复 after-save"。判据是**真实派发次数** —— 订阅者在第一次
    发布时收到 1 个事件；把耐久行打回 ``failed`` 让 worker 再重放一轮后，仍然只有那
    1 个事件，而行照样收敛成 ``published``。

    这是"闸门有没有接上"的唯一可信判据：光有 ``claim_consumption`` API 而派发口不调它，
    行为上与没有闸门完全一样（additive 死代码），而任何"字符串是否出现"式守卫都会绿。
    """
    fact = snap["fanout_at_most_once"]
    assert fact["first_publish"]["published"] == 1
    assert fact["dispatched_after_first"] == 1, "第一次发布必须真的派发一次"
    assert fact["keys_after_first"] == [f"{fact['outbox_id']}|{fact['fanout_key']}"], (
        "派发口必须以 (event_id, fanout handler@vN) 记账，否则重放无从判重"
    )

    # worker 确实选到了这一行（否则下面的"没有重复派发"是空转）。
    assert fact["worker_read_count"] == 1
    assert fact["worker_published_count"] == 1
    assert fact["worker_failed_count"] == 0
    assert fact["worker_deduplicated"] == 1, "去重必须在报告里可见（Requirement 13.9）"

    assert fact["dispatched_after_replay"] == 1, (
        "重放把副作用又派发了一遍 ⇒ 下游一致性比对/stale/联动/SSE 全部重复执行"
    )
    assert fact["status_after_replay"] == "published"
    assert fact["keys_after_replay"] == fact["keys_after_first"], "重放不该新增消费记录"


def test_fanout_failure_returns_the_ticket_so_replay_can_deliver(
    snap: dict[str, Any]
) -> None:
    """**Validates: Requirements 13.3, 13.4**

    闸门与 Property 54 不能互相打架：抢到派发权后**派发本身失败**时必须把权归还，否则
    重放会命中闸门直接跳过 —— 事件永久静默丢失，正是 Requirement 13.4 禁止的形态。
    """
    fact = snap["fanout_failure_releases_the_claim"]
    assert fact["injected_failures"] >= 1
    assert fact["failed_publish"]["failed"] == 1
    assert fact["failed_publish"]["published"] == 0
    assert fact["status_after_failure"] in {"failed", "pending"}
    assert fact["dispatched_after_failure"] == 0
    assert fact["keys_after_failure"] == [], (
        "派发失败却留着消费记录 ⇒ 重放被闸门挡下，事件永久丢失"
    )

    assert fact["worker_read_count"] == 1
    assert fact["worker_published_count"] == 1
    assert fact["worker_deduplicated"] == 0, "这一轮是真派发，不该计入去重"
    assert fact["dispatched_after_replay"] == 1, "归还派发权后重放必须真的补上这一次"
    assert fact["status_after_replay"] == "published"
    assert fact["keys_after_replay"] == [f"{fact['outbox_id']}|{snap['fanout_at_most_once']['fanout_key']}"]


def test_import_domain_replay_semantics_are_untouched(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.3**

    闸门范围必须**双向**可 falsify：既要证明底稿事件被管住，也要证明导入域没被顺手改掉。
    ``LEDGER_*`` 的重放语义属于 ledger-import spec（那边的 handler 各自记账并依赖"重放
    会重新派发"），Task 16 把它扩进闸门就是越界改别人的行为。
    """
    fact = snap["import_domain_is_not_gated"]
    assert fact["dispatched_after_first"] == 1
    assert fact["worker_read_count"] == 1
    assert fact["dispatched_after_replay"] == 2, (
        "导入域被闸门管住了 ⇒ 越界修改了 ledger-import 的重放语义"
    )
    assert fact["worker_deduplicated"] == 0
    assert fact["keys_for_this_event"] == [], "导入域事件不该被派发口记 fan-out 账"
