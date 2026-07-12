"""批量导入导出 SSE 进度端点测试 — workpaper-bulk-tab-import-export Task 5.3

覆盖：
- BulkProgressService 内存状态管理 (create/tick/complete/fail)
- SSE subscriber queue 推送机制
- BulkProgressCallback 适配器
- GET /progress/{task_id} 端点行为（终态直接返回 / 实时流 / 404）
- 过期任务清理

Validates: Requirements 6.1
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.services.bulk_tab.bulk_progress import (
    BulkProgressCallback,
    BulkProgressService,
    BulkTaskProgress,
    bulk_progress_service,
)


# ===========================================================================
# Unit: BulkProgressService
# ===========================================================================


class TestBulkProgressService:
    """BulkProgressService 内存状态管理"""

    def setup_method(self):
        self.svc = BulkProgressService()

    def test_create_task(self):
        """create_task 应立即返回 running 状态任务"""
        task = self.svc.create_task("proj-1", "user-1", "export-templates", 10)
        assert task.task_id
        assert task.project_id == "proj-1"
        assert task.user_id == "user-1"
        assert task.operation == "export-templates"
        assert task.total == 10
        assert task.current == 0
        assert task.status == "running"

    def test_get_task(self):
        """get_task 应返回已创建的任务"""
        task = self.svc.create_task("p", "u", "import", 5)
        assert self.svc.get_task(task.task_id) is task
        assert self.svc.get_task("nonexistent") is None

    def test_tick_increments_current(self):
        """tick 应递增 current 并更新 message"""
        task = self.svc.create_task("p", "u", "export-data", 3)
        self.svc.tick(task.task_id, "processing D2-1")
        assert task.current == 1
        assert task.message == "processing D2-1"
        self.svc.tick(task.task_id, "processing D2-2")
        assert task.current == 2

    def test_complete_sets_terminal_state(self):
        """complete 应设置终态"""
        task = self.svc.create_task("p", "u", "import", 2)
        self.svc.tick(task.task_id)
        self.svc.tick(task.task_id)
        self.svc.complete(task.task_id, "全部完成")
        assert task.status == "complete"
        assert task.message == "全部完成"
        assert task.completed_at is not None

    def test_fail_sets_error_state(self):
        """fail 应设置失败态"""
        task = self.svc.create_task("p", "u", "import", 5)
        self.svc.fail(task.task_id, "ZIP 校验失败")
        assert task.status == "failed"
        assert task.error == "ZIP 校验失败"
        assert task.completed_at is not None

    def test_tick_nonexistent_task_no_error(self):
        """对不存在的 task tick 不报错"""
        self.svc.tick("nonexistent", "msg")  # 不抛异常

    def test_cleanup_expired(self):
        """cleanup_expired 应清理过期任务"""
        task = self.svc.create_task("p", "u", "import", 1)
        self.svc.complete(task.task_id)
        # 强制设置过期时间
        from datetime import datetime, timedelta, timezone
        task.completed_at = datetime.now(timezone.utc) - timedelta(hours=25)
        removed = self.svc.cleanup_expired(max_age_hours=24.0)
        assert removed == 1
        assert self.svc.get_task(task.task_id) is None


# ===========================================================================
# Unit: SSE subscriber queue
# ===========================================================================


class TestSSESubscriber:
    """SSE subscriber queue 推送验证"""

    def setup_method(self):
        self.svc = BulkProgressService()

    def test_subscribe_receives_tick_events(self):
        """subscriber 应收到 tick 事件"""
        task = self.svc.create_task("p", "u", "export-templates", 3)
        queue = self.svc.subscribe(task.task_id)
        self.svc.tick(task.task_id, "step 1")
        msg = queue.get_nowait()
        assert msg["type"] == "progress"
        assert msg["current"] == 1
        assert msg["total"] == 3
        assert msg["message"] == "step 1"

    def test_subscribe_receives_complete_event(self):
        """subscriber 应收到 complete 终态事件"""
        task = self.svc.create_task("p", "u", "import", 1)
        queue = self.svc.subscribe(task.task_id)
        self.svc.tick(task.task_id)
        self.svc.complete(task.task_id, "done")
        # skip progress event
        queue.get_nowait()
        msg = queue.get_nowait()
        assert msg["type"] == "complete"
        assert msg["message"] == "done"

    def test_subscribe_receives_error_event(self):
        """subscriber 应收到 error 终态事件"""
        task = self.svc.create_task("p", "u", "import", 1)
        queue = self.svc.subscribe(task.task_id)
        self.svc.fail(task.task_id, "boom")
        msg = queue.get_nowait()
        assert msg["type"] == "error"
        assert msg["message"] == "boom"

    def test_unsubscribe_removes_queue(self):
        """unsubscribe 后 queue 不再收消息"""
        task = self.svc.create_task("p", "u", "export-data", 2)
        queue = self.svc.subscribe(task.task_id)
        self.svc.unsubscribe(task.task_id, queue)
        self.svc.tick(task.task_id, "after unsubscribe")
        assert queue.empty()

    def test_multiple_subscribers(self):
        """多个 subscriber 应同时收到事件"""
        task = self.svc.create_task("p", "u", "import", 1)
        q1 = self.svc.subscribe(task.task_id)
        q2 = self.svc.subscribe(task.task_id)
        self.svc.tick(task.task_id, "x")
        assert not q1.empty()
        assert not q2.empty()
        assert q1.get_nowait()["message"] == "x"
        assert q2.get_nowait()["message"] == "x"


# ===========================================================================
# Unit: BulkProgressCallback adapter
# ===========================================================================


class TestBulkProgressCallback:
    """BulkProgressCallback 适配器（给 service 层使用）"""

    def test_tick_delegates_to_service(self):
        """callback.tick 应委托给 service.tick"""
        svc = BulkProgressService()
        task = svc.create_task("p", "u", "export-templates", 5)
        cb = svc.make_progress_callback(task.task_id)
        assert isinstance(cb, BulkProgressCallback)
        cb.tick("hello")
        assert task.current == 1
        assert task.message == "hello"

    def test_tick_without_message(self):
        """callback.tick() 无参数也正常递增"""
        svc = BulkProgressService()
        task = svc.create_task("p", "u", "import", 2)
        cb = svc.make_progress_callback(task.task_id)
        cb.tick()
        assert task.current == 1
        assert task.message == ""


# ===========================================================================
# Integration: GET /progress/{task_id} endpoint
# ===========================================================================


class TestProgressEndpoint:
    """GET /progress/{task_id} 端点集成测试"""

    @pytest.fixture
    def app(self):
        """创建最小 FastAPI 实例挂载 bulk-tab 路由"""
        from fastapi import FastAPI
        from app.routers.wp_bulk_router import router
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_404_for_nonexistent_task(self, client):
        """不存在的 task_id 应返回 404"""
        # 绕过权限依赖 — 直接测 service 逻辑
        from app.routers.wp_bulk_router import get_bulk_progress_stream
        from fastapi import HTTPException
        from unittest.mock import AsyncMock, patch
        import types

        mock_user = types.SimpleNamespace(id="u1", role=types.SimpleNamespace(value="admin"))
        from uuid import UUID
        with pytest.raises(HTTPException) as exc_info:
            await get_bulk_progress_stream(
                project_id=UUID("00000000-0000-0000-0000-000000000001"),
                task_id="nonexistent-task",
                current_user=mock_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_terminal_complete_returns_immediately(self):
        """已完成的任务应直接返回 complete 事件（不阻塞）"""
        from app.routers.wp_bulk_router import get_bulk_progress_stream
        from fastapi.responses import StreamingResponse
        import types
        from uuid import UUID

        # 创建已完成的任务
        task = bulk_progress_service.create_task(
            "00000000-0000-0000-0000-000000000001", "u1", "export-templates", 5
        )
        task.current = 5
        bulk_progress_service.complete(task.task_id, "全部完成")

        mock_user = types.SimpleNamespace(id="u1", role=types.SimpleNamespace(value="admin"))
        response = await get_bulk_progress_stream(
            project_id=UUID("00000000-0000-0000-0000-000000000001"),
            task_id=task.task_id,
            current_user=mock_user,
        )
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"

        # 消费 SSE 流
        body = b""
        async for chunk in response.body_iterator:
            body += chunk.encode() if isinstance(chunk, str) else chunk
        text = body.decode()
        assert "event: complete" in text
        assert '"type": "complete"' in text

        # 清理
        bulk_progress_service._tasks.pop(task.task_id, None)

    @pytest.mark.asyncio
    async def test_terminal_failed_returns_error_event(self):
        """已失败的任务应直接返回 error 事件"""
        from app.routers.wp_bulk_router import get_bulk_progress_stream
        from fastapi.responses import StreamingResponse
        import types
        from uuid import UUID

        task = bulk_progress_service.create_task(
            "00000000-0000-0000-0000-000000000001", "u1", "import", 3
        )
        bulk_progress_service.fail(task.task_id, "ZIP 损坏")

        mock_user = types.SimpleNamespace(id="u1", role=types.SimpleNamespace(value="admin"))
        response = await get_bulk_progress_stream(
            project_id=UUID("00000000-0000-0000-0000-000000000001"),
            task_id=task.task_id,
            current_user=mock_user,
        )
        body = b""
        async for chunk in response.body_iterator:
            body += chunk.encode() if isinstance(chunk, str) else chunk
        text = body.decode()
        assert "event: error" in text
        assert "ZIP" in text

        bulk_progress_service._tasks.pop(task.task_id, None)

    @pytest.mark.asyncio
    async def test_project_mismatch_returns_404(self):
        """task 属于不同项目时返回 404"""
        from app.routers.wp_bulk_router import get_bulk_progress_stream
        from fastapi import HTTPException
        import types
        from uuid import UUID

        task = bulk_progress_service.create_task(
            "00000000-0000-0000-0000-000000000002", "u1", "import", 1
        )

        mock_user = types.SimpleNamespace(id="u1", role=types.SimpleNamespace(value="admin"))
        with pytest.raises(HTTPException) as exc_info:
            await get_bulk_progress_stream(
                project_id=UUID("00000000-0000-0000-0000-000000000001"),
                task_id=task.task_id,
                current_user=mock_user,
            )
        assert exc_info.value.status_code == 404

        bulk_progress_service._tasks.pop(task.task_id, None)

    @pytest.mark.asyncio
    async def test_running_task_streams_events(self):
        """正在运行的任务应开始 SSE 流并接收实时事件"""
        from app.routers.wp_bulk_router import get_bulk_progress_stream
        from fastapi.responses import StreamingResponse
        import types
        from uuid import UUID

        task = bulk_progress_service.create_task(
            "00000000-0000-0000-0000-000000000001", "u1", "export-data", 3
        )

        mock_user = types.SimpleNamespace(id="u1", role=types.SimpleNamespace(value="admin"))
        response = await get_bulk_progress_stream(
            project_id=UUID("00000000-0000-0000-0000-000000000001"),
            task_id=task.task_id,
            current_user=mock_user,
        )
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"

        # 模拟后台推送然后完成
        async def push_events():
            await asyncio.sleep(0.05)
            bulk_progress_service.tick(task.task_id, "D2-1")
            await asyncio.sleep(0.05)
            bulk_progress_service.complete(task.task_id, "done")

        push_task = asyncio.create_task(push_events())

        body = b""
        async for chunk in response.body_iterator:
            body += chunk.encode() if isinstance(chunk, str) else chunk
        await push_task

        text = body.decode()
        assert "event: progress" in text
        assert "D2-1" in text
        assert "event: complete" in text

        bulk_progress_service._tasks.pop(task.task_id, None)
