"""Task 32 欠账②守卫：`_fold_observability_facts` 的读侧派生逻辑。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure（Task 70 前置：Task 32 读路由）

same-application higher-sequence fold 的写侧（Task 23 advance_room_durable_fence）一直在
维护 application 的 origin/effective sequence 与 room 的 latest-durable 指针，但此前**无读
路由暴露** ⇒ `same_application_higher_sequence_fold` 场景无从观测、只能落 failed。

本守卫锁死读侧派生（纯函数逻辑，不依赖真库）：
  · effective_ge_origin = effective >= origin（fold 只 GREATEST、从不回退）；
  · same_application_fold = room.latest_durable_application_id == application.id
    （canonical fence 仍指向本 application ⇒ 更高 sequence 只 fold、未 self-stale、origin 未改写）。
用假 session/application 直接喂三种形态：正常 fold、指针指向别的 application（self-stale）、
未绑定 room。
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

from app.routers.wp_sync_router import _fold_observability_facts


class _FakeResult:
    def __init__(self, row: Any) -> None:
        self._row = row

    def first(self) -> Any:
        return self._row


class _FakeSession:
    """只实现 helper 用到的 `execute(...).first()`；返回预置的 room 行。"""

    def __init__(self, room_row: Any) -> None:
        self._room_row = room_row
        self.calls = 0

    async def execute(self, _stmt: Any) -> _FakeResult:
        self.calls += 1
        return _FakeResult(self._room_row)


def _svc(room_row: Any) -> Any:
    return SimpleNamespace(session=_FakeSession(room_row))


def _app(app_id: uuid.UUID, *, origin: int, effective: int) -> Any:
    return SimpleNamespace(
        id=app_id,
        origin_request_sequence=origin,
        effective_request_sequence=effective,
    )


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_fold_when_room_fence_still_points_at_this_application() -> None:
    app_id = uuid.uuid4()
    room_id = uuid.uuid4()
    # room 的 canonical 指针仍指向本 application，effective 高于 origin（发生过 fold）
    svc = _svc((app_id, 7))
    facts = _run(
        _fold_observability_facts(
            svc, application=_app(app_id, origin=3, effective=7), room_id=room_id
        )
    )
    assert facts["origin_request_sequence"] == 3
    assert facts["effective_request_sequence"] == 7
    assert facts["effective_ge_origin"] is True
    assert facts["room_latest_durable_application_id"] == str(app_id)
    assert facts["room_latest_durable_sequence"] == 7
    # 指针仍指向本 application ⇒ 只 fold、未 self-stale、origin 未改写
    assert facts["same_application_fold"] is True


def test_not_a_fold_when_room_fence_points_at_another_application() -> None:
    app_id = uuid.uuid4()
    other_id = uuid.uuid4()
    room_id = uuid.uuid4()
    # canonical 指针指向**别的** application ⇒ same_application_fold 必须为 False
    svc = _svc((other_id, 9))
    facts = _run(
        _fold_observability_facts(
            svc, application=_app(app_id, origin=3, effective=3), room_id=room_id
        )
    )
    assert facts["same_application_fold"] is False
    assert facts["room_latest_durable_application_id"] == str(other_id)
    # origin==effective 时仍满足单调不回退
    assert facts["effective_ge_origin"] is True


def test_no_room_yields_null_room_facts_and_no_fold_claim() -> None:
    app_id = uuid.uuid4()
    svc = _svc(None)
    facts = _run(
        _fold_observability_facts(
            svc, application=_app(app_id, origin=1, effective=1), room_id=None
        )
    )
    # 未绑定 room ⇒ 不查库、不宣称 fold
    assert svc.session.calls == 0
    assert facts["room_latest_durable_application_id"] is None
    assert facts["room_latest_durable_sequence"] is None
    assert facts["same_application_fold"] is None


def test_missing_room_row_does_not_fabricate_a_fold() -> None:
    app_id = uuid.uuid4()
    room_id = uuid.uuid4()
    # room_id 给了但查不到行（room 被删/scope 漂移）⇒ 不得编造 fold
    svc = _svc(None)
    facts = _run(
        _fold_observability_facts(
            svc, application=_app(app_id, origin=2, effective=5), room_id=room_id
        )
    )
    assert svc.session.calls == 1
    assert facts["same_application_fold"] is None
    assert facts["room_latest_durable_application_id"] is None
