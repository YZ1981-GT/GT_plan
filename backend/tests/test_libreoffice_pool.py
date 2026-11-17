"""LibreOffice 有界异步执行器测试。

子进程层是 ``subprocess.Popen`` + ``asyncio.to_thread``（Windows Selector 循环
不支持 ``asyncio.create_subprocess_exec``），所以这里的假进程是**同步**对象，
测试替换的落点是 ``pool._spawn_process``。
"""
from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote, urlparse

import pytest
from fastapi import HTTPException

from app.services import libreoffice_pool as pool


@pytest.fixture(autouse=True)
def _fresh_pool_state():
    original = (
        pool._libreoffice_semaphore,
        pool.LIBREOFFICE_MAX_CONCURRENCY,
        pool.LIBREOFFICE_MAX_QUEUE,
        pool.LIBREOFFICE_REAP_TIMEOUT_SECONDS,
    )
    pool._libreoffice_semaphore = asyncio.Semaphore(2)
    pool.LIBREOFFICE_MAX_CONCURRENCY = 2
    pool.LIBREOFFICE_MAX_QUEUE = 8
    pool.LIBREOFFICE_REAP_TIMEOUT_SECONDS = 0.2
    pool._queue_waiters = 0
    pool._active_conversions = 0
    pool._waiter_started.clear()
    pool._preview_locks.clear()
    pool.reset_cached_path()
    yield
    (
        pool._libreoffice_semaphore,
        pool.LIBREOFFICE_MAX_CONCURRENCY,
        pool.LIBREOFFICE_MAX_QUEUE,
        pool.LIBREOFFICE_REAP_TIMEOUT_SECONDS,
    ) = original
    pool._queue_waiters = 0
    pool._active_conversions = 0
    pool._waiter_started.clear()
    pool._preview_locks.clear()
    pool.reset_cached_path()


class _FakeProcess:
    """同步假进程：接口对齐 ``subprocess.Popen`` 的被用子集。"""

    def __init__(self, cmd, *, delay: float = 0.0, release=None, returncode=0):
        self.cmd = list(cmd)
        self.pid = 4242
        self.delay = delay
        self.release = release
        self.returncode = None
        self.final_returncode = returncode
        self.killed = False

    def kill(self):
        self.killed = True
        self.returncode = -9
        if self.release is not None:
            self.release.set()

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            if self.release is not None:
                self.release.wait(timeout=timeout)
            if not self.killed:
                self.returncode = self.final_returncode
        return self.returncode

    def communicate(self, timeout=None):
        if self.release is not None:
            self.release.wait(timeout=timeout)
        if self.delay:
            time.sleep(self.delay)
        if not self.killed:
            self.returncode = self.final_returncode
            if self.returncode == 0:
                outdir = Path(self.cmd[self.cmd.index("--outdir") + 1])
                source = Path(self.cmd[-1])
                output_format = self.cmd[self.cmd.index("--convert-to") + 1]
                suffix = output_format.split(":", 1)[0]
                (outdir / f"{source.stem}.{suffix}").write_bytes(b"converted")
        stderr = b"format error" if self.returncode else b""
        return b"stdout", stderr


def _profile_path(command: list[str]) -> Path:
    argument = next(item for item in command if item.startswith("-env:UserInstallation="))
    uri = argument.split("=", 1)[1]
    parsed = urlparse(uri)
    path = unquote(parsed.path)
    if parsed.netloc:
        path = f"//{parsed.netloc}{path}"
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return Path(path)


@pytest.mark.asyncio
async def test_real_executor_limits_concurrency_and_uses_unique_profiles(tmp_path):
    active = 0
    maximum = 0
    commands: list[list[str]] = []
    lock = threading.Lock()

    class TrackingProcess(_FakeProcess):
        def communicate(self, timeout=None):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                return super().communicate(timeout=timeout)
            finally:
                with lock:
                    active -= 1

    def spawn(cmd):
        commands.append(list(cmd))
        return TrackingProcess(cmd, delay=0.02)

    sources = []
    for index in range(5):
        source = tmp_path / f"source-{index}.docx"
        source.write_bytes(b"office")
        sources.append(source)

    with patch.object(pool, "_find_soffice", return_value="soffice"), patch.object(
        pool, "_spawn_process", new=spawn
    ):
        payloads = await asyncio.gather(
            *(
                pool.convert_office_to_pdf_bytes(
                    source, timeout=1, queue_timeout=1
                )
                for source in sources
            )
        )

    assert payloads == [b"converted"] * 5
    assert maximum == 2
    profile_paths = [_profile_path(command) for command in commands]
    assert len({str(path) for path in profile_paths}) == 5
    assert all(not path.parent.exists() for path in profile_paths)
    assert pool.get_capacity_snapshot()["active"] == 0
    assert pool.get_capacity_snapshot()["waiting"] == 0


