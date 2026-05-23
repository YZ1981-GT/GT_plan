"""ZIP 清理测试 — proposal-remaining-18 task 5.7 / MT-8 配套

验证 ExportProgressService.cleanup_expired() + export_cleanup_worker 逻辑。
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.export_progress_service import (
    ExportProgressService,
    ExportTask,
)


class TestCleanupExpired:
    """ExportProgressService.cleanup_expired 行为"""

    def test_removes_old_zip_files(self, tmp_path, monkeypatch):
        """超过 max_age_hours 的 zip 应被删除"""
        # 重定向 EXPORT_DIR 到 tmp_path
        from app.services import export_progress_service as mod
        monkeypatch.setattr(mod, "EXPORT_DIR", tmp_path)

        # 创建 2 个 zip：1 个 25h 前 + 1 个 10min 前
        old_zip = tmp_path / "old-task.zip"
        old_zip.write_bytes(b"PK\x03\x04 fake old zip")
        new_zip = tmp_path / "new-task.zip"
        new_zip.write_bytes(b"PK\x03\x04 fake new zip")

        # 把 old_zip 的 mtime 改到 25h 前
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).timestamp()
        os.utime(old_zip, (old_ts, old_ts))

        svc = ExportProgressService()
        result = svc.cleanup_expired(max_age_hours=24.0)

        assert result["removed_files"] == 1
        assert result["kept_files"] == 1
        assert not old_zip.exists()
        assert new_zip.exists()

    def test_removes_expired_in_memory_tasks(self, tmp_path, monkeypatch):
        """超过 max_age_hours 的内存任务应被清理"""
        from app.services import export_progress_service as mod
        monkeypatch.setattr(mod, "EXPORT_DIR", tmp_path)

        svc = ExportProgressService()

        old_task = ExportTask(
            task_id="old", project_id="p1", user_id="u1",
            wp_ids=["w1"], total=1,
            created_at=datetime.now(timezone.utc) - timedelta(hours=30),
            completed_at=datetime.now(timezone.utc) - timedelta(hours=29),
            status="complete",
        )
        new_task = ExportTask(
            task_id="new", project_id="p1", user_id="u1",
            wp_ids=["w2"], total=1,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            status="complete",
        )
        svc._tasks[old_task.task_id] = old_task
        svc._tasks[new_task.task_id] = new_task

        result = svc.cleanup_expired(max_age_hours=24.0)
        assert result["removed_tasks"] == 1
        assert "old" not in svc._tasks
        assert "new" in svc._tasks

    def test_no_export_dir_returns_zero(self, tmp_path, monkeypatch):
        """EXPORT_DIR 不存在时不报错，返回 0"""
        from app.services import export_progress_service as mod
        non_existent = tmp_path / "does-not-exist"
        monkeypatch.setattr(mod, "EXPORT_DIR", non_existent)

        svc = ExportProgressService()
        result = svc.cleanup_expired(max_age_hours=24.0)
        assert result == {"removed_files": 0, "removed_tasks": 0, "kept_files": 0}

    def test_custom_max_age(self, tmp_path, monkeypatch):
        """max_age_hours=1 时 2h 前的也算过期"""
        from app.services import export_progress_service as mod
        monkeypatch.setattr(mod, "EXPORT_DIR", tmp_path)

        zip_2h = tmp_path / "2h-task.zip"
        zip_2h.write_bytes(b"x")
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
        os.utime(zip_2h, (old_ts, old_ts))

        svc = ExportProgressService()
        result = svc.cleanup_expired(max_age_hours=1.0)
        assert result["removed_files"] == 1


class TestExportCleanupWorker:
    """export_cleanup_worker run 函数行为（仅冒烟）"""

    def test_resolve_max_age_default(self, monkeypatch):
        from app.workers.export_cleanup_worker import _resolve_max_age_hours
        monkeypatch.delenv("EXPORT_CLEANUP_MAX_AGE_HOURS", raising=False)
        assert _resolve_max_age_hours() == 24.0

    def test_resolve_max_age_from_env(self, monkeypatch):
        from app.workers.export_cleanup_worker import _resolve_max_age_hours
        monkeypatch.setenv("EXPORT_CLEANUP_MAX_AGE_HOURS", "12.5")
        assert _resolve_max_age_hours() == 12.5

    def test_resolve_max_age_invalid_falls_back(self, monkeypatch):
        from app.workers.export_cleanup_worker import _resolve_max_age_hours
        monkeypatch.setenv("EXPORT_CLEANUP_MAX_AGE_HOURS", "not-a-number")
        assert _resolve_max_age_hours() == 24.0

    def test_resolve_max_age_negative_falls_back(self, monkeypatch):
        from app.workers.export_cleanup_worker import _resolve_max_age_hours
        monkeypatch.setenv("EXPORT_CLEANUP_MAX_AGE_HOURS", "-5")
        assert _resolve_max_age_hours() == 24.0

    @pytest.mark.asyncio
    async def test_worker_run_stops_on_event(self, tmp_path, monkeypatch):
        """stop_event.set() 后 run() 应快速退出"""
        import asyncio
        from app.workers import export_cleanup_worker as worker_mod

        # 把 EXPORT_DIR 指到 tmp 防止真删
        from app.services import export_progress_service as svc_mod
        monkeypatch.setattr(svc_mod, "EXPORT_DIR", tmp_path)

        # 缩短 heartbeat 间隔以加速测试
        monkeypatch.setattr(worker_mod, "HEARTBEAT_INTERVAL_SECONDS", 0.05)

        stop_event = asyncio.Event()
        task = asyncio.create_task(worker_mod.run(stop_event))
        await asyncio.sleep(0.1)
        stop_event.set()
        await asyncio.wait_for(task, timeout=2.0)
