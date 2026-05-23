"""批量导出 SSE 进度推送测试 — proposal-remaining-18 C-3

覆盖：
- ExportType 枚举值新增（export.progress / export.complete / export.failed）
- ExportProgressService.create_task 立即返回 task_id
- 后台 _run_export 按顺序推送 progress → complete SSE 事件
- 失败路径推送 export.failed
- ExportTask 状态机（pending → running → complete/failed）
- 路由注册到 router_registry §116

Validates: requirements.md §三 C-3
"""

from __future__ import annotations

import asyncio
import inspect
import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.audit_platform_schemas import EventType
from app.services.export_progress_service import (
    EXPORT_DIR,
    ExportProgressService,
    ExportTask,
    export_progress_service,
)


# ---------------------------------------------------------------------------
# 1. EventType 枚举扩展
# ---------------------------------------------------------------------------


class TestEventTypeExtension:
    """C-3 新增 3 个事件类型"""

    def test_export_progress_value(self):
        assert EventType.EXPORT_PROGRESS.value == "export.progress"

    def test_export_complete_value(self):
        assert EventType.EXPORT_COMPLETE.value == "export.complete"

    def test_export_failed_value(self):
        assert EventType.EXPORT_FAILED.value == "export.failed"


# ---------------------------------------------------------------------------
# 2. ExportProgressService 行为
# ---------------------------------------------------------------------------


class TestExportProgressServiceCreateTask:
    """create_task 立即返回 task_id 并启动后台任务"""

    @pytest.mark.asyncio
    async def test_create_task_returns_task_id_immediately(self):
        """create_task 返回 task_id 不阻塞（后台任务自行运行）"""
        svc = ExportProgressService()

        # Mock _run_export 防止真的访问数据库
        async def _noop(task):
            task.status = "complete"

        with patch.object(svc, "_run_export", _noop):
            task = svc.create_task(
                project_id="proj-1",
                user_id="user-1",
                wp_ids=["wp-1", "wp-2", "wp-3"],
            )

            assert task.task_id
            assert task.total == 3
            assert task.done == 0
            assert task.status in ("pending", "running", "complete")
            # 任务应被记录
            assert svc.get_task(task.task_id) is task

    @pytest.mark.asyncio
    async def test_create_task_handles_empty_wp_ids(self):
        """空列表也能创建任务（total=0）"""
        svc = ExportProgressService()

        async def _noop(task):
            task.status = "complete"

        with patch.object(svc, "_run_export", _noop):
            task = svc.create_task(
                project_id="proj-1",
                user_id="user-1",
                wp_ids=[],
            )
            assert task.total == 0


class TestSseEventOrder:
    """关键正确性：SSE 事件按顺序推送 progress * N → complete（或 failed）"""

    @pytest.mark.asyncio
    async def test_progress_then_complete_sequence(self, tmp_path):
        """3 个底稿应推 3 次 progress + 1 次 complete"""
        svc = ExportProgressService()

        events: list[tuple[str, dict]] = []

        # 拦截 broadcast_raw 推送
        from app.services import event_bus as eb_module

        def _capture(event_type, extra=None):
            events.append((event_type, extra or {}))

        # 拦截 _add_one_workpaper 跳过 DB 访问
        async def _add_stub(self, db, zf, wp_id_str):
            # 写一个占位文件
            zf.writestr(f"{wp_id_str}.txt", b"placeholder")

        # 拦截数据库 session
        class _DummyDb:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def execute(self, *a, **kw):
                m = MagicMock()
                m.first.return_value = None
                return m

        def _dummy_session():
            return _DummyDb()

        # 重定向 EXPORT_DIR 到 tmp_path
        export_dir_patch = tmp_path / "exports"

        with patch.object(eb_module.event_bus, "broadcast_raw", _capture), \
             patch.object(ExportProgressService, "_add_one_workpaper", _add_stub), \
             patch("app.services.export_progress_service.EXPORT_DIR", export_dir_patch), \
             patch("app.core.database.async_session", _dummy_session):

            task = ExportTask(
                task_id="t-1",
                project_id="p-1",
                user_id="u-1",
                wp_ids=["wp-a", "wp-b", "wp-c"],
                total=3,
            )
            svc._tasks[task.task_id] = task

            await svc._run_export(task)

        # 4 次广播：3 次 progress + 1 次 complete
        types = [e[0] for e in events]
        assert types == [
            "export.progress",
            "export.progress",
            "export.progress",
            "export.complete",
        ], f"actual sequence: {types}"

        # 每次 progress 的 done 单调递增
        progress_dones = [e[1]["done"] for e in events if e[0] == "export.progress"]
        assert progress_dones == [1, 2, 3]

        # complete 事件含 download_url + task_id
        complete = events[-1]
        assert complete[0] == "export.complete"
        assert complete[1]["task_id"] == "t-1"
        assert complete[1]["download_url"] == "/api/exports/t-1"

        # 任务状态 complete + file_path 已写入
        assert task.status == "complete"
        assert task.file_path is not None
        assert task.file_path.exists()

        # ZIP 内容可读
        with zipfile.ZipFile(task.file_path) as zf:
            assert sorted(zf.namelist()) == ["wp-a.txt", "wp-b.txt", "wp-c.txt"]

    @pytest.mark.asyncio
    async def test_failed_path_publishes_export_failed(self, tmp_path):
        """异常路径必须推送 export.failed"""
        svc = ExportProgressService()

        events: list[tuple[str, dict]] = []
        from app.services import event_bus as eb_module

        def _capture(event_type, extra=None):
            events.append((event_type, extra or {}))

        # 让 db session __aenter__ 抛错
        class _BoomDb:
            async def __aenter__(self):
                raise RuntimeError("db unavailable")

            async def __aexit__(self, *a):
                return False

        def _boom_session():
            return _BoomDb()

        with patch.object(eb_module.event_bus, "broadcast_raw", _capture), \
             patch("app.core.database.async_session", _boom_session), \
             patch("app.services.export_progress_service.EXPORT_DIR", tmp_path / "exports"):

            task = ExportTask(
                task_id="t-fail",
                project_id="p-1",
                user_id="u-1",
                wp_ids=["wp-x"],
                total=1,
            )
            svc._tasks[task.task_id] = task
            await svc._run_export(task)

        types = [e[0] for e in events]
        assert "export.failed" in types
        assert task.status == "failed"
        assert task.error and "db unavailable" in task.error


# ---------------------------------------------------------------------------
# 3. 路由注册
# ---------------------------------------------------------------------------


class TestRouterRegistration:
    """路由必须注册到 router_registry §116"""

    def test_router_registered_in_collaboration(self):
        import app.router_registry.collaboration as mod

        src = inspect.getsource(mod)
        assert "batch_export_progress" in src, "§116 batch_export_progress 必须在协作域注册"
        assert "§116" in src, "§116 注释不能缺失"

    def test_router_endpoints_exist(self):
        from app.routers.batch_export_progress import router, download_router

        # 项目级 POST 端点
        paths_main = {r.path for r in router.routes}
        assert any("batch-export-async" in p for p in paths_main)

        # 全局下载端点
        paths_dl = {r.path for r in download_router.routes}
        assert any(p.endswith("/{task_id}") for p in paths_dl)
        assert any(p.endswith("/{task_id}/status") for p in paths_dl)


# ---------------------------------------------------------------------------
# 4. 全局单例
# ---------------------------------------------------------------------------


class TestGlobalSingleton:
    """模块导出的全局 export_progress_service 可用"""

    def test_singleton_importable(self):
        assert export_progress_service is not None
        assert isinstance(export_progress_service, ExportProgressService)