@pytest.mark.asyncio
async def test_conversion_keeps_event_loop_responsive(tmp_path):
    source = tmp_path / "source.docx"
    source.write_bytes(b"office")
    ticked = asyncio.Event()

    def spawn(cmd):
        return _FakeProcess(cmd, delay=0.03)

    async def ticker():
        await asyncio.sleep(0.005)
        ticked.set()

    with patch.object(pool, "_find_soffice", return_value="soffice"), patch.object(
        pool, "_spawn_process", new=spawn
    ):
        payload, _ = await asyncio.gather(
            pool.convert_office_to_pdf_bytes(source, timeout=1),
            ticker(),
        )

    assert payload == b"converted"
    assert ticked.is_set()


@pytest.mark.asyncio
async def test_queue_full_and_acquire_timeout_return_retryable_503(monkeypatch):
    pool._libreoffice_semaphore = asyncio.Semaphore(1)
    pool.LIBREOFFICE_MAX_CONCURRENCY = 1
    pool.LIBREOFFICE_MAX_QUEUE = 1

    await pool._acquire_slot(1)
    waiter = asyncio.create_task(pool._acquire_slot(1))
    for _ in range(50):
        if pool.get_queue_depth() == 1:
            break
        await asyncio.sleep(0)

    assert pool.get_queue_depth() == 1
    assert pool.get_capacity_snapshot()["oldest_wait_seconds"] >= 0

    with pytest.raises(HTTPException) as full_error:
        await pool._acquire_slot(1)
    assert full_error.value.status_code == 503
    assert full_error.value.detail["reason"] == "libreoffice_queue_full"
    assert full_error.value.headers["Retry-After"]

    pool._release_slot()
    await waiter
    pool._release_slot()

    pool._libreoffice_semaphore = asyncio.Semaphore(0)
    with pytest.raises(HTTPException) as timeout_error:
        await pool._acquire_slot(0.01)
    assert timeout_error.value.status_code == 503
    assert timeout_error.value.detail["reason"] == "libreoffice_queue_timeout"
    assert pool.get_queue_depth() == 0


@pytest.mark.asyncio
async def test_timeout_kills_reaps_and_releases_slot(tmp_path):
    source = tmp_path / "slow.docx"
    source.write_bytes(b"office")
    release = threading.Event()
    spawned: list[_FakeProcess] = []

    def spawn(cmd):
        process = _FakeProcess(cmd, release=release)
        spawned.append(process)
        return process

    with patch.object(pool, "_find_soffice", return_value="soffice"), patch.object(
        pool, "_kill_blocking", side_effect=lambda proc: proc.kill()
    ), patch.object(pool, "_spawn_process", new=spawn):
        with pytest.raises(HTTPException) as exc_info:
            await pool.convert_office_to_pdf_bytes(source, timeout=0.01)

    assert exc_info.value.status_code == 504
    assert exc_info.value.detail["reason"] == "libreoffice_timeout"
    assert exc_info.value.headers["Retry-After"]
    assert spawned[0].killed is True
    assert pool.get_capacity_snapshot()["active"] == 0


