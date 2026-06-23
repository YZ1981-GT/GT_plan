"""Integration test: concurrent writes across different paths → one 409

Validates: Requirements 2.2, 2.3

模拟 html_save + univer_save 同时写同一底稿（相同 expected_version）→ 恰好一个 409。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck

from app.services.workpaper_save_orchestrator import (
    OptimisticLockError,
    WorkpaperSaveOrchestrator,
)


def _make_wp(file_version: int = 1) -> MagicMock:
    wp = MagicMock()
    wp.id = uuid.uuid4()
    wp.project_id = uuid.uuid4()
    wp.file_version = file_version
    wp.prefill_stale = False
    wp.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return wp


def _make_user(name: str = "user") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = name
    return user


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def _patch_event_bus():
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()
    with patch("app.services.event_bus.event_bus", mock_bus):
        yield mock_bus


class TestConcurrentWritesAcrossPaths:
    """并发写同一底稿（不同路径）→ 后提交者 409"""

    @pytest.mark.asyncio
    async def test_html_save_vs_univer_save(self):
        """html_save + univer_save 同时写同一底稿 → 一个成功一个 409"""
        wp = _make_wp(file_version=5)
        db = _make_db()
        user_a = _make_user("editor_a")
        user_b = _make_user("editor_b")

        orch = WorkpaperSaveOrchestrator()

        # 第一个写入：html_save（成功）
        new_ver = await orch.after_save(
            db, wp, user_a,
            trigger="html_save",
            extra={"sheet_name": "审定表"},
            expected_version=5,
        )
        assert new_ver == 6
        assert wp.file_version == 6

        # 第二个写入：univer_save（使用旧版本号 5，应冲突）
        with pytest.raises(OptimisticLockError) as exc_info:
            await orch.after_save(
                db, wp, user_b,
                trigger="univer_save",
                extra={"content_hash": "abc123"},
                expected_version=5,
            )
        assert exc_info.value.expected == 5
        assert exc_info.value.actual == 6

    @pytest.mark.asyncio
    async def test_custom_query_vs_onlyoffice(self):
        """custom_query_writeback + onlyoffice_callback 同时写 → 一个 409"""
        wp = _make_wp(file_version=10)
        db = _make_db()
        user = _make_user("system")

        orch = WorkpaperSaveOrchestrator()

        # custom_query_writeback 先到
        await orch.after_save(
            db, wp, user,
            trigger="custom_query_writeback",
            extra={},
            expected_version=10,
        )
        assert wp.file_version == 11

        # onlyoffice_callback 后到（使用旧版本号）
        with pytest.raises(OptimisticLockError):
            await orch.after_save(
                db, wp, user,
                trigger="onlyoffice_callback",
                extra={},
                expected_version=10,
            )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        initial_version=st.integers(min_value=1, max_value=50),
        path_a=st.sampled_from(["html_save", "univer_save", "onlyoffice_callback", "custom_query_writeback"]),
        path_b=st.sampled_from(["html_save", "univer_save", "onlyoffice_callback", "custom_query_writeback"]),
    )
    @pytest.mark.asyncio
    async def test_any_two_paths_conflict(self, initial_version, path_a, path_b, _patch_event_bus):
        """**Validates: Requirements 2.2**

        Property: 任意两条路径并发写同一底稿（相同 expected_version）→ 恰好一个成功一个 409。
        """
        wp = _make_wp(file_version=initial_version)
        db = _make_db()
        user = _make_user()

        orch = WorkpaperSaveOrchestrator()
        results = []

        for path in [path_a, path_b]:
            try:
                await orch.after_save(
                    db, wp, user,
                    trigger=path,
                    extra={},
                    expected_version=initial_version,
                )
                results.append("success")
            except OptimisticLockError:
                results.append("conflict")

        assert results.count("success") == 1
        assert results.count("conflict") == 1
        assert wp.file_version == initial_version + 1
