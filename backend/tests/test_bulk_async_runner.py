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
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import UploadFile

import pytest

from app.services.bulk_tab import bulk_async_runner
from app.services.bulk_tab.bulk_progress import bulk_progress_service
from app.services.bulk_tab.snapshot_guard import AtomicityMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_import_reservations():
    """测试间隔离单 worker 的临时 admission 状态。"""
    bulk_async_runner._IMPORT_RESERVATIONS.clear()
    yield
    bulk_async_runner._IMPORT_RESERVATIONS.clear()


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


# ---------------------------------------------------------------------------
# 密码保护 fail-closed（spec environment-hygiene-deps-and-scratch-schemas Requirement 4.3）
#
# 走**真** bulk_export_service.export（不 patch 它）：要求密码而缺 pyzipper 时，后台任务必须
# 失败、错误文本就是中文原因（不带「503: 」前缀 —— runner 用 ``str(exc)`` 写错误）、且不落 ZIP。
# 旧实现在同一情形下会「导出完成」并落一个**明文** ZIP。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_export_with_password_but_no_pyzipper_fails_without_writing_zip(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(bulk_async_runner, "BULK_EXPORT_DIR", tmp_path / "bulk_exports")
    factory, _ = _fake_session_factory()
    monkeypatch.setattr(bulk_async_runner, "async_session_factory", factory)
    monkeypatch.setitem(sys.modules, "pyzipper", None)  # import pyzipper → ImportError

    task = bulk_progress_service.create_task("proj-1", "user-1", "export-data", total=0)
    build = AsyncMock(return_value=_make_manifest_stub(2))
    with patch("app.services.bulk_tab.manifest_builder.build_manifest", build), patch(
        "app.services.bulk_tab.bulk_export_service.build_manifest", build
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
            filename="x.zip",
            # 合法 ASCII 密码：Req 8.3 起中文密码在 export() 第 0 步就被 422 拦掉，
            # 用中文会让本条测的不再是「缺 pyzipper」这条链路
            password="Audit-Pa55!",
        )

    t = bulk_progress_service.get_task(task.task_id)
    assert t.status == "failed"
    assert (t.error or "").startswith("服务器未安装 AES 加密组件"), t.error
    assert t.result_path is None
    assert build.await_count == 1, "只允许 runner 的进度预计数调用一次；导出本身必须在建 manifest 之前失败"
    out_dir = tmp_path / "bulk_exports"
    assert not out_dir.exists() or not any(out_dir.iterdir())


class _ChunkOnlyStream(io.BytesIO):
    """拒绝无界 read()，守护上传不得一次性读完整包。"""

    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        assert size > 0, "异步上传必须按有界块读取"
        self.read_sizes.append(size)
        return super().read(size)


@pytest.mark.asyncio
async def test_spool_import_upload_streams_to_disk_and_closes_upload(
    tmp_path, monkeypatch
):
    zip_bytes = _make_zip_bytes(2)
    stream = _ChunkOnlyStream(zip_bytes)
    upload = UploadFile(file=stream, filename="bulk.zip")
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_DIR", tmp_path)

    spool_path = await bulk_async_runner.spool_import_upload(
        upload,
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )

    assert spool_path.read_bytes() == zip_bytes
    assert stream.read_sizes
    assert max(stream.read_sizes) <= bulk_async_runner.BULK_IMPORT_COPY_CHUNK_BYTES
    assert stream.closed is True
    assert spool_path.suffix == ".zip"
    assert not list(spool_path.parent.glob("*.tmp"))
    capacity = bulk_async_runner.get_import_capacity_snapshot()
    assert capacity["active"] == 1
    assert capacity["oldest_active_age_seconds"] >= 0
    assert capacity["max_copy_memory_bytes"] == (
        bulk_async_runner.BULK_IMPORT_GLOBAL_LIMIT
        * bulk_async_runner.BULK_IMPORT_COPY_CHUNK_BYTES
    )

    await bulk_async_runner.cleanup_import_spool(spool_path)
    assert not spool_path.exists()
    assert bulk_async_runner.get_import_capacity_snapshot()["active"] == 0