@pytest.mark.asyncio
async def test_cancellation_kills_process_and_removes_job_directory(tmp_path):
    source = tmp_path / "cancel.docx"
    source.write_bytes(b"office")
    release = threading.Event()
    started = asyncio.Event()
    loop = asyncio.get_running_loop()
    spawned: list[_FakeProcess] = []
    job_roots: list[Path] = []

    def spawn(cmd):
        process = _FakeProcess(cmd, release=release)
        spawned.append(process)
        job_roots.append(Path(cmd[cmd.index("--outdir") + 1]).parent)
        loop.call_soon_threadsafe(started.set)
        return process

    with patch.object(pool, "_find_soffice", return_value="soffice"), patch.object(
        pool, "_kill_blocking", side_effect=lambda proc: proc.kill()
    ), patch.object(pool, "_spawn_process", new=spawn):
        task = asyncio.create_task(
            pool.convert_office_to_pdf_bytes(source, timeout=10)
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert spawned[0].killed is True
    assert all(not root.exists() for root in job_roots)
    assert pool.get_capacity_snapshot()["active"] == 0


@pytest.mark.asyncio
async def test_preview_cache_singleflight_and_atomic_publish(tmp_path):
    source = tmp_path / "same.docx"
    source.write_bytes(b"office")
    cache = tmp_path / "cache" / "same.pdf"

    async def convert(*_args, **_kwargs):
        await asyncio.sleep(0.01)
        return b"%PDF-complete"

    with patch.object(
        pool,
        "convert_office_to_pdf_bytes",
        new=AsyncMock(side_effect=convert),
    ) as convert_mock:
        results = await asyncio.gather(
            pool.get_or_create_preview_pdf(source, cache),
            pool.get_or_create_preview_pdf(source, cache),
        )

    assert sorted(status for _, status in results) == ["hit", "miss"]
    assert all(payload == b"%PDF-complete" for payload, _ in results)
    assert convert_mock.await_count == 1
    assert cache.read_bytes() == b"%PDF-complete"
    assert not list(cache.parent.glob("*.tmp"))


@pytest.mark.asyncio
async def test_nonzero_exit_surfaces_stderr_and_releases_slot(tmp_path):
    source = tmp_path / "broken.docx"
    source.write_bytes(b"office")

    def spawn(cmd):
        return _FakeProcess(cmd, returncode=1)

    with patch.object(pool, "_find_soffice", return_value="soffice"), patch.object(
        pool, "_spawn_process", new=spawn
    ):
        with pytest.raises(HTTPException) as exc_info:
            await pool.convert_office_to_pdf_bytes(source)

    assert exc_info.value.status_code == 500
    assert "format error" in str(exc_info.value.detail)
    assert pool.get_capacity_snapshot()["active"] == 0


@pytest.mark.asyncio
async def test_convert_with_libreoffice_atomically_replaces_xlsx(tmp_path):
    source = tmp_path / "book.xlsx"
    source.write_bytes(b"original")

    def spawn(cmd):
        assert "--calc" in cmd
        return _FakeProcess(cmd)

    with patch.object(pool, "_find_soffice", return_value="soffice"), patch.object(
        pool, "_spawn_process", new=spawn
    ):
        result = await pool.convert_with_libreoffice(source)

    assert result == source
    assert source.read_bytes() == b"converted"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.asyncio
async def test_spawn_failure_maps_to_retryable_503(tmp_path):
    """Selector 循环上 ``create_subprocess_exec`` 抛的 NotImplementedError 必须被接住。"""
    source = tmp_path / "never.docx"
    source.write_bytes(b"office")

    def spawn(_cmd):
        raise NotImplementedError

    with patch.object(pool, "_find_soffice", return_value="soffice"), patch.object(
        pool, "_spawn_process", new=spawn
    ):
        with pytest.raises(HTTPException) as exc_info:
            await pool.convert_office_to_pdf_bytes(source)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["reason"] == "libreoffice_start_failed"
    assert pool.get_capacity_snapshot()["active"] == 0


def test_process_group_kwargs_are_platform_specific(monkeypatch):
    """子进程必须进独立进程组，否则杀不掉 soffice 派生的子进程。"""
    monkeypatch.setattr(pool.os, "name", "nt")
    kwargs = pool._process_group_kwargs()
    assert kwargs["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP

    monkeypatch.setattr(pool.os, "name", "posix")
    assert pool._process_group_kwargs() == {"start_new_session": True}


@pytest.mark.asyncio
async def test_kill_blocking_uses_taskkill_tree_on_windows(monkeypatch):
    """Windows ``TerminateProcess`` 不连带子进程 ⇒ 必须 ``taskkill /T``。"""
    calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        calls.append(list(args))

        class _Result:
            returncode = 0

        return _Result()

    proc = _FakeProcess(["soffice"])
    monkeypatch.setattr(pool.os, "name", "nt")
    monkeypatch.setattr(pool.subprocess, "run", fake_run)

    await asyncio.to_thread(pool._kill_blocking, proc)

    assert calls and calls[0][:1] == ["taskkill"]
    assert "/T" in calls[0] and "/F" in calls[0]


def test_spawn_process_passes_process_group_to_popen(monkeypatch):
    """树杀依赖独立进程组：``_spawn_process`` 必须把 kwargs 真的交给 Popen。

    只测 ``_process_group_kwargs`` 的返回值抓不到「忘了传」这一层
    （变异：删掉 ``**_process_group_kwargs()`` 后该用例原本全绿）。
    """
    captured: dict[str, object] = {}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured.update(kwargs)

    monkeypatch.setattr(pool.os, "name", "nt")
    monkeypatch.setattr(pool.subprocess, "Popen", _FakePopen)

    pool._spawn_process(["soffice", "--headless"])

    assert captured["cmd"] == ["soffice", "--headless"]
    assert captured["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
    assert captured["stdout"] is subprocess.PIPE
    assert captured["stderr"] is subprocess.PIPE


def test_find_soffice_and_profile_uri(tmp_path, monkeypatch):
    profile = tmp_path / "带 空格" / "profile"
    profile.mkdir(parents=True)
    uri = pool._build_user_installation(profile)
    assert uri.startswith("file:")
    assert "%20" in uri

    pool.reset_cached_path()
    monkeypatch.setenv("LIBREOFFICE_PATH", str(tmp_path / "soffice"))
    with patch.object(Path, "exists", return_value=True):
        assert pool.find_soffice_path() == str(tmp_path / "soffice")


def test_queue_depth_header_reflects_waiters(monkeypatch):
    monkeypatch.setattr(pool, "_queue_waiters", 2)
    assert pool.get_queue_depth_header() == {"X-Recompute-Queue-Depth": "2"}


@pytest.mark.asyncio
async def test_startup_health_check_is_nonblocking_probe_only():
    with patch.object(pool, "_find_soffice", return_value="soffice"), patch.object(
        pool, "_spawn_process", new=AsyncMock()
    ) as spawn:
        await pool.startup_health_check()
    spawn.assert_not_called()
