"""公式推送事件触发（任务 11）：事件 → run；科目相交判定；只跑被保存的底稿；失败不冒泡；注册防重复。

spec: chain-closure-phase2-formula-push-engine · design §八 · 需求 2.1 / 2.2
「引擎写入不发 WORKPAPER_SAVED」由 test_formula_push_engine::test_engine_writes_never_publish_workpaper_saved 守卫。
"""
from __future__ import annotations

import uuid

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.formula_push import triggers
from app.services.formula_push.engine import PushActionError

PID = uuid.uuid4()
WP = uuid.uuid4()


@pytest.fixture
def calls(monkeypatch):
    got: list[tuple] = []

    async def fake_push(project_id, year, trigger, *, wp_id=None):
        got.append((project_id, year, trigger, wp_id))

    monkeypatch.setattr(triggers, "_push", fake_push)
    return got


def tb(codes=None, year=2025, pid=PID) -> EventPayload:
    return EventPayload(event_type=EventType.TRIAL_BALANCE_UPDATED, project_id=pid, year=year, account_codes=codes)


def saved(wp_code="E1", wp_id=WP, year=2025) -> EventPayload:
    extra = {"wp_code": wp_code, "trigger": "checklist_response_save", "item_ids": ["E1-adj-cash-note"]}
    if wp_id is not None:
        extra["wp_id"] = str(wp_id)
    return EventPayload(event_type=EventType.WORKPAPER_SAVED, project_id=PID, year=year, extra=extra)


@pytest.mark.asyncio
@pytest.mark.parametrize("codes, fires", [
    (None, True), ([], True),                         # 全量重算
    (["1002"], True), (["1001.01"], True), (["6601", "1012.03"], True),
    (["6601", "2202"], False), (["10"], False), (["01001"], False),
])
async def test_trial_balance_updated_fires_only_when_cash_accounts_touched(calls, codes, fires):
    await triggers.on_trial_balance_updated(tb(codes))
    assert calls == ([(PID, 2025, "TRIAL_BALANCE_UPDATED", None)] if fires else [])


@pytest.mark.asyncio
async def test_trial_balance_updated_without_year_is_not_guessed(calls):
    await triggers.on_trial_balance_updated(tb(year=None))
    assert calls == [], "缺年度不猜（不 `or 2025`）"


@pytest.mark.asyncio
async def test_workpaper_saved_runs_only_that_e1_workpaper(calls):
    await triggers.on_workpaper_saved(saved())
    assert calls == [(PID, 2025, "WORKPAPER_SAVED", WP)]


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [saved(wp_code="D2"), saved(wp_code=None), saved(wp_id=None), saved(year=None)])
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
