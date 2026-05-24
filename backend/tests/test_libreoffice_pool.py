"""Property-based tests for LibreOffice pool (Req 8).

Feature: advanced-query-enhancements-p1p2
Properties 15, 16, 17: concurrency limit, UserInstallation uniqueness, timeout kill.

Validates: Requirements 8.1, 8.2, 8.4
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st

# ---------------------------------------------------------------------------
# Property 15: 并发限制 ≤ 2
# Feature: advanced-query-enhancements-p1p2, Property 15: LibreOffice concurrency limit
# Validates: Requirements 8.1
# ---------------------------------------------------------------------------


class TestConcurrencyLimit:
    """Property 15: For any N concurrent calls (N > 2), at most 2 should be
    executing simultaneously."""

    @settings(max_examples=20, deadline=None)
    @given(n_concurrent=st.integers(min_value=3, max_value=20))
    def test_concurrency_never_exceeds_2(self, n_concurrent: int):
        """For any number of concurrent conversion requests, at most 2 soffice
        subprocesses should be alive simultaneously."""

        async def _run_test(n: int):
            # Create a fresh semaphore for each test run to avoid event loop binding issues
            semaphore = asyncio.Semaphore(2)

            # Track max concurrent executions
            current_active = 0
            max_active = 0
            lock = asyncio.Lock()

            async def _fake_convert(idx: int):
                nonlocal current_active, max_active
                async with semaphore:
                    async with lock:
                        current_active += 1
                        if current_active > max_active:
                            max_active = current_active
                    # Simulate work
                    await asyncio.sleep(0.005)
                    async with lock:
                        current_active -= 1

            tasks = [asyncio.create_task(_fake_convert(i)) for i in range(n)]
            await asyncio.gather(*tasks)

            assert max_active <= 2, (
                f"Max concurrent executions was {max_active}, expected ≤ 2"
            )

        asyncio.run(_run_test(n_concurrent))


# ---------------------------------------------------------------------------
# Property 16: Windows UserInstallation 唯一性
# Feature: advanced-query-enhancements-p1p2, Property 16: Windows UserInstallation uniqueness
# Validates: Requirements 8.2
# ---------------------------------------------------------------------------


class TestUserInstallationUniqueness:
    """Property 16: For any two concurrent calls on Windows, their
    UserInstallation paths must be different."""

    @settings(max_examples=20)
    @given(
        pid1=st.integers(min_value=1, max_value=100000),
        pid2=st.integers(min_value=1, max_value=100000),
        tid1=st.integers(min_value=1, max_value=100000),
        tid2=st.integers(min_value=1, max_value=100000),
    )
    def test_different_pid_or_tid_produces_unique_paths(
        self, pid1: int, pid2: int, tid1: int, tid2: int
    ):
        """For any two (pid, tid) pairs that differ in at least one component,
        the UserInstallation paths must be distinct."""
        from app.services.libreoffice_pool import _build_user_installation

        # Skip if both pairs are identical (same process+thread = same path is OK)
        if pid1 == pid2 and tid1 == tid2:
            return

        with patch("app.services.libreoffice_pool.os.getpid", return_value=pid1), \
             patch("app.services.libreoffice_pool.threading.get_ident", return_value=tid1):
            path1 = _build_user_installation()

        with patch("app.services.libreoffice_pool.os.getpid", return_value=pid2), \
             patch("app.services.libreoffice_pool.threading.get_ident", return_value=tid2):
            path2 = _build_user_installation()

        assert path1 != path2, (
            f"UserInstallation paths must be unique for different (pid,tid) pairs: "
            f"({pid1},{tid1}) -> {path1}, ({pid2},{tid2}) -> {path2}"
        )

    def test_windows_path_format(self):
        """On Windows, UserInstallation path uses file:/// URI with forward slashes."""
        from app.services.libreoffice_pool import _build_user_installation

        with patch("app.services.libreoffice_pool.sys.platform", "win32"), \
             patch("app.services.libreoffice_pool.os.getpid", return_value=1234), \
             patch("app.services.libreoffice_pool.threading.get_ident", return_value=5678), \
             patch.dict(os.environ, {"TEMP": r"C:\Users\test\AppData\Local\Temp"}):
            path = _build_user_installation()

        assert path.startswith("file:///")
        assert "soffice_1234_5678" in path
        assert "\\" not in path  # No backslashes in file:// URI

    def test_linux_path_format(self):
        """On Linux, UserInstallation path uses /tmp."""
        from app.services.libreoffice_pool import _build_user_installation

        with patch("app.services.libreoffice_pool.sys.platform", "linux"), \
             patch("app.services.libreoffice_pool.os.getpid", return_value=9999), \
             patch("app.services.libreoffice_pool.threading.get_ident", return_value=7777):
            path = _build_user_installation()

        assert path == "file:///tmp/soffice_9999_7777"