@pytest.mark.asyncio
async def test_spool_import_upload_rejects_oversize_and_cleans_partial_file(
    tmp_path, monkeypatch
):
    from app.services.bulk_tab import zip_handler

    payload = _make_zip_bytes(1)
    upload = UploadFile(file=_ChunkOnlyStream(payload), filename="bulk.zip")
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_DIR", tmp_path)
    monkeypatch.setattr(zip_handler, "DEFAULT_MAX_TOTAL_ZIP_SIZE", len(payload) - 1)

    with pytest.raises(Exception) as exc_info:
        await bulk_async_runner.spool_import_upload(
            upload,
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )

    assert getattr(exc_info.value, "status_code", None) == 413
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.asyncio
async def test_run_import_passes_path_and_removes_spool_on_success(
    tmp_path, monkeypatch
):
    user = MagicMock()
    user.id = uuid.uuid4()
    factory, _ = _fake_session_factory(user=user)
    monkeypatch.setattr(bulk_async_runner, "async_session_factory", factory)

    spool_path = tmp_path / "queued.zip"
    spool_path.write_bytes(_make_zip_bytes(1))
    task = bulk_progress_service.create_task("proj-1", "user-1", "import", total=0)
    report = MagicMock()
    report.to_dict.return_value = {"summary": {"success": 1}}
    report.summary = {"success": 1}

    run_mock = AsyncMock(return_value=report)
    with patch("app.services.bulk_tab.bulk_import_service.run", run_mock):
        await bulk_async_runner._run_import(
            task.task_id,
            project_id=uuid.uuid4(),
            zip_bytes=spool_path,
            strategy="overwrite",
            atomicity=AtomicityMode.PER_SHEET,
            user_id=user.id,
            username="tester",
            role_value="manager",
        )

    assert run_mock.call_args.kwargs["zip_bytes"] == spool_path
    assert not spool_path.exists()
    assert bulk_progress_service.get_task(task.task_id).status == "complete"


@pytest.mark.asyncio
async def test_run_import_removes_spool_on_failure(tmp_path, monkeypatch):
    user = MagicMock()
    user.id = uuid.uuid4()
    factory, _ = _fake_session_factory(user=user)
    monkeypatch.setattr(bulk_async_runner, "async_session_factory", factory)

    spool_path = tmp_path / "failed.zip"
    spool_path.write_bytes(_make_zip_bytes(1))
    task = bulk_progress_service.create_task("proj-1", "user-1", "import", total=0)

    with patch(
        "app.services.bulk_tab.bulk_import_service.run",
        AsyncMock(side_effect=RuntimeError("import failed")),
    ):
        await bulk_async_runner._run_import(
            task.task_id,
            project_id=uuid.uuid4(),
            zip_bytes=spool_path,
            strategy="overwrite",
            atomicity=AtomicityMode.PER_SHEET,
            user_id=user.id,
            username="tester",
            role_value="manager",
        )

    assert not spool_path.exists()
    saved = bulk_progress_service.get_task(task.task_id)
    assert saved.status == "failed"
    assert "import failed" in (saved.error or "")


def test_schedule_import_cleans_spool_when_worker_cannot_be_scheduled(
    tmp_path, monkeypatch
):
    spool_path = tmp_path / "orphan.zip"
    spool_path.write_bytes(_make_zip_bytes(1))
    bulk_async_runner._IMPORT_RESERVATIONS[spool_path] = (
        bulk_async_runner._ImportReservation(
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            reserved_bytes=100,
        )
    )
    monkeypatch.setattr(bulk_async_runner, "_spawn", lambda coro: coro.close() or None)

    task_id = bulk_async_runner.schedule_import(
        project_id=uuid.uuid4(),
        zip_bytes=spool_path,
        strategy="overwrite",
        atomicity=AtomicityMode.PER_SHEET,
        user_id=uuid.uuid4(),
        username="tester",
        role_value="manager",
    )

    assert not spool_path.exists()
    assert spool_path not in bulk_async_runner._IMPORT_RESERVATIONS
    task = bulk_progress_service.get_task(task_id)
    assert task.status == "failed"
    assert "调度失败" in (task.error or "")


