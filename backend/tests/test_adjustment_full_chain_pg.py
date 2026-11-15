"""C8 / F3：批准 → 试算表 → durable outbox → 真实 EventBus handler 全链验收。

与既有分段用例的分工
--------------------
* ``test_adjustment_c8_faults*.py`` 用**替身**验证 outbox 的失败/重试/幂等状态机；
* 本文件**不 mock 相邻层**：``AdjustmentReviewCoordinator`` 真实跑（行锁 + 任务状态机 +
  ``recalc_adjustments`` / ``recalc_audited`` + outbox 入队），发布阶段走
  ``DurableEventOutboxService.publish_pending`` 的真实派发口
  （``ImportEventOutboxService._deliver`` → ``event_bus.publish_immediate``），
  handler 用**生产注册**的那些（``register_event_handlers()``）。

只在专用验收库（``GT_ADJ_ACCEPT_DB_URL``）里跑，见 ``scripts/e2e/create_adjustment_accept_db.py``。

🔴 关于「handler 中途失败」的实测语义（2026-11-15 探针实证）
------------------------------------------------------------
``EventBus._dispatch`` 对每个 handler 单独 try/except：**吞掉异常**、记日志、
再发一条 ``SYNC_FAILED`` 通知，然后继续下一个 handler。因此：

* handler 抛异常**不会**让 outbox 行落 ``failed``，也不会进 DLQ ——
  探针实测 ``published=1 failed=0``、outbox 行 ``status=published``；
* DLQ 只由 ``ImportEventOutboxService._deliver`` 自身抛错（例如 envelope 与路由字段
  不一致、fan-out 闸门取不到、DB 不可用）触发。

本文件按这个**真实**语义断言，不把「handler 失败应进 DLQ」写成判据 ——
那样写出来的用例只能是恒绿或恒红。
"""
from __future__ import annotations

import asyncio
import importlib
import pkgutil
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.test_adjustment_concurrency_and_rls_pg import (  # noqa: F401 - fixture 复用
    ACCEPT_URL_ENV,
    _accept_url,
    accept_db,
)


@pytest.fixture(scope="module", autouse=True)
def _models_loaded():
    import app.models as models_pkg

    for mod in pkgutil.iter_modules(models_pkg.__path__):
        if mod.name.startswith("_"):
            continue
        importlib.import_module(f"app.models.{mod.name}")


@pytest_asyncio.fixture(autouse=True)
async def _restore_event_bus_handlers():
    """每条用例前后还原 event_bus 的 handler 注册表。

    ``register_event_handlers()`` 是进程级副作用，且本文件会临时挂探针 handler。
    不还原的话：①下一条用例的 ``publish_pending`` 会调用上一条残留的探针；
    ②某条用例失败时 ``finally`` 里摘除探针可能来不及，残留 handler 会持有连接，
    让后续用例在 ``publish_pending`` 里长时间等待（2026-11-15 实测：单独跑绿、
    合跑时第二条 60s 超时）。
    """
    from app.services.event_bus import event_bus

    snapshot = {event_type: list(handlers)
                for event_type, handlers in event_bus._handlers.items()}
    try:
        yield
    finally:
        event_bus._handlers.clear()
        for event_type, handlers in snapshot.items():
            event_bus._handlers[event_type] = list(handlers)
        # 生产注册函数用模块级 _REGISTERED 去重；handlers 被清掉后必须一并重置，
        # 否则下一次 register_event_handlers() 会认为"已注册"而直接返回。
        try:
            import app.services.event_handlers as event_handlers_pkg

            registry = getattr(event_handlers_pkg, "_REGISTERED", None)
            if registry is not None:
                registry.clear()
        except Exception:  # noqa: BLE001
            pass


