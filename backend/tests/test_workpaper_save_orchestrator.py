"""WorkpaperSaveOrchestrator 单元测试

Validates: Requirements 1.2, 2.1, 2.2, 2.3
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workpaper_save_orchestrator import (
    OptimisticLockError,
    WorkpaperSaveOrchestrator,
    orchestrator,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _make_wp(file_version: int = 1) -> MagicMock:
    """创建模拟 WorkingPaper 实例"""
    wp = MagicMock()
    wp.id = uuid.uuid4()
    wp.project_id = uuid.uuid4()
    wp.file_version = file_version
    wp.prefill_stale = False
    wp.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return wp


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "test_user"
    return user


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def _patch_event_bus():
    """统一 patch event_bus.publish 避免真实调用"""
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()
    with patch("app.services.event_bus.event_bus", mock_bus):
        yield mock_bus


# ─── Unit Tests ──────────────────────────────────────────────────────────────


class TestAfterSaveIncrementsFileVersion:
    """test_after_save_increments_file_version"""

    @pytest.mark.asyncio
    async def test_increments_from_1_to_2(self):
        wp = _make_wp(file_version=1)
        db = _make_db()
        user = _make_user()

        new_ver = await orchestrator.after_save(
            db, wp, user, trigger="html_save", extra={}
        )

        assert new_ver == 2
        assert wp.file_version == 2

    @pytest.mark.asyncio
    async def test_increments_from_5_to_6(self):
        wp = _make_wp(file_version=5)
        db = _make_db()
        user = _make_user()

        new_ver = await orchestrator.after_save(
            db, wp, user, trigger="univer_save", extra={}
        )

        assert new_ver == 6
        assert wp.file_version == 6


class TestAfterSaveMarksPrefillStale:
    """test_after_save_marks_prefill_stale"""

    @pytest.mark.asyncio
    async def test_sets_prefill_stale_true(self):
        wp = _make_wp()
        wp.prefill_stale = False
        db = _make_db()
        user = _make_user()

        await orchestrator.after_save(
            db, wp, user, trigger="html_save", extra={}
        )

        assert wp.prefill_stale is True


class TestAfterSavePublishesWorkpaperSavedEvent:
    """test_after_save_publishes_workpaper_saved_event"""

    @pytest.mark.asyncio
    async def test_publishes_event(self, _patch_event_bus):
        wp = _make_wp(file_version=3)
        db = _make_db()
        user = _make_user()

        await orchestrator.after_save(
            db, wp, user, trigger="custom_query_writeback", extra={"year": 2025}
        )

        _patch_event_bus.publish.assert_called_once()
        payload = _patch_event_bus.publish.call_args[0][0]
        assert payload.event_type.value == "workpaper.saved"
        assert payload.project_id == wp.project_id
        assert payload.extra["trigger"] == "custom_query_writeback"
        assert payload.extra["file_version"] == 4


class TestAfterSaveWritesAuditLog:
    """test_after_save_writes_audit_log"""

    @pytest.mark.asyncio
    async def test_writes_log(self):
        wp = _make_wp(file_version=2)
        db = _make_db()
        user = _make_user()

        await orchestrator.after_save(
            db, wp, user, trigger="onlyoffice_callback", extra={}
        )

        # db.add 应被调用（添加 Log 实例）
        db.add.assert_called_once()
        log_obj = db.add.call_args[0][0]
        assert log_obj.action_type == "workpaper_onlyoffice_callback"
        assert log_obj.object_type == "working_paper"
        assert log_obj.object_id == wp.id
        assert log_obj.new_value["old_version"] == 2
        assert log_obj.new_value["new_version"] == 3


class TestOptimisticLockMismatchRaises409:
    """test_optimistic_lock_mismatch_raises_409"""

    @pytest.mark.asyncio
    async def test_raises_when_expected_version_mismatch(self):
        wp = _make_wp(file_version=3)
        db = _make_db()
        user = _make_user()

        with pytest.raises(OptimisticLockError) as exc_info:
            await orchestrator.after_save(
                db, wp, user,
                trigger="html_save",
                extra={},
                expected_version=2,  # wp.file_version is 3
            )

        assert exc_info.value.expected == 2
        assert exc_info.value.actual == 3
        # file_version 不应被修改
        assert wp.file_version == 3

    @pytest.mark.asyncio
    async def test_passes_when_expected_version_matches(self):
        wp = _make_wp(file_version=3)
        db = _make_db()
        user = _make_user()

        new_ver = await orchestrator.after_save(
            db, wp, user,
            trigger="html_save",
            extra={},
            expected_version=3,
        )

        assert new_ver == 4

    @pytest.mark.asyncio
    async def test_skips_check_when_expected_version_none(self):
        wp = _make_wp(file_version=5)
        db = _make_db()
        user = _make_user()

        new_ver = await orchestrator.after_save(
            db, wp, user,
            trigger="html_save",
            extra={},
            expected_version=None,
        )

        assert new_ver == 6


# ─── PBT: Concurrent saves — one succeeds, one conflicts ────────────────────

from hypothesis import given, settings, strategies as st, HealthCheck


class TestConcurrentSavesOneSucceedsOneConflicts:
    """test_concurrent_saves_one_succeeds_one_conflicts (PBT)

    **Validates: Requirements 2.2**

    Property: 给定同一底稿的两个并发写入（使用相同 expected_version），
    恰好一个成功（file_version 递增），另一个收到 OptimisticLockError。
    """

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        initial_version=st.integers(min_value=1, max_value=100),
        trigger_a=st.sampled_from(["html_save", "univer_save", "onlyoffice_callback", "custom_query_writeback"]),
        trigger_b=st.sampled_from(["html_save", "univer_save", "onlyoffice_callback", "custom_query_writeback"]),
    )
    @pytest.mark.asyncio
    async def test_exactly_one_succeeds(self, initial_version, trigger_a, trigger_b, _patch_event_bus):
        """两个并发写入同一底稿（相同 expected_version）→ 恰好一个成功一个 409"""
        wp = _make_wp(file_version=initial_version)
        db = _make_db()
        user = _make_user()

        orch = WorkpaperSaveOrchestrator()
        success_count = 0
        conflict_count = 0

        # 第一个写入（应成功）
        try:
            await orch.after_save(
                db, wp, user,
                trigger=trigger_a,
                extra={},
                expected_version=initial_version,
            )
            success_count += 1
        except OptimisticLockError:
            conflict_count += 1

        # 第二个写入（使用相同的 expected_version，应冲突）
        try:
            await orch.after_save(
                db, wp, user,
                trigger=trigger_b,
                extra={},
                expected_version=initial_version,
            )
            success_count += 1
        except OptimisticLockError:
            conflict_count += 1

        assert success_count == 1, f"Expected exactly 1 success, got {success_count}"
        assert conflict_count == 1, f"Expected exactly 1 conflict, got {conflict_count}"
        assert wp.file_version == initial_version + 1
