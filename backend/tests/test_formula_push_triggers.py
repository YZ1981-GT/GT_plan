"""公式推送事件触发（任务 11）：事件 → run；科目相交判定；只跑被保存的底稿；失败不冒泡；注册防重复。

spec: chain-closure-phase2-formula-push-engine · design §八 · 需求 2.1 / 2.2
「引擎写入不发 WORKPAPER_SAVED」由 test_formula_push_engine::test_engine_writes_never_publish_workpaper_saved 守卫。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.formula_push import triggers
from app.services.formula_push.engine import PushActionError

PID = uuid.uuid4()
WP = uuid.uuid4()


@pytest.fixture
def calls(monkeypatch):
    got: list[tuple] = []

    async def fake_push(project_id, year, trigger, *, wp_id=None, codes=None):
        normalized_codes = tuple(sorted(codes)) if codes is not None else None
        got.append((project_id, year, trigger, wp_id, normalized_codes))

    monkeypatch.setattr(triggers, "_push", fake_push)

    async def no_lookup(project_id, wp_id):
        return None

    monkeypatch.setattr(triggers, "_lookup_wp_code", no_lookup)
    return got


def tb(codes=None, year=2025, pid=PID) -> EventPayload:
    return EventPayload(event_type=EventType.TRIAL_BALANCE_UPDATED, project_id=pid, year=year, account_codes=codes)


def saved(wp_code="E1", wp_id=WP, year=2025) -> EventPayload:
    extra = {"wp_code": wp_code, "trigger": "checklist_response_save", "item_ids": ["E1-adj-cash-note"]}
    if wp_id is not None:
        extra["wp_id"] = str(wp_id)
    return EventPayload(event_type=EventType.WORKPAPER_SAVED, project_id=PID, year=year, extra=extra)


@pytest.mark.asyncio
@pytest.mark.parametrize("codes, fires, selected", [
    (None, True, None), ([], True, None),                         # 全量重算
    (["1002"], True, ("E1",)), (["1001.01"], True, ("E1",)),
    (["6601", "1012.03"], True, ("E1",)),
    (["6601", "2202"], False, None), (["10"], False, None), (["01001"], False, None),
])
async def test_trial_balance_updated_fires_only_when_cash_accounts_touched(calls, codes, fires, selected):
    await triggers.on_trial_balance_updated(tb(codes))
    assert calls == ([(PID, 2025, "TRIAL_BALANCE_UPDATED", None, selected)] if fires else [])


@pytest.mark.asyncio
async def test_trial_balance_updated_passes_only_matching_binding_codes(monkeypatch, calls):
    # K1 已永久注册（account_prefixes = ('1221', '1231')）；测试只验证科目前缀过滤逻辑。
    await triggers.on_trial_balance_updated(tb(["1001", "1221.01"]))
    # E1 匹配 1001，K1 匹配 1221 → 两个 binding 都应跑
    assert len(calls) == 1
    _, _, _, _, codes = calls[0]
    assert "E1" in codes and "K1" in codes
    calls.clear()
    await triggers.on_trial_balance_updated(tb(["1001"]))
    _, _, _, _, codes2 = calls[0]
    assert "E1" in codes2
    assert "K1" not in codes2
    calls.clear()
    # 不匹配任何 binding 的科目码 → 仍可能匹配 Tier A 码
    await triggers.on_trial_balance_updated(tb(["9999"]))
    assert calls == []


@pytest.mark.asyncio
async def test_trial_balance_updated_empty_codes_preserve_full_rebuild_compatibility(calls):
    await triggers.on_trial_balance_updated(tb([]))
    assert calls == [(PID, 2025, "TRIAL_BALANCE_UPDATED", None, None)]


@pytest.mark.asyncio
async def test_trial_balance_updated_without_year_is_not_guessed(calls):
    await triggers.on_trial_balance_updated(tb(year=None))
    assert calls == [], "缺年度不猜（不 `or 2025`）"


@pytest.mark.asyncio
@pytest.mark.parametrize("wp_owned, index_owned, wp_deleted, index_deleted, expected", [
    (True, True, False, False, "K1-1"),
    (False, True, False, False, None),
    (True, False, False, False, None),
    (False, False, False, False, None),
    (True, True, True, False, None),
    (True, True, False, True, None),
], ids=["active", "foreign-paper", "foreign-index", "foreign-both", "deleted-paper", "deleted-index"])
async def test_lookup_wp_code_enforces_project_and_soft_delete(
    monkeypatch, wp_owned, index_owned, wp_deleted, index_deleted, expected,
):
    import app.core.database as database

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        project_id, other_project, wp_id, index_id = (uuid.uuid4() for _ in range(4))
        async with engine.begin() as conn:
            await conn.execute(sa.text(
                "CREATE TABLE wp_index (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, "
                "wp_code TEXT NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT 0)"
            ))
            await conn.execute(sa.text(
                "CREATE TABLE working_paper (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, "
                "wp_index_id TEXT NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT 0)"
            ))
            await conn.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code, is_deleted) "
                "VALUES (:id, :pid, 'K1-1', :deleted)"
            ), {"id": str(index_id), "pid": str(project_id if index_owned else other_project),
                "deleted": index_deleted})
            await conn.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id, is_deleted) "
                "VALUES (:id, :pid, :index_id, :deleted)"
            ), {"id": str(wp_id), "pid": str(project_id if wp_owned else other_project),
                "index_id": str(index_id), "deleted": wp_deleted})
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(database, "async_session", factory)
        assert await triggers._lookup_wp_code(project_id, wp_id) == expected
        assert await triggers._lookup_wp_code(project_id, uuid.uuid4()) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_workpaper_saved_runs_only_that_e1_workpaper(calls):
    await triggers.on_workpaper_saved(saved())
    assert calls == [(PID, 2025, "WORKPAPER_SAVED", WP, ("E1",))]


@pytest.mark.asyncio
async def test_workpaper_saved_normalizes_registered_subcode(monkeypatch, calls):
    # K1 已永久注册，K1-1 归到主编码 K1
    await triggers.on_workpaper_saved(saved(wp_code="K1-1"))
    assert len(calls) == 1
    _, _, _, _, codes = calls[0]
    assert codes == ("K1",)


@pytest.mark.asyncio
async def test_workpaper_saved_looks_up_missing_code_and_normalizes_subcode(monkeypatch, calls):
    # K1 已永久注册；测试 wp_code 缺失时的反查路径
    async def lookup(project_id, wp_id):
        assert (project_id, wp_id) == (PID, WP)
        return "K1-1"

    monkeypatch.setattr(triggers, "_lookup_wp_code", lookup)
    await triggers.on_workpaper_saved(saved(wp_code=None))
    assert len(calls) == 1
    _, _, _, _, codes = calls[0]
    assert codes == ("K1",)


@pytest.mark.asyncio
async def test_workpaper_saved_ignores_unregistered_subcode(calls):
    # Z9 未注册 → Z9-1 保存不触发推送
    await triggers.on_workpaper_saved(saved(wp_code="Z9-1"))
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [saved(wp_code="Z9"), saved(wp_code=None), saved(wp_id=None), saved(year=None)])
async def test_workpaper_saved_ignores_other_or_incomplete_events(calls, event):
    await triggers.on_workpaper_saved(event)
    assert calls == []


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_push_failure_does_not_propagate_and_notifies_sync_failed(monkeypatch):
    """事件是上游提交后的副作用：推送失败不冒泡（否则打断重算 / 保存链），并推 sync.failed 可见降级。"""
    import app.core.database as database
    from app.services.event_bus import event_bus
    from app.services.formula_push import engine

    notified: list[EventPayload] = []

    async def boom(db, **kw):
        raise RuntimeError("四表取数失败")

    async def capture(payload):
        notified.append(payload)

    monkeypatch.setattr(database, "async_session", lambda: _FakeSession())
    monkeypatch.setattr(engine, "run_and_commit", boom)
    monkeypatch.setattr(event_bus, "_notify_sse", capture)
    await triggers._push(PID, 2025, "TRIAL_BALANCE_UPDATED")  # 不抛
    [evt] = notified
    assert evt.event_type == EventType.SYNC_FAILED and evt.extra["handler"] == "公式推送"
    assert "四表取数失败" in evt.extra["error"] and evt.extra["retry_endpoint"].endswith("/formula-push/run")


@pytest.mark.asyncio
async def test_business_refusal_is_not_reported_as_failure(monkeypatch):
    import app.core.database as database
    from app.services.event_bus import event_bus
    from app.services.formula_push import engine

    notified: list = []

    async def refuse(db, **kw):
        raise PushActionError("项目不存在或已删除")

    async def capture(payload):
        notified.append(payload)

    monkeypatch.setattr(database, "async_session", lambda: _FakeSession())
    monkeypatch.setattr(engine, "run_and_commit", refuse)
    monkeypatch.setattr(event_bus, "_notify_sse", capture)
    await triggers._push(PID, 2025, "TRIAL_BALANCE_UPDATED")
    assert notified == []


def test_register_subscribes_both_events_once():
    class Bus:
        def __init__(self):
            self.subs: list[tuple] = []

        def subscribe(self, event_type, handler):
            self.subs.append((event_type, handler))

    bus = Bus()
    triggers.register_formula_push_handlers(bus)
    triggers.register_formula_push_handlers(bus)  # 再注册一次（subscribe 不去重 ⇒ 须自防）
    assert bus.subs == [
        (EventType.TRIAL_BALANCE_UPDATED, triggers.on_trial_balance_updated),
        (EventType.WORKPAPER_SAVED, triggers.on_workpaper_saved),
    ]


def test_main_registers_formula_push_handlers():
    """注册点在 main._register_phase_handlers（与审批重算 handler 同处）—— 漏注册则事件驱动整条断。"""
    import ast
    import inspect

    import app.main as main

    tree = ast.parse(inspect.getsource(main._register_phase_handlers))
    names = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "register_formula_push_handlers" in names
