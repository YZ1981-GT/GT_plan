"""后端集成测试：复核对话路由 review_dialog.py

Tasks 6.1-6.5:
- 6.1 Property 11: 关闭线程拒绝消息 (hypothesis PBT)
- 6.2 thread_key 唯一约束
- 6.3 broadcast_raw 调用验证
- 6.4 AI 生成端点 mock
- 6.5 权限守卫 403

**Validates: Requirements 9.7, 9.3, 10.1, 7.1, 8.5**
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings, strategies as st

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.routers.review_dialog import router

# ─── Fixtures ────────────────────────────────────────────────────────────────

_USER_ID = uuid.uuid4()
_PROJECT_ID = uuid.uuid4()
_WP_ID = uuid.uuid4()
_THREAD_ID = uuid.uuid4()


class _FakeUser:
    id = _USER_ID
    username = "审计员张三"
    role = UserRole.auditor


class _FakeRow:
    """Simulates a DB row tuple."""

    def __init__(self, *values):
        self._values = values

    def __getitem__(self, idx):
        return self._values[idx]

    def fetchone(self):
        return self


def _make_app(db_mock, user=None) -> FastAPI:
    """Create minimal FastAPI app with overridden deps."""
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_mock

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user or _FakeUser()
    return app


def _mock_db(execute_side_effects: list | None = None):
    """Create a mock AsyncSession with configurable execute results."""
    db = AsyncMock()
    if execute_side_effects:
        db.execute = AsyncMock(side_effect=execute_side_effects)
    db.commit = AsyncMock()
    return db


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _result(row):
    """Wrap a tuple/None as a mock execute result with fetchone."""
    r = MagicMock()
    r.fetchone.return_value = row
    r.fetchall = MagicMock(return_value=[])
    return r


def _result_with_messages(row, messages=None):
    """Wrap a row for thread query + messages query."""
    r = MagicMock()
    r.fetchone.return_value = row
    r.fetchall = MagicMock(return_value=messages or [])
    return r


# ─── 6.1 Property 11: closed thread rejects message (hypothesis) ────────────


class TestClosedThreadRejectsMessage:
    """Property 11: 关闭线程拒绝新消息 — HTTP 400.

    **Validates: Requirements 9.7**
    """

    @settings(max_examples=5)
    @given(content=st.text(min_size=1, max_size=200))
    @pytest.mark.asyncio
    async def test_closed_thread_returns_400(self, content: str):
        """For any non-empty message content, POST to a closed thread → 400."""
        thread_row = (str(_THREAD_ID), "closed", str(_PROJECT_ID))

        # DB: thread lookup returns closed thread
        # DB: project_assignments check passes
        db = _mock_db()
        db.execute = AsyncMock(side_effect=[
            _result(thread_row),  # SELECT thread
        ])

        app = _make_app(db)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/review-threads/{_THREAD_ID}/messages",
                json={"content": content, "message_type": "text"},
            )

        assert resp.status_code == 400
        assert "已关闭" in resp.json()["detail"]


# ─── 6.2 thread_key unique constraint ───────────────────────────────────────


class TestThreadKeyUnique:
    """同 wp_id + section_id 二次请求返回同一线程。

    **Validates: Requirements 9.3**
    """

    @pytest.mark.asyncio
    async def test_get_or_create_returns_same_thread(self):
        """Two GET requests with same wp_id+section_id → same thread id."""
        thread_id = str(uuid.uuid4())
        thread_key = f"{_WP_ID}:audit-note"

        # Mock: _get_project_id_for_wp returns project
        wp_row = (str(_PROJECT_ID),)
        # Mock: _check_project_access passes
        access_row = (1,)
        # Mock: thread exists
        thread_row = (thread_id, thread_key, "open")

        def make_side_effects():
            return [
                _result(wp_row),           # SELECT project_id FROM working_paper
                _result(access_row),       # SELECT 1 FROM project_assignments
                _result(thread_row),       # SELECT thread by thread_key
                _result_with_messages(None, []),  # SELECT messages (fetchall)
            ]

        # First request
        db1 = _mock_db()
        db1.execute = AsyncMock(side_effect=make_side_effects())
        app1 = _make_app(db1)
        transport1 = ASGITransport(app=app1)
        async with AsyncClient(transport=transport1, base_url="http://test") as c:
            r1 = await c.get(
                "/api/review-threads",
                params={"wp_id": str(_WP_ID), "section_id": "audit-note"},
            )

        # Second request
        db2 = _mock_db()
        db2.execute = AsyncMock(side_effect=make_side_effects())
        app2 = _make_app(db2)
        transport2 = ASGITransport(app=app2)
        async with AsyncClient(transport=transport2, base_url="http://test") as c:
            r2 = await c.get(
                "/api/review-threads",
                params={"wp_id": str(_WP_ID), "section_id": "audit-note"},
            )

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"] == thread_id


# ─── 6.3 broadcast_raw 调用验证 ─────────────────────────────────────────────


class TestBroadcastRaw:
    """消息创建后 event_bus.broadcast_raw 被调用且 payload 正确。

    **Validates: Requirements 10.1**
    """

    @pytest.mark.asyncio
    async def test_broadcast_raw_called_on_message_create(self):
        """After successful POST /messages, broadcast_raw is called."""
        thread_row = (str(_THREAD_ID), "open", str(_PROJECT_ID))
        access_row = (1,)
        created_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        created_row = (created_at,)

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[
            _result(thread_row),     # SELECT thread (status check)
            _result(access_row),     # project_assignments check
            MagicMock(),             # INSERT message
            MagicMock(),             # UPDATE thread updated_at
            _result(created_row),    # SELECT created_at
        ])

        app = _make_app(db)
        transport = ASGITransport(app=app)

        # Patch at the module that gets imported lazily inside create_message
        mock_bus = MagicMock()
        mock_event_bus_module = MagicMock(event_bus=mock_bus)
        with patch.dict("sys.modules", {"app.services.event_bus": mock_event_bus_module}):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    f"/api/review-threads/{_THREAD_ID}/messages",
                    json={"content": "请复核此数据", "message_type": "text"},
                )

        assert resp.status_code == 200
        # Verify broadcast_raw was called
        assert mock_bus.broadcast_raw.called
        call_args = mock_bus.broadcast_raw.call_args
        assert call_args[0][0] == "review_message.created"
        payload = call_args[0][1]
        assert payload["project_id"] == str(_PROJECT_ID)
        assert payload["thread_id"] == str(_THREAD_ID)
        assert payload["message"]["content"] == "请复核此数据"
        assert payload["message"]["sender_id"] == str(_USER_ID)


# ─── 6.4 AI 生成端点 ────────────────────────────────────────────────────────


class TestAiGenerate:
    """mock chat_completion 验证返回结构。

    **Validates: Requirements 7.1**
    """

    @pytest.mark.asyncio
    async def test_ai_generate_returns_generated_text(self):
        """POST /workpapers/{wp_id}/review-dialog/ai-generate → generated_text."""
        wp_row = (str(_PROJECT_ID),)
        access_row = (1,)

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[
            _result(wp_row),     # SELECT project_id FROM working_paper
            _result(access_row), # project_assignments check
        ])

        app = _make_app(db)
        transport = ASGITransport(app=app)

        mock_result = "经审计，银行存款期末余额为¥1,234,567.89，与银行对账单核对一致。"
        mock_chat = AsyncMock(return_value=mock_result)
        mock_llm_module = MagicMock(chat_completion=mock_chat)
        # Patch the lazy import at module level
        with patch.dict("sys.modules", {"app.services.llm_client": mock_llm_module}):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    f"/api/workpapers/{_WP_ID}/review-dialog/ai-generate",
                    json={
                        "section_id": "audit-note",
                        "related_data": {"amount": 1234567.89},
                        "existing_content": "",
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert "generated_text" in data
        assert data["generated_text"] == mock_result
        assert data["is_stub"] is False


# ─── 6.5 权限守卫 ───────────────────────────────────────────────────────────


class TestPermissionGuard:
    """无关项目用户请求返回 403。

    **Validates: Requirements 8.5**
    """

    @pytest.mark.asyncio
    async def test_unauthorized_user_gets_403(self):
        """User with no project_assignments → 403."""
        wp_row = (str(_PROJECT_ID),)
        no_access = None  # fetchone returns None → no assignment

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[
            _result(wp_row),     # SELECT project_id FROM working_paper
            _result(no_access),  # project_assignments check → None
        ])

        app = _make_app(db)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                "/api/review-threads",
                params={"wp_id": str(_WP_ID), "section_id": "audit-note"},
            )

        assert resp.status_code == 403
        assert "无权访问" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_unauthorized_user_ai_generate_403(self):
        """User with no project assignment on AI generate → 403."""
        wp_row = (str(_PROJECT_ID),)
        no_access = None

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[
            _result(wp_row),
            _result(no_access),
        ])

        app = _make_app(db)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                f"/api/workpapers/{_WP_ID}/review-dialog/ai-generate",
                json={"section_id": "audit-note", "related_data": {}},
            )

        assert resp.status_code == 403
