"""Tests for advanced-query audit throttling strategy (Task 15.4).

design.md §Components 11 / R14.3 / R14.4:
- 回写 (writeback) 与跨 sheet 溯源 (cross_sheet_trace)：逐次记录（不节流），
  记录 操作者 / UTC 秒级时间戳 / 操作类型 / 目标 addr_id 集合 / 新旧值 / 结果。
- 查询执行 (query_execution)：按 60s 窗口节流为 1 条（audit_throttle.should_record）。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.services.custom_query import audit_helper
from app.services.custom_query.audit_helper import (
    ACTION_CROSS_SHEET_TRACE,
    ACTION_QUERY_EXECUTE,
    ACTION_WRITEBACK,
    QUERY_EXECUTION_THROTTLE_WINDOW_SECONDS,
    _normalize_addr_ids,
    _utc_second_timestamp,
    record_cross_sheet_trace,
    record_query_execution,
    record_writeback,
)


@pytest_asyncio.fixture
async def fake_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest.fixture
def captured_logs(monkeypatch):
    """Capture calls to audit_logger.log_action (async)."""
    calls: list[dict] = []

    async def _fake_log_action(**kwargs):
        calls.append(kwargs)
        return kwargs

    monkeypatch.setattr(audit_helper.audit_logger, "log_action", _fake_log_action)
    return calls


# ---------------------------------------------------------------------------
# Helpers: timestamp + addr_id normalization
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_utc_second_timestamp_has_no_microseconds(self):
        ts = _utc_second_timestamp()
        parsed = datetime.fromisoformat(ts)
        assert parsed.microsecond == 0
        assert parsed.tzinfo is not None
        # UTC offset zero
        assert parsed.utcoffset() == timezone.utc.utcoffset(None)

    def test_normalize_addr_ids_single_string(self):
        assert _normalize_addr_ids("D2/明细表D2-1/E10") == ["D2/明细表D2-1/E10"]

    def test_normalize_addr_ids_dedup_and_drop_empty(self):
        out = _normalize_addr_ids(["a", None, "", "a", "b"])
        assert out == ["a", "b"]

    def test_normalize_addr_ids_none(self):
        assert _normalize_addr_ids(None) == []


# ---------------------------------------------------------------------------
# Writeback: unconditional (not throttled) + required fields
# ---------------------------------------------------------------------------


class TestRecordWriteback:
    @pytest.mark.asyncio
    async def test_writeback_records_required_fields(self, captured_logs):
        """R14.3: operator / UTC sec timestamp / op type / addr_id set / old&new / result."""
        ok = await record_writeback(
            user_id="user-1",
            addr_ids="D2/明细表D2-1/E10",
            old_value=100,
            new_value=200,
            result="success",
            project_id="proj-1",
            object_id="wp-1",
            extra={"wp_code": "D2"},
        )
        assert ok is True
        assert len(captured_logs) == 1
        call = captured_logs[0]
        assert call["action"] == ACTION_WRITEBACK
        assert call["user_id"] == "user-1"
        assert call["project_id"] == "proj-1"
        d = call["details"]
        assert d["operation"] == ACTION_WRITEBACK
        assert d["addr_ids"] == ["D2/明细表D2-1/E10"]
        assert d["old_value"] == 100
        assert d["new_value"] == 200
        assert d["result"] == "success"
        assert d["wp_code"] == "D2"
        # UTC second-precision timestamp present
        assert datetime.fromisoformat(d["occurred_at"]).microsecond == 0

    @pytest.mark.asyncio
    async def test_writeback_never_throttled(self, captured_logs):
        """R14.4: every writeback recorded (no throttle, no redis involved)."""
        for _ in range(5):
            await record_writeback(
                user_id="user-1",
                addr_ids="D2/S/E10",
                old_value=1,
                new_value=2,
            )
        assert len(captured_logs) == 5

    @pytest.mark.asyncio
    async def test_writeback_audit_failure_swallowed(self, monkeypatch):
        """Audit failure must not raise to caller (returns False)."""
        async def _boom(**kwargs):
            raise RuntimeError("queue down")

        monkeypatch.setattr(audit_helper.audit_logger, "log_action", _boom)
        ok = await record_writeback(user_id="u", addr_ids="a", old_value=1, new_value=2)
        assert ok is False


# ---------------------------------------------------------------------------
# Cross-sheet trace: unconditional (not throttled)
# ---------------------------------------------------------------------------


class TestRecordCrossSheetTrace:
    @pytest.mark.asyncio
    async def test_trace_records_addr_id_set(self, captured_logs):
        ok = await record_cross_sheet_trace(
            user_id="user-1",
            addr_ids=["D2/S/A2", "D3/S/B5", None, "D2/S/A2"],
            result="success",
            project_id="proj-1",
            object_id="wp-1",
            extra={"chain_length": 2},
        )
        assert ok is True
        d = captured_logs[0]["details"]
        assert captured_logs[0]["action"] == ACTION_CROSS_SHEET_TRACE
        assert d["operation"] == ACTION_CROSS_SHEET_TRACE
        # dedup + drop None
        assert d["addr_ids"] == ["D2/S/A2", "D3/S/B5"]
        assert d["result"] == "success"
        assert d["chain_length"] == 2
        assert "occurred_at" in d

    @pytest.mark.asyncio
    async def test_trace_never_throttled(self, captured_logs):
        for _ in range(4):
            await record_cross_sheet_trace(user_id="u", addr_ids="D2/S/A2")
        assert len(captured_logs) == 4


# ---------------------------------------------------------------------------
# Query execution: throttled to 1 per 60s window
# ---------------------------------------------------------------------------


class TestRecordQueryExecution:
    @pytest.mark.asyncio
    async def test_query_execution_throttled_within_window(self, fake_redis, captured_logs):
        """R14.4: same (user, source, filters) within 60s → only first recorded."""
        source = "workpaper:D2|审定表D2-1"
        filters = {"year": "2025"}

        r1 = await record_query_execution(
            redis=fake_redis, user_id="user-1", source=source,
            filters=filters, details={"row_count": 3},
        )
        r2 = await record_query_execution(
            redis=fake_redis, user_id="user-1", source=source,
            filters=filters, details={"row_count": 3},
        )
        assert r1 is True
        assert r2 is False
        assert len(captured_logs) == 1
        assert captured_logs[0]["action"] == ACTION_QUERY_EXECUTE

    @pytest.mark.asyncio
    async def test_query_execution_uses_60s_window(self, captured_logs):
        """Verify should_record is called with window_seconds=60."""
        with patch.object(
            audit_helper, "should_record", new=AsyncMock(return_value=True)
        ) as mock_sr:
            await record_query_execution(
                redis=None, user_id="user-1", source="s", filters={},
                details={},
            )
        assert mock_sr.await_args.kwargs["window_seconds"] == 60
        assert QUERY_EXECUTION_THROTTLE_WINDOW_SECONDS == 60
        # throttle key action is the non-sensitive execute action (so it throttles)
        assert mock_sr.await_args.kwargs["action"] == ACTION_QUERY_EXECUTE

    @pytest.mark.asyncio
    async def test_query_execution_custom_action_label(self, fake_redis, captured_logs):
        """Batch execution logs a different action label but still throttles."""
        await record_query_execution(
            redis=fake_redis, user_id="user-1", source="batch:D2,D3",
            filters={}, details={"total": 2}, action="custom_query.batch_execute",
        )
        assert captured_logs[0]["action"] == "custom_query.batch_execute"

    @pytest.mark.asyncio
    async def test_different_source_not_throttled(self, fake_redis, captured_logs):
        await record_query_execution(
            redis=fake_redis, user_id="u", source="workpaper:D2",
            filters={"y": "2025"}, details={},
        )
        await record_query_execution(
            redis=fake_redis, user_id="u", source="workpaper:D3",
            filters={"y": "2025"}, details={},
        )
        assert len(captured_logs) == 2

    @pytest.mark.asyncio
    async def test_redis_none_degrades_to_always_record(self, captured_logs):
        """R12.7-style degradation: redis None → should_record returns True → records."""
        r1 = await record_query_execution(
            redis=None, user_id="u", source="s", filters={}, details={},
        )
        r2 = await record_query_execution(
            redis=None, user_id="u", source="s", filters={}, details={},
        )
        assert r1 is True and r2 is True
        assert len(captured_logs) == 2

    @pytest.mark.asyncio
    async def test_throttle_check_failure_returns_false(self, captured_logs):
        """If throttle check raises, do not record and do not raise to caller."""
        with patch.object(
            audit_helper, "should_record", new=AsyncMock(side_effect=RuntimeError("x"))
        ):
            ok = await record_query_execution(
                redis="whatever", user_id="u", source="s", filters={}, details={},
            )
        assert ok is False
        assert len(captured_logs) == 0