@pytest.mark.asyncio
async def test_async_import_router_spools_upload_instead_of_reading_all(
    tmp_path, monkeypatch
):
    from app.routers import wp_bulk_router

    project_id = uuid.uuid4()
    user = SimpleNamespace(
        id=uuid.uuid4(),
        username="tester",
        role=SimpleNamespace(value="manager"),
    )
    upload = MagicMock()
    upload.read = AsyncMock(side_effect=AssertionError("不得调用 UploadFile.read()"))
    spool_path = tmp_path / "route-spool.zip"
    spool_path.write_bytes(_make_zip_bytes(1))

    from app.services import platform_job_service

    monkeypatch.setattr(
        wp_bulk_router, "_check_project_importable", AsyncMock(return_value=None)
    )
    spool_mock = AsyncMock(return_value=spool_path)
    monkeypatch.setattr(bulk_async_runner, "spool_import_upload", spool_mock)
    release_mock = AsyncMock()
    monkeypatch.setattr(bulk_async_runner, "release_import_reservation", release_mock)
    monkeypatch.setattr(platform_job_service, "acquire_admission_lock", AsyncMock())
    job_id = uuid.uuid4()
    create_mock = AsyncMock(return_value=(SimpleNamespace(id=job_id), True))
    monkeypatch.setattr(platform_job_service, "create_or_get_job", create_mock)
    capacity_mock = AsyncMock()
    monkeypatch.setattr(platform_job_service, "enforce_active_capacity", capacity_mock)
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    response = await wp_bulk_router.bulk_import_async(
        project_id=project_id,
        file=upload,
        strategy="overwrite",
        all_or_nothing=False,
        idempotency_key="idem-1",
        current_user=user,
        db=db,
    )

    assert response.task_id == str(job_id)
    spool_mock.assert_awaited_once_with(
        upload,
        project_id=project_id,
        user_id=user.id,
    )
    create_kwargs = create_mock.call_args.kwargs
    assert create_kwargs["payload_ref"]["spool_path"] == str(spool_path)
    assert create_kwargs["request_payload"] == {
        "sha256": create_kwargs["payload_ref"]["sha256"],
        "size": len(_make_zip_bytes(1)),
        "strategy": "overwrite",
        "atomicity": AtomicityMode.PER_SHEET.value,
    }
    assert create_kwargs["idempotency_key"] == "idem-1"
    capacity_mock.assert_awaited_once()
    release_mock.assert_awaited_once_with(spool_path)
    db.commit.assert_awaited_once()
    upload.read.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("global_limit", "user_limit", "project_limit", "same_user", "same_project", "reason"),
    [
        (1, 5, 5, False, False, "bulk_import_global_limit"),
        (5, 1, 5, True, False, "bulk_import_user_limit"),
        (5, 5, 1, False, True, "bulk_import_project_limit"),
    ],
)
async def test_import_admission_enforces_global_user_and_project_limits(
    tmp_path,
    monkeypatch,
    global_limit,
    user_limit,
    project_limit,
    same_user,
    same_project,
    reason,
):
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_DIR", tmp_path)
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_GLOBAL_LIMIT", global_limit)
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_USER_LIMIT", user_limit)
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_PROJECT_LIMIT", project_limit)

    project_1 = uuid.uuid4()
    user_1 = uuid.uuid4()
    project_2 = project_1 if same_project else uuid.uuid4()
    user_2 = user_1 if same_user else uuid.uuid4()
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    await bulk_async_runner._reserve_import_spool(
        first,
        project_id=project_1,
        user_id=user_1,
        reserved_bytes=100,
    )
    with pytest.raises(Exception) as exc_info:
        await bulk_async_runner._reserve_import_spool(
            second,
            project_id=project_2,
            user_id=user_2,
            reserved_bytes=100,
        )

    error = exc_info.value
    assert getattr(error, "status_code", None) == 429
    assert error.detail["reason"] == reason
    assert error.headers["Retry-After"] == str(
        bulk_async_runner.BULK_IMPORT_RETRY_AFTER_SECONDS
    )


@pytest.mark.asyncio
async def test_import_admission_enforces_spool_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_DIR", tmp_path)
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_GLOBAL_LIMIT", 5)
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_USER_LIMIT", 5)
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_PROJECT_LIMIT", 5)
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_SPOOL_BUDGET_BYTES", 150)

    await bulk_async_runner._reserve_import_spool(
        tmp_path / "first.zip",
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        reserved_bytes=100,
    )
    with pytest.raises(Exception) as exc_info:
        await bulk_async_runner._reserve_import_spool(
            tmp_path / "second.zip",
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            reserved_bytes=100,
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["reason"] == "bulk_import_spool_budget"