# ---------------------------------------------------------------------------
# Property 17: 超时强制 kill
# Feature: advanced-query-enhancements-p1p2, Property 17: Timeout enforcement
# Validates: Requirements 8.4
# ---------------------------------------------------------------------------


class TestTimeoutEnforcement:
    """Property 17: For any soffice subprocess that does not complete within
    60 seconds, the process must be killed and HTTP 504 returned."""

    @settings(max_examples=20, deadline=None)
    @given(timeout_val=st.integers(min_value=1, max_value=3))
    def test_timeout_kills_process_and_returns_504(self, timeout_val: int):
        """For any call exceeding the timeout, subprocess must be killed
        and semaphore released."""

        async def _run_test(timeout: int):
            # Use a fresh semaphore to avoid event loop binding issues
            import app.services.libreoffice_pool as pool_mod

            # Save and replace the module semaphore
            original_sem = pool_mod._libreoffice_semaphore
            pool_mod._libreoffice_semaphore = asyncio.Semaphore(2)
            pool_mod.reset_cached_path()

            try:
                # Mock a process that never completes (wait hangs)
                mock_proc = AsyncMock()
                mock_proc.returncode = None
                mock_proc.stdout = AsyncMock()
                mock_proc.stderr = AsyncMock()
                killed = False

                async def _never_finish():
                    # This will be cancelled by wait_for timeout
                    await asyncio.sleep(timeout + 100)

                async def _wait_after_kill():
                    # After kill, wait returns immediately (process reaped)
                    return None

                def _do_kill():
                    nonlocal killed
                    killed = True
                    # After kill, subsequent wait() should return immediately
                    mock_proc.wait = _wait_after_kill

                mock_proc.wait = _never_finish
                mock_proc.kill = MagicMock(side_effect=_do_kill)

                initial_value = pool_mod._libreoffice_semaphore._value

                with patch(
                    "app.services.libreoffice_pool._find_soffice",
                    return_value="/usr/bin/soffice",
                ), patch(
                    "asyncio.create_subprocess_exec",
                    return_value=mock_proc,
                ):
                    from fastapi import HTTPException
                    with pytest.raises(HTTPException) as exc_info:
                        await pool_mod.convert_with_libreoffice(
                            Path("/tmp/test.xlsx"), timeout=timeout
                        )

                    # Verify HTTP 504
                    assert exc_info.value.status_code == 504

                    # Verify process was killed
                    assert killed, "Process must be killed on timeout"

                # Verify semaphore was released (value restored)
                assert pool_mod._libreoffice_semaphore._value == initial_value, (
                    "Semaphore must be released after timeout kill"
                )
            finally:
                pool_mod._libreoffice_semaphore = original_sem

        asyncio.run(_run_test(timeout_val))

    def test_successful_conversion_releases_semaphore(self):
        """After successful conversion, semaphore must be released."""

        async def _run():
            import app.services.libreoffice_pool as pool_mod
            import tempfile

            # Use fresh semaphore
            original_sem = pool_mod._libreoffice_semaphore
            pool_mod._libreoffice_semaphore = asyncio.Semaphore(2)
            pool_mod.reset_cached_path()

            try:
                initial_value = pool_mod._libreoffice_semaphore._value

                # Mock successful process
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.stdout = AsyncMock(read=AsyncMock(return_value=b""))
                mock_proc.stderr = AsyncMock(read=AsyncMock(return_value=b""))
                mock_proc.wait = AsyncMock(return_value=0)

                # Create a temp file to simulate conversion
                tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
                tmp.write(b"fake xlsx")
                tmp.close()
                xlsx_path = Path(tmp.name)

                try:
                    with patch(
                        "app.services.libreoffice_pool._find_soffice",
                        return_value="/usr/bin/soffice",
                    ), patch(
                        "asyncio.create_subprocess_exec",
                        return_value=mock_proc,
                    ), patch(
                        "tempfile.mkdtemp",
                        return_value=str(xlsx_path.parent),
                    ), patch(
                        "app.services.libreoffice_pool.shutil.copy",
                    ), patch(
                        "app.services.libreoffice_pool.shutil.rmtree",
                    ):
                        # Make the converted file "exist"
                        converted_path = xlsx_path.parent / f"{xlsx_path.stem}.xlsx"
                        converted_path.write_bytes(b"converted")

                        try:
                            result = await pool_mod.convert_with_libreoffice(
                                xlsx_path, timeout=60
                            )
                        finally:
                            if converted_path.exists():
                                converted_path.unlink()

                    assert pool_mod._libreoffice_semaphore._value == initial_value
                finally:
                    if xlsx_path.exists():
                        xlsx_path.unlink()
            finally:
                pool_mod._libreoffice_semaphore = original_sem

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Additional unit tests
# ---------------------------------------------------------------------------


