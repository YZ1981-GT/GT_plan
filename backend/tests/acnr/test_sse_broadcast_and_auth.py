"""ACNR SSE 广播 + 项目授权单元测试（Wave 6）

Feature: acnr-invalidation-overlay-hardening
Properties: P6(失效广播不变量 R2) P7(SSE 项目授权 R3)
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ─── P6: invalidate() 恒广播 acnr:invalidate（R2）─────────────────────────────

@pytest.mark.asyncio
async def test_p6_invalidate_broadcasts_acnr_invalidate():
    from app.services.acnr import events as acnr_events

    pid = str(uuid.uuid4())
    captured: list[tuple] = []

    def _fake_broadcast(event_type, extra=None):
        captured.append((event_type, extra))

    # 隔离：increment_epoch no-op（不写 dev DB），只验证广播
    with patch("app.services.acnr.cache_epoch.increment_epoch", new=AsyncMock(return_value=7)), \
         patch("app.services.event_bus.event_bus.broadcast_raw", new=_fake_broadcast):
        await acnr_events.invalidate(pid, wp_id="w1", trigger="test")

    acnr_calls = [c for c in captured if c[0] == "acnr:invalidate"]
    assert len(acnr_calls) == 1
    _, extra = acnr_calls[0]
    assert extra["project_id"] == pid
    assert extra["wp_id"] == "w1"
    assert extra["epoch"] == 7


@pytest.mark.asyncio
async def test_p6_empty_project_id_no_broadcast():
    from app.services.acnr import events as acnr_events

    captured: list[tuple] = []
    with patch("app.services.event_bus.event_bus.broadcast_raw",
               new=lambda et, extra=None: captured.append((et, extra))):
        await acnr_events.invalidate("")  # 空 project_id → 入口直接返回

    assert captured == []


@pytest.mark.asyncio
async def test_p6_broadcast_exception_does_not_break_invalidate():
    from app.services.acnr import events as acnr_events

    pid = str(uuid.uuid4())

    def _raise(event_type, extra=None):
        raise RuntimeError("sse queue boom")

    with patch("app.services.acnr.cache_epoch.increment_epoch", new=AsyncMock(return_value=1)), \
         patch("app.services.event_bus.event_bus.broadcast_raw", new=_raise):
        # 不应抛出（R2.5：广播异常仅告警不阻断）
        await acnr_events.invalidate(pid)


# ─── P7: SSE 项目授权（R3）─────────────────────────────────────────────────

def _mk_user(role: str):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.role = MagicMock()
    u.role.value = role
    return u


@pytest.mark.asyncio
async def test_p7_check_project_access_allows_admin():
    from app.services.acnr.auth import check_project_access

    # admin 直接放行，不查库
    session = AsyncMock()
    await check_project_access(_mk_user("admin"), str(uuid.uuid4()), session)
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_p7_check_project_access_allows_partner():
    from app.services.acnr.auth import check_project_access

    session = AsyncMock()
    await check_project_access(_mk_user("partner"), str(uuid.uuid4()), session)
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_p7_check_project_access_denies_non_member():
    from app.services.acnr.auth import check_project_access

    # 非 admin/partner 且 project_users / project_assignments 均无命中 → 403
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = None  # 两次查询均无行
    session.execute.return_value = result

    with pytest.raises(HTTPException) as exc:
        await check_project_access(_mk_user("staff"), str(uuid.uuid4()), session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_p7_sse_stream_endpoint_uses_project_access():
    """回归守卫：events 路由 sse_stream / get_events_since 引用 check_project_access（R3 接线）。"""
    import inspect
    from app.routers import events as events_router

    src = inspect.getsource(events_router)
    assert "check_project_access" in src
    # /stream 用 SSE 专用鉴权（query token 回退），/since 用普通鉴权
    assert "get_current_user_sse" in src
