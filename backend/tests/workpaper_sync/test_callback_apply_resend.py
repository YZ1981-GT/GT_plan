"""回调后 apply 的失败只能留在 operation 上，回调一律回 0（spec writeback-followup-issue-closure R3.3 / R3.4）。

incoming 已 durable 之后，非零 / 500 都会让文档服务器反复重投或丢件。原先两条路径冒成 500：

* 文档服务器重发已处理过的回调 ⇒ 协调器抛 `ReapplyForbiddenError`（application 已应用过）或
  `ApplicationTerminalStaleError`（已作废）—— 这是「没事可做」，不是失败；
* 协调器入口校验在它自己的失败记录之前抛出 —— 只能由路由把失败写到 operation 上。

另：注册 / 绑定找不到 adapter 原先只打日志，现在同样写到 operation 上（落库语义见
`test_callback_apply_failure_pg.py`）。这里用替身逐条钉住路由的分派。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routers import wp_sync_router as R
from app.services.workpaper_sync.adapters.registry import RegistryError
from app.services.workpaper_sync.models import SyncDomainError


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _Session:
    """按顺序回放 execute 结果；记 rollback / commit 次数。"""

    def __init__(self, *values: Any) -> None:
        self._values = list(values)
        self.rollbacks = 0
        self.commits = 0

    async def execute(self, *_a: Any, **_k: Any) -> _Result:
        return _Result(self._values.pop(0) if self._values else None)

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def commit(self) -> None:
        self.commits += 1


def _app_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), entry_id="xlsx/gt-d2-accounts-receivable", wp_id=uuid.uuid4(),
        project_id=uuid.uuid4(), room_id=uuid.uuid4(), generation=3,
    )


def _outcome(app_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(application_id=app_id, operation_id=uuid.uuid4(), delivery_id=uuid.uuid4(), response_error=0)


@pytest.fixture
def wiring(monkeypatch):
    """注册 / 绑定成功、协调器行为由用例给定；记下失败记录调用。"""
    recorded: list[dict[str, Any]] = []

    async def _record(db, *, outcome, exc, stage):
        recorded.append({"stage": stage, "exc": type(exc).__name__})

    monkeypatch.setattr(R, "_attach_pilot_adapters", AsyncMock())
    monkeypatch.setattr(
        R, "bind_registration_to_target", AsyncMock(return_value=SimpleNamespace(adapter=object(), contract=None))
    )
    monkeypatch.setattr(R, "_record_callback_apply_failure", _record)

    def use(apply_side_effect: BaseException) -> None:
        class _Coordinator:
            def __init__(self, **_kw: Any) -> None:
                pass

            async def apply_durable_incoming(self, **_kw: Any) -> Any:
                raise apply_side_effect

        monkeypatch.setattr(R, "OoToHtmlCoordinator", _Coordinator)

    return SimpleNamespace(recorded=recorded, use=use)


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [
    R.ReapplyForbiddenError("application 已应用过"),
    R.ApplicationTerminalStaleError("application 已作废"),
])
async def test_resent_callback_for_finished_application_is_a_quiet_no_op(wiring, exc):
    wiring.use(exc)
    row = _app_row()
    db = _Session(row, uuid.uuid4())
    await R._apply_durable_incoming(db, outcome=_outcome(row.id))
    assert db.rollbacks == 1
    assert wiring.recorded == [], "已应用过 / 已作废不是失败，不得写成 operation error"


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [SyncDomainError("入口校验失败"), KeyError("bug")])
async def test_coordinator_entry_failure_is_recorded_on_the_operation(wiring, exc):
    wiring.use(exc)
    row = _app_row()
    await R._apply_durable_incoming(_Session(row, uuid.uuid4()), outcome=_outcome(row.id))
    assert wiring.recorded == [{"stage": "pre_apply", "exc": type(exc).__name__}]


@pytest.mark.asyncio
async def test_registry_failure_is_recorded_on_the_operation(wiring, monkeypatch):
    monkeypatch.setattr(R, "bind_registration_to_target", AsyncMock(side_effect=RegistryError("没有 adapter")))
    row = _app_row()
    await R._apply_durable_incoming(_Session(row), outcome=_outcome(row.id))
    assert wiring.recorded == [{"stage": "registry", "exc": "RegistryError"}]


class _BrokenSession(_Session):
    """rollback 从第 n 次起抛（模拟连接已断）。"""

    def __init__(self, fail_from: int) -> None:
        super().__init__()
        self._fail_from = fail_from

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollbacks >= self._fail_from:
            raise ConnectionError("连接已断")


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_from", [1, 2])
async def test_failure_recording_never_raises(monkeypatch, fail_from):
    """记录失败、之后的 rollback 也失败 ⇒ 只打日志；冒出去就是 500，文档服务器会反复重投。"""
    import app.services.workpaper_sync.callback_apply_failure as CAF

    monkeypatch.setattr(CAF, "record_pre_apply_failure", AsyncMock(side_effect=RuntimeError("写不进库")))
    db = _BrokenSession(fail_from)
    await R._record_callback_apply_failure(
        db, outcome=_outcome(uuid.uuid4()), exc=KeyError("x"), stage="pre_apply"
    )
    assert db.rollbacks == 2


def test_route_answers_zero_and_still_closes_the_room_for_a_resent_callback(wiring, monkeypatch):
    """路由层：同一 incoming 再到一次 ⇒ `{"error": 0}`（原先 500），并照常走关闭 room。"""
    wiring.use(R.ReapplyForbiddenError("application 已应用过"))
    row = _app_row()
    outcome = _outcome(row.id)

    class _Delivery:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def handle_callback(self, **_k: Any) -> Any:
            return outcome

    import app.services.workpaper_sync.callback_route as CR

    monkeypatch.setattr(R, "CallbackDeliveryService", _Delivery)
    monkeypatch.setattr(R, "build_download_policy", lambda **_k: None)
    monkeypatch.setattr(R, "build_httpx_transport", lambda: None)
    monkeypatch.setattr(R, "_onlyoffice_secret", lambda: "s")
    monkeypatch.setattr(CR, "resolve_platform_callback_authorization", lambda **_k: "Bearer x")
    monkeypatch.setattr(R, "_record_callback_metrics", AsyncMock())
    closed = AsyncMock()
    monkeypatch.setattr(R, "close_room_if_docserver_saved", closed)
    db = _Session(row, uuid.uuid4())

    app = FastAPI()
    app.include_router(R.public_router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    r = TestClient(app).post(f"/api/workpaper-sync/rooms/{uuid.uuid4()}/onlyoffice-callback", json={"status": 2})
    assert r.status_code == 200 and r.json() == {"error": 0}
    closed.assert_awaited_once()