@pytest_asyncio.fixture
async def handler_sessions_bound_to_accept_db(monkeypatch):
    """把生产 handler 的 session 工厂指到验收库（否则它们连共享库，见 chain_world 说明）。

    🔴 这里**不能**写 ``from app.services.event_handlers import _impl as handlers_impl``：
    ``event_handlers/__init__.py`` 末尾有 ``sys.modules[__name__] = _impl``，把包本身
    换成了 ``_impl`` 模块，于是 ``from ... import _impl`` 拿到的是那个模块里名为
    ``_impl`` 的属性（一个再包装层），patch 它不会影响 handler 闭包读的模块全局。
    2026-11-15 实测：patch 错了对象 ⇒ handler 仍连共享库 ⇒ ``tb_change_history``
    的 ``project_id`` 外键失败、看起来像"全链没跑通"。
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import app.services.event_handlers as handlers_impl  # 已被替换为 _impl 模块本身

    engine = create_async_engine(_accept_url(), poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    original = handlers_impl.async_session_factory
    monkeypatch.setattr(handlers_impl, "async_session_factory", factory)
    assert handlers_impl.async_session_factory is factory
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def chain_world(accept_db):
    """在验收库里补一套「可批准」的分录组夹具，并把 handler 的 session 工厂指到验收库。

    🔴 为什么必须改这个工厂：生产 handler（``app/services/event_handlers/_impl.py``）
    一律用模块级 ``async_session_factory = app.core.database.async_session`` **自开
    session**。若不改，handler 会连到 ``settings.DATABASE_URL``（共享库），于是
    "项目不存在"、``logs``/``tb_change_history`` 写失败 —— 全链看起来像挂了，
    实际是 handler 在另一个库里找不到数据（2026-11-15 实测）。
    """
    return accept_db


async def _prepare_pending_group(world, *, adjustment_no: str, debit: str = "100"):
    """建科目 + TB 行 + 待复核分录组 + 复核任务，返回 (group_id, reviewer_id, account_codes)。"""
    from app.models.audit_platform_models import (
        AccountCategory, AccountChart, AccountDirection, AccountSource,
        AdjustmentType, ReviewStatus, TrialBalance,
    )
    from app.models.audit_platform_schemas import ReviewStatusChange
    from app.models.base import UserRole
    from app.models.core import User
    from app.services import adjustment_review_task_service as tasks
    from app.services.adjustment_group_writer import AdjustmentGroupLine, AdjustmentGroupWriter
    from app.services.adjustment_service import AdjustmentService

    sessions = world["sessions"]
    project_id, actor_id = world["project_id"], world["actor_id"]
    accounts = {"1122": ("应收账款", AccountCategory.asset),
                "6702": ("信用减值损失", AccountCategory.expense)}

    reviewer_id = uuid.uuid4()
    async with sessions[0]() as db:
        db.add(User(
            id=reviewer_id, username=f"t_adj_rv_{uuid.uuid4().hex[:8]}",
            email=f"t_adj_rv_{uuid.uuid4().hex[:8]}@test.local",
            hashed_password="x", role=UserRole.manager,
        ))
        for code, (name, category) in accounts.items():
            db.add(AccountChart(
                project_id=project_id, account_code=code, account_name=name,
                direction=AccountDirection.debit, level=1, category=category,
                source=AccountSource.standard,
            ))
            db.add(TrialBalance(
                project_id=project_id, year=2025, company_code="001",
                standard_account_code=code, account_name=name, account_category=category,
                unadjusted_amount=Decimal("1000"), aje_adjustment=Decimal("0"),
                rje_adjustment=Decimal("0"), wp_adjustment=Decimal("0"),
                audited_amount=Decimal("1000"),
            ))
        await db.commit()

    group_id = uuid.uuid4()
    async with sessions[0]() as db:
        await AdjustmentGroupWriter(db).write_group(
            project_id=project_id, year=2025, company_code="001",
            adjustment_no=adjustment_no,
            adjustment_type=AdjustmentType.aje,
            description="全链验收", entry_group_id=group_id,
            lines=[
                AdjustmentGroupLine(standard_account_code="1122", account_name="应收账款",
                                    debit_amount=Decimal(debit)),
                AdjustmentGroupLine(standard_account_code="6702", account_name="信用减值损失",
                                    credit_amount=Decimal(debit)),
            ],
            content_revision=1, audit_phase="final",
            review_status=ReviewStatus.draft, created_by=actor_id,
        )
        await db.flush()
        service = AdjustmentService(db)
        rows = await service._get_group_rows(project_id, group_id, for_update=True)
        await tasks.create_task(
            db, project_id=project_id, year=2025, rows=rows,
            reviewer_ids=[str(reviewer_id)], submitted_by=actor_id, note=None,
        )
        await service.change_review_status(
            project_id, group_id,
            ReviewStatusChange(status=ReviewStatus.pending_review,
                               expected_revision=rows[0].content_revision),
            actor_id,
        )
        await db.commit()
    return group_id, reviewer_id, sorted(accounts)


# ---------------------------------------------------------------------------
# F3-1：全链 —— 批准 → TB 调整列/审定数 → outbox 两条 → 真实 handler 被调用
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_approve_commits_tb_and_delivers_events_to_real_handlers(
    chain_world, handler_sessions_bound_to_accept_db,
):
    """不 mock 相邻层：coordinator 真实跑，发布走真实派发口，handler 走生产注册。

    断言链：
    1. ``decide`` 返回 ``tb_update_status=committed`` 且带 2 条 publication；
    2. 试算表 aje_adjustment / audited_amount 真的变了（批准语义落在财务事实上）；
    3. ``publish_pending`` 后两条事件都 ``published``，无 failed / rolled_back；
    4. 真实 handler 被调用（用生产注册 + 一个探针 handler 记录事件类型）；
    5. handler 侧真落库的证据：``tb_change_history`` 有本次操作记录。
    """
    from app.models.audit_platform_models import ReviewStatus
    from app.models.audit_platform_schemas import EventType
    from app.models.core import User
    from app.services.adjustment_review_coordinator import AdjustmentReviewCoordinator
    from app.services.event_bus import event_bus
    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    sessions = chain_world["sessions"]
    project_id, actor_id = chain_world["project_id"], chain_world["actor_id"]
    group_id, reviewer_id, account_codes = await _prepare_pending_group(
        chain_world, adjustment_no="AJE-CHAIN-FULL-1",
    )

    # 生产注册的 handler 就位（重复调用幂等，register_event_handlers 内部去重）。
    # 🔴 但**只保留与调整链直接相关的那几个**：全量注册会把 ReportEngine /
    # DeliverableStale 等重下游也挂上，它们在无请求上下文的环境里会长时间阻塞
    # （2026-11-15 实测：全量注册后 publish_pending 45s 不返回，抓 pg_stat_activity
    # 看到一个连接停在 "idle in transaction / RELEASE SAVEPOINT"）。本用例要证明的是
    # 「批准事件真的被派发到**生产 handler**」，不是「跑完所有下游」。
    import app.services.event_handlers as event_handlers_pkg

    event_handlers_pkg.register_event_handlers()
    from app.services.event_bus import event_bus as _bus

    chain_handlers = {
        "ADJUSTMENT_APPROVED": (
            "_mark_workpapers_stale_by_account",
            "_record_tb_change_on_adjustment",
            "_mark_reports_stale_on_adjustment",
        ),
        "TRIAL_BALANCE_UPDATED": (
            "_log_cascade_on_tb_updated",
        ),
    }
    for event_name, keep_names in chain_handlers.items():
        event_type = getattr(EventType, event_name)
        kept = [handler for handler in _bus._handlers.get(event_type, [])
                if any(name in getattr(handler, "__qualname__", "") for name in keep_names)]
        assert kept, f"{event_name} 上没有找到期望的生产 handler：{keep_names}"
        _bus._handlers[event_type] = kept

    delivered: list[str] = []

    async def probe(payload):
        delivered.append(payload.event_type.value)

    event_bus.subscribe(EventType.ADJUSTMENT_APPROVED, probe)
    event_bus.subscribe(EventType.TRIAL_BALANCE_UPDATED, probe)

    try:
        # ① 批准（真实 coordinator）
        async with sessions[0]() as db:
            reviewer = await db.get(User, reviewer_id)
            result = await AdjustmentReviewCoordinator(db).decide(
                project_id=project_id, entry_group_id=group_id,
                status=ReviewStatus.approved, actor=reviewer, reason="全链验收批准",
            )
            await db.commit()
            publications = list(result.publications)
            assert result.info["tb_update_status"] == "committed"
            assert len(publications) == 2

        # ② 试算表真的改了
        async with sessions[0]() as db:
            rows = {
                row[0]: (Decimal(str(row[1])), Decimal(str(row[2])))
                for row in (await db.execute(sa.text(
                    "select standard_account_code, aje_adjustment, audited_amount "
                    "from trial_balance where project_id = :p and is_deleted = false"
                ), {"p": project_id})).all()
            }
        assert rows["1122"] == (Decimal("100.00"), Decimal("1100.00")), rows
        assert rows["6702"] == (Decimal("-100.00"), Decimal("900.00")), rows

        # ③ 发布 outbox（真实派发口）
        async with sessions[0]() as db:
            try:
                report = await asyncio.wait_for(
                    DurableEventOutboxService.publish_pending(db, publications), timeout=45,
                )
            except asyncio.TimeoutError:
                # 超时时抓等待链，把"卡在哪张表/哪个锁"变成可诊断输出
                import sqlalchemy as _sa

                from sqlalchemy.ext.asyncio import create_async_engine as _cae
                from sqlalchemy.pool import NullPool as _NP

                diag_engine = _cae(_accept_url(), poolclass=_NP)
                try:
                    async with diag_engine.connect() as conn:
                        waits = (await conn.execute(_sa.text("""
                            select pid, state, wait_event_type, wait_event,
                                   left(regexp_replace(query, '\\s+', ' ', 'g'), 90) as q
                            from pg_stat_activity
                            where datname = current_database() and pid <> pg_backend_pid()
                              and state is not null
                        """))).all()
                        ungranted = (await conn.execute(_sa.text("""
                            select l.pid, l.mode, c.relname
                            from pg_locks l left join pg_class c on c.oid = l.relation
                            where not l.granted
                        """))).all()
                finally:
                    await diag_engine.dispose()
                from pathlib import Path as _Path

                diag = _Path(__file__).resolve().parents[2] / "tmp_adj_accept" / "publish_hang_diag.txt"
                diag.parent.mkdir(parents=True, exist_ok=True)
                diag.write_text(
                    "active sessions:\n"
                    + "\n".join(
                        f"pid={w.pid} state={w.state} wait={w.wait_event_type}/{w.wait_event} q={w.q}"
                        for w in waits
                    )
                    + "\nungranted locks:\n"
                    + "\n".join(f"pid={u.pid} mode={u.mode} rel={u.relname}" for u in ungranted),
                    encoding="utf-8",
                )
                pytest.fail(f"publish_pending 45s 未返回，诊断见 {diag}")
        assert report.published == 2, report
        assert report.failed == 0 and report.rolled_back == 0, report

        # ④ 真实 handler 被调用
        assert "adjustment.approved" in delivered, delivered
        assert "trial_balance.updated" in delivered, delivered

        # ⑤ handler 侧真落库：TB 变更历史有本次批准记录
        async with sessions[0]() as db:
            history = (await db.execute(sa.text(
                "select operation_type, row_code from tb_change_history "
                "where project_id = :p order by created_at"
            ), {"p": project_id})).all()
        assert history, "tb_change_history 应至少有一条记录（handler 真的写了库）"
        assert any(row[1] in account_codes for row in history), history
    finally:
        # 摘掉探针 handler，避免影响后续用例
        for event_type in (EventType.ADJUSTMENT_APPROVED, EventType.TRIAL_BALANCE_UPDATED):
            handlers = event_bus._handlers.get(event_type, [])
            if probe in handlers:
                handlers.remove(probe)


# ---------------------------------------------------------------------------
# F3-2：handler 抛异常时的真实语义 —— outbox 仍 published（事件已派发），不谎报 DLQ
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handler_failure_does_not_flip_outbox_to_failed(
    chain_world, handler_sessions_bound_to_accept_db,
):
    """如实钉住 EventBus 的异常语义：handler 失败被吞掉 + 发 SYNC_FAILED，outbox 仍 published。

    为什么这样断言：``EventBus._dispatch`` 对每个 handler 单独 try/except，
    handler 异常不会冒泡到 ``_deliver``，所以 outbox 行不会落 ``failed``。
    如果把「handler 失败 ⇒ outbox failed」写成判据，用例会恒红。

    真正会让 outbox 落 failed 的是 ``_deliver`` 自身抛错（见 F3-3 的 envelope 不一致）。
    """
    from app.models.audit_platform_schemas import EventPayload, EventType
    from app.services.event_bus import event_bus
    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    sessions = chain_world["sessions"]
    project_id = chain_world["project_id"]

    async def boom(_payload):
        raise RuntimeError("F3 handler 中途失败注入")

    # SYNC_FAILED **不派发 handlers**（event_bus._dispatch 里只 _persist_to_stream +
    # _notify_sse），所以用 subscribe 收不到 —— 必须拦这两个出口。
    sync_failed: list[dict] = []
    original_notify = event_bus._notify_sse

    async def spy_notify(payload):
        if getattr(payload, "event_type", None) == EventType.SYNC_FAILED:
            sync_failed.append(dict(payload.extra or {}))
        return await original_notify(payload)

    event_bus.subscribe(EventType.TRIAL_BALANCE_UPDATED, boom)
    event_bus._notify_sse = spy_notify
    try:
        async with sessions[0]() as db:
            publication = await DurableEventOutboxService.enqueue_event(db, EventPayload(
                event_type=EventType.TRIAL_BALANCE_UPDATED,
                project_id=project_id, year=2025, account_codes=["1122"],
            ))
            await db.commit()
            report = await DurableEventOutboxService.publish_pending(db, [publication])
            status = await db.scalar(sa.text(
                "select status from import_event_outbox where id = :i"
            ), {"i": publication.outbox_id})
        # 事件已经派发出去 ⇒ outbox 记 published（handler 的失败不改变"已投递"事实）
        assert report.published == 1, report
        assert report.failed == 0, report
        assert str(getattr(status, "value", status)) == "published"
        # 但失败必须**可见**：EventBus 发了 SYNC_FAILED，且带上源事件与错误
        assert sync_failed, "handler 失败必须发出 SYNC_FAILED 通知"
        assert sync_failed[0]["source_event"] == "trial_balance.updated", sync_failed
        # 生产注册的其它 handler 也可能失败（例如 ReportEngine 在无请求上下文时），
        # 所以按 handler 名定位本次注入的那条，而不是取列表第一条。
        injected = [item for item in sync_failed
                    if "boom" in str(item.get("handler", ""))]
        assert injected, sync_failed
        assert "handler 中途失败注入" in str(injected[0].get("error", "")), injected
    finally:
        event_bus._notify_sse = original_notify
        handlers = event_bus._handlers.get(EventType.TRIAL_BALANCE_UPDATED, [])
        if boom in handlers:
            handlers.remove(boom)


# ---------------------------------------------------------------------------
# F3-3：真正进 failed / DLQ 的路径 —— envelope 与路由字段不一致
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deliver_level_error_marks_outbox_failed_then_replay_reaches_dlq(
    chain_world, handler_sessions_bound_to_accept_db,
):
    """``_deliver`` 自身抛错（envelope 与 outbox 路由字段不一致）才让行落 failed。

    随后把重试次数上限压到 1 再重放一次，验证真的升到 DLQ —— 这是
    「死信可见」的判据，也是与 F3-2 的分界：handler 失败不落 failed，投递失败才落。
    """
    from app.models.audit_platform_schemas import EventPayload, EventType
    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    sessions = chain_world["sessions"]
    project_id = chain_world["project_id"]

    async with sessions[0]() as db:
        publication = await DurableEventOutboxService.enqueue_event(db, EventPayload(
            event_type=EventType.TRIAL_BALANCE_UPDATED,
            project_id=project_id, year=2025, account_codes=["1122"],
        ))
        await db.commit()
        # 破坏 envelope：把 typed payload 的 event_type 改成别的，_deliver 会抛 ValueError
        # （真实键名见 workpaper_sync/outbox.TYPED_EVENT_PAYLOAD_KEY）
        from app.services.workpaper_sync.outbox import TYPED_EVENT_PAYLOAD_KEY

        updated = await db.execute(sa.text("""
            update import_event_outbox
               set payload = jsonb_set(
                     payload,
                     ARRAY[:k1, :k2],
                     '"adjustment.approved"'::jsonb
                   )
             where id = :i
        """), {
            "i": publication.outbox_id,
            "k1": TYPED_EVENT_PAYLOAD_KEY,
            "k2": "event_type",
        })
        assert updated.rowcount == 1, "envelope 破坏失败：payload 里没有 typed payload"
        await db.commit()

        report = await DurableEventOutboxService.publish_pending(db, [publication])
        assert report.failed == 1, report
        row = (await db.execute(sa.text(
            "select status, attempt_count, last_error from import_event_outbox where id = :i"
        ), {"i": publication.outbox_id})).one()
    assert str(getattr(row[0], "value", row[0])) == "failed"
    assert int(row[1]) >= 1
    assert "不一致" in str(row[2] or "") or "envelope" in str(row[2] or "").lower(), row[2]

    # 重放到 DLQ：``max_attempts`` 的语义是「attempt_count >= max_attempts 的行
    # 不再进入本轮重放窗口，只统计 exhausted」；搬到 DLQ 只发生在「本轮真的尝试
    # 重放且又失败」的分支。所以先把计数归零让它进入窗口，再以 max_attempts=1 重放：
    # 这一次尝试必然再失败 ⇒ attempt_count 变 1 ⇒ >= max_attempts ⇒ 搬 DLQ。
    async with sessions[0]() as db:
        await db.execute(sa.text(
            "update import_event_outbox set attempt_count = 0, status = 'failed' where id = :i"
        ), {"i": publication.outbox_id})
        await db.commit()
        report = await DurableEventOutboxService.replay_pending(db, max_attempts=1)
        await db.commit()
        dlq = (await db.execute(sa.text(
            "select count(*) from event_outbox_dlq where original_event_id = :i"
        ), {"i": publication.outbox_id})).scalar_one()
        status = await db.scalar(sa.text(
            "select status from import_event_outbox where id = :i"
        ), {"i": publication.outbox_id})
    assert int(report.get("moved_to_dlq_count") or 0) >= 1, report
    assert int(dlq) >= 1, "投递失败且重试耗尽必须进 DLQ"
    # 原 outbox 行保留作审计痕迹（status=failed + attempt_count），不删除
    assert str(getattr(status, "value", status)) == "failed", status


# ---------------------------------------------------------------------------
# F3-4：不留残留 —— 前面的用例必须把【测试】项目与它派生的写入全部清掉
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chain_cases_leave_no_residual_rows(chain_world):
    """守卫：验收库里不得留下调整链的测试残留。

    fixture 的清理是逐语句 try/except 的（任一 FK 失败要能继续下一条），
    这种写法最容易静默漏表 —— 2026-11-15 实测就漏过 ``import_event_consumptions``
    与 ``event_outbox_dlq``，导致 ``projects`` 永远删不掉。本用例把"漏没漏"
    变成断言，而不是靠人去看库。
    """
    sessions = chain_world["sessions"]
    project_id = chain_world["project_id"]
    async with sessions[0]() as db:
        residual = {}
        for table in (
            "adjustment_entries", "adjustments", "adjustment_review_tasks",
            "adjustment_client_bookings", "adjustment_treatment_events",
        ):
            # 只统计「已不存在的项目」上的行：这些是清理漏网的孤儿
            residual[table] = int(await db.scalar(sa.text(f"""
                select count(*) from {table} t
                where not exists (select 1 from projects p where p.id = t.project_id)
            """)) or 0) if table not in {"adjustment_entries"} else 0
        # 分录组行：按 entry_group_id 判断，孤儿 = 组头已不在
        orphan_entries = int(await db.scalar(sa.text("""
            select count(*) from adjustment_entries e
            where e.is_deleted = false
              and not exists (
                select 1 from adjustments a
                where a.entry_group_id = e.entry_group_id and a.is_deleted = false
              )
        """)) or 0)
        # 本文件专属复核人前缀：除当前 fixture 的账号外，不应有遗留
        # （当前 actor 用户名是 t_adj_cc_*，复核人是 t_adj_rv_*，此处只查 rv 前缀）
        leftover_reviewers = int(await db.scalar(sa.text(
            "select count(*) from users where username like 't_adj_rv\\_%' and is_deleted = false"
        )) or 0)
    assert residual == dict.fromkeys(residual, 0), residual
    assert orphan_entries == 0, f"孤儿分录明细 {orphan_entries} 行"
    assert leftover_reviewers == 0, f"复核人账号未清理：{leftover_reviewers} 个"
