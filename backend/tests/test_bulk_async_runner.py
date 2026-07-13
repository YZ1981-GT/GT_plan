"""Unit tests for bulk_async_runner — Task 9.1 异步导出/导入后台任务。

测试覆盖：
  - _run_export 快乐路径：进度 total 回填 + ZIP 落盘 + 结果路径 + complete
  - _run_export 异常路径：fail 标记 + error 记录
  - _run_import 快乐路径：run() 调用 + commit + result 存储 + complete
  - _run_import all-or-nothing atomicity 透传
  - _run_import 用户不存在 → fail
  - schedule_* 返回 task_id 且登记到 progress 服务

关联需求：6.1, 6.2, 4.2
"""
from __future__ import annotations

import io
import uuid
import zipfile
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.bulk_tab import bulk_async_runner
from app.services.bulk_tab.bulk_progress import bulk_progress_service
from app.services.bulk_tab.snapshot_guard import AtomicityMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSession:
    """假 AsyncSession，支持 async with + commit/execute。"""

    def __init__(self, user=None):
        self._user = user
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        self.committed = True

    async def execute(self, *_a, **_k):
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._user
        return result


def _fake_session_factory(user=None):
    """返回一个可调用工厂：调用即产生新的假会话 (async context manager)。"""
    session = _FakeSession(user=user)

    def factory():
        return session

    return factory, session


def _make_manifest_stub(n_exportable: int):
    m = MagicMock()
    m.exportable.return_value = list(range(n_exportable))
    return m


def _make_zip_bytes(n_files: int) -> bytes:
    buf = io.BytesIO()
    files = [{"sheet_code": f"D2-{i}", "zip_path": f"D/D2/x{i}.xlsx"} for i in range(n_files)]
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"files": files, "cycles": ["D"]}))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_export_happy_path(tmp_path, monkeypatch):
    """_run_export：total 回填 + ZIP 落盘 + result_path + complete。"""
    monkeypatch.setattr(bulk_async_runner, "BULK_EXPORT_DIR", tmp_path)
    factory, _ = _fake_session_factory()
    monkeypatch.setattr(bulk_async_runner, "async_session_factory", factory)

    task = bulk_progress_service.create_task("proj-1", "user-1", "export-data", total=0)

    zip_buf = io.BytesIO(b"PK-fake-zip-bytes")
    with patch(
        "app.services.bulk_tab.manifest_builder.build_manifest",
        AsyncMock(return_value=_make_manifest_stub(5)),
    ), patch(
        "app.services.bulk_tab.bulk_export_service.export",
        AsyncMock(return_value=zip_buf),
    ):
        await bulk_async_runner._run_export(
            task.task_id,
            project_id=uuid.uuid4(),
            cycles=["D"],
            mode="data",
            only_with_data=False,
            exported_by="tester",
            platform_version="v1",
            audit_year=2025,
            filename="项目_2025_底稿批量数据.zip",
        )

    t = bulk_progress_service.get_task(task.task_id)
    assert t.status == "complete"
    assert t.total == 5  # manifest 预建回填
    assert t.result_path is not None
    assert Path(t.result_path).exists()
    assert Path(t.result_path).read_bytes() == b"PK-fake-zip-bytes"
    assert t.result_filename == "项目_2025_底稿批量数据.zip"