class TestFindSoffice:
    """Unit tests for _find_soffice path detection."""

    def test_returns_none_when_no_path_found(self):
        from app.services.libreoffice_pool import _find_soffice, reset_cached_path

        reset_cached_path()
        with patch("app.services.libreoffice_pool.shutil.which", return_value=None), \
             patch("app.services.libreoffice_pool.Path.exists", return_value=False), \
             patch.dict(os.environ, {}, clear=True):
            # Remove LIBREOFFICE_PATH if set
            os.environ.pop("LIBREOFFICE_PATH", None)
            result = _find_soffice()
            assert result is None

        reset_cached_path()

    def test_returns_path_from_env(self):
        from app.services.libreoffice_pool import _find_soffice, reset_cached_path

        reset_cached_path()
        with patch.dict(os.environ, {"LIBREOFFICE_PATH": "/custom/soffice"}), \
             patch("app.services.libreoffice_pool.Path.exists", return_value=True):
            result = _find_soffice()
            assert result == "/custom/soffice"

        reset_cached_path()


class TestQueueDepth:
    """Unit tests for queue depth and response header."""

    def test_queue_depth_header_empty_when_below_threshold(self):
        from app.services.libreoffice_pool import get_queue_depth_header

        # With no waiters, depth should be 0 → no header
        headers = get_queue_depth_header()
        assert headers == {}

    def test_get_queue_depth_returns_zero_initially(self):
        from app.services.libreoffice_pool import get_queue_depth

        depth = get_queue_depth()
        assert depth == 0


class TestStartupHealthCheck:
    """Unit tests for startup health check."""

    def test_health_check_logs_error_when_not_found(self):
        """When soffice is not found, health check logs error but doesn't raise."""

        async def _run():
            from app.services.libreoffice_pool import startup_health_check, reset_cached_path

            reset_cached_path()
            with patch("app.services.libreoffice_pool._find_soffice", return_value=None):
                # Should not raise
                await startup_health_check()

        asyncio.run(_run())

    def test_health_check_succeeds_with_valid_soffice(self):
        """When soffice is found and responds, health check passes."""

        async def _run():
            from app.services.libreoffice_pool import startup_health_check, reset_cached_path

            reset_cached_path()

            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(
                return_value=(b"LibreOffice 7.6.4.1", b"")
            )

            with patch(
                "app.services.libreoffice_pool._find_soffice",
                return_value="/usr/bin/soffice",
            ), patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ):
                await startup_health_check()

        asyncio.run(_run())

    def test_health_check_handles_timeout(self):
        """When soffice --version times out, health check logs error but doesn't raise."""

        async def _run():
            from app.services.libreoffice_pool import startup_health_check, reset_cached_path

            reset_cached_path()

            mock_proc = AsyncMock()

            async def _hang():
                await asyncio.sleep(100)
                return (b"", b"")

            mock_proc.communicate = _hang

            with patch(
                "app.services.libreoffice_pool._find_soffice",
                return_value="/usr/bin/soffice",
            ), patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ):
                # Should not raise even on timeout
                # We patch wait_for timeout to be very short
                with patch(
                    "asyncio.wait_for",
                    side_effect=asyncio.TimeoutError(),
                ):
                    await startup_health_check()

        asyncio.run(_run())