@pytest.mark.asyncio
async def test_run_export_failure(tmp_path, monkeypatch):
    """_run_export：export 抛异常 → fail 标记 + error。"""
    monkeypatch.setattr(bulk_async_runner, "BULK_EXPORT_DIR", tmp_path)
    factory, _ = _fake_session_factory()
    monkeypatch.setattr(bulk_async_runner, "async_session_factory", factory)

    task = bulk_progress_service.create_task("proj-1", "user-1", "export-data", total=0)

    with patch(
        "app.services.bulk_tab.manifest_builder.build_manifest",
        AsyncMock(return_value=_make_manifest_stub(3)),
    ), patch(
        "app.services.bulk_tab.bulk_export_service.export",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await bulk_async_runner._run_export(
            task.task_id,
            project_id=uuid.uuid4(),
            cycles=None,
            mode="template",
            only_with_data=False,
            exported_by="tester",
            platform_version="v1",
            audit_year=2025,
            filename="x.zip",
        )

    t = bulk_progress_service.get_task(task.task_id)
    assert t.status == "failed"
    assert "boom" in (t.error or "")
    assert t.result_path is None


# ---------------------------------------------------------------------------
# 导入
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_import_happy_path(monkeypatch):
    """_run_import：run() 被调用 + commit + result 存储 + complete。"""
    user = MagicMock()
    user.id = uuid.uuid4()
    factory, session = _fake_session_factory(user=user)
    monkeypatch.setattr(bulk_async_runner, "async_session_factory", factory)

    task = bulk_progress_service.create_task("proj-1", "user-1", "import", total=0)

    report = MagicMock()
    report.to_dict.return_value = {"import_id": "imp-1", "summary": {"success": 2}}
    report.summary = {"success": 2}

    run_mock = AsyncMock(return_value=report)
    with patch("app.services.bulk_tab.bulk_import_service.run", run_mock):
        await bulk_async_runner._run_import(
            task.task_id,
            project_id=uuid.uuid4(),
            zip_bytes=_make_zip_bytes(2),
            strategy="overwrite",
            atomicity=AtomicityMode.PER_SHEET,
            user_id=user.id,
            username="tester",
            role_value="manager",
        )

    t = bulk_progress_service.get_task(task.task_id)
    assert t.status == "complete"
    assert t.total == 2  # ZIP manifest 预读回填
    assert t.result == {"import_id": "imp-1", "summary": {"success": 2}}
    assert session.committed is True
    # atomicity 透传
    assert run_mock.call_args.kwargs["atomicity"] == AtomicityMode.PER_SHEET


@pytest.mark.asyncio
async def test_run_import_all_or_nothing_passed(monkeypatch):
    """_run_import：all-or-nothing atomicity 正确透传给 run()。"""
    user = MagicMock()
    user.id = uuid.uuid4()
    factory, _ = _fake_session_factory(user=user)
    monkeypatch.setattr(bulk_async_runner, "async_session_factory", factory)

    task = bulk_progress_service.create_task("proj-1", "user-1", "import", total=0)
    report = MagicMock()
    report.to_dict.return_value = {}
    report.summary = {}

    run_mock = AsyncMock(return_value=report)
    with patch("app.services.bulk_tab.bulk_import_service.run", run_mock):
        await bulk_async_runner._run_import(
            task.task_id,
            project_id=uuid.uuid4(),
            zip_bytes=_make_zip_bytes(1),
            strategy="reject",
            atomicity=AtomicityMode.ALL_OR_NOTHING,
            user_id=user.id,
            username="tester",
            role_value="admin",
        )

    assert run_mock.call_args.kwargs["atomicity"] == AtomicityMode.ALL_OR_NOTHING
    assert run_mock.call_args.kwargs["strategy"] == "reject"


@pytest.mark.asyncio
async def test_run_import_user_not_found(monkeypatch):
    """_run_import：worker session 查不到 user → fail。"""
    factory, _ = _fake_session_factory(user=None)
    monkeypatch.setattr(bulk_async_runner, "async_session_factory", factory)

    task = bulk_progress_service.create_task("proj-1", "user-1", "import", total=0)

    with patch("app.services.bulk_tab.bulk_import_service.run", AsyncMock()) as run_mock:
        await bulk_async_runner._run_import(
            task.task_id,
            project_id=uuid.uuid4(),
            zip_bytes=_make_zip_bytes(1),
            strategy="overwrite",
            atomicity=AtomicityMode.PER_SHEET,
            user_id=uuid.uuid4(),
            username="ghost",
            role_value="manager",
        )

    t = bulk_progress_service.get_task(task.task_id)
    assert t.status == "failed"
    assert "用户不存在" in (t.error or "")
    run_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# schedule_* 受理（无 running loop 时 _spawn 返回 None，仍返回 task_id）
# ---------------------------------------------------------------------------


def test_schedule_export_returns_task_id(monkeypatch):
    """schedule_export 登记任务并返回 task_id（不依赖后台执行）。"""
    monkeypatch.setattr(bulk_async_runner, "_spawn", lambda coro: coro.close() or None)

    task_id = bulk_async_runner.schedule_export(
        project_id=uuid.uuid4(),
        cycles=["D"],
        mode="template",
        only_with_data=False,
        exported_by="tester",
        platform_version="v1",
        audit_year=2025,
        user_id="user-1",
        filename="x.zip",
    )
    assert bulk_progress_service.get_task(task_id) is not None
    assert bulk_progress_service.get_task(task_id).operation == "export-template"


def test_schedule_import_returns_task_id(monkeypatch):
    """schedule_import 登记任务并返回 task_id。"""
    monkeypatch.setattr(bulk_async_runner, "_spawn", lambda coro: coro.close() or None)

    task_id = bulk_async_runner.schedule_import(
        project_id=uuid.uuid4(),
        zip_bytes=_make_zip_bytes(1),
        strategy="overwrite",
        atomicity=AtomicityMode.PER_SHEET,
        user_id=uuid.uuid4(),
        username="tester",
        role_value="manager",
    )
    assert bulk_progress_service.get_task(task_id) is not None
    assert bulk_progress_service.get_task(task_id).operation == "import"
