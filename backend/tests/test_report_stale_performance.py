"""性能断言：mark_if_mapped <50ms

Validates: Requirements US-2 验收标准 5 — stale 标记 <50ms，不阻塞保存主流程
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import patch, MagicMock

import pytest

from app.services.report_stale_service import ReportStaleService


class FakeResult:
    """Simulates SQLAlchemy result."""

    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeDB:
    """Minimal async DB session mock for performance testing."""

    def __init__(self, report_line_codes: list[str]):
        self._report_line_codes = report_line_codes

    async def execute(self, stmt):
        # Simulate minimal DB latency (no actual I/O)
        return FakeResult([(code,) for code in self._report_line_codes])


@pytest.mark.asyncio
async def test_mark_if_mapped_performance_under_50ms():
    """mark_if_mapped should complete in <50ms (excluding actual DB I/O).

    **Validates: Requirements US-2 验收标准 5**

    This test measures the service logic overhead (mapping lookup + SQL construction
    + SSE broadcast) with mocked DB. Real DB latency is separate.
    """
    service = ReportStaleService()
    project_id = uuid.uuid4()
    wp_code = "D2"

    # Simulate a realistic scenario: 5 account codes → 10 report lines
    fake_mapping = {
        "D2": ["1122", "1123", "1131", "1132", "1221"],
    }
    report_line_codes = [f"BS{i:03d}" for i in range(10)]
    fake_db = FakeDB(report_line_codes)

    with patch(
        "app.services.report_stale_service._load_wp_account_mapping",
        return_value=fake_mapping,
    ), patch(
        "app.services.event_bus.event_bus",
        MagicMock(broadcast_raw=MagicMock()),
    ):
        # Warm up (first call may have import overhead)
        await service.mark_if_mapped(wp_code, project_id, fake_db)

        # Measure 10 iterations
        start = time.perf_counter()
        iterations = 10
        for _ in range(iterations):
            await service.mark_if_mapped(wp_code, project_id, fake_db)
        elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    assert avg_ms < 50, (
        f"mark_if_mapped average time {avg_ms:.2f}ms exceeds 50ms threshold"
    )


@pytest.mark.asyncio
async def test_mark_if_mapped_no_mapping_fast():
    """When wp_code has no mapping, should return immediately (<1ms).

    **Validates: Requirements US-2 验收标准 5** (fast path)
    """
    service = ReportStaleService()
    project_id = uuid.uuid4()
    wp_code = "Z99"  # Non-existent wp_code

    fake_mapping: dict[str, list[str]] = {}
    fake_db = FakeDB([])

    with patch(
        "app.services.report_stale_service._load_wp_account_mapping",
        return_value=fake_mapping,
    ):
        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            result = await service.mark_if_mapped(wp_code, project_id, fake_db)
        elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    assert result == []
    assert avg_ms < 1, (
        f"No-mapping fast path average time {avg_ms:.4f}ms exceeds 1ms threshold"
    )


@pytest.mark.asyncio
async def test_mark_if_mapped_large_mapping_under_50ms():
    """Even with many account codes and report lines, should stay <50ms.

    **Validates: Requirements US-2 验收标准 5** (stress scenario)
    """
    service = ReportStaleService()
    project_id = uuid.uuid4()
    wp_code = "D2"

    # Simulate large mapping: 20 account codes → 50 report lines
    fake_mapping = {
        "D2": [f"{1100 + i}" for i in range(20)],
    }
    report_line_codes = [f"BS{i:03d}" for i in range(50)]
    fake_db = FakeDB(report_line_codes)

    with patch(
        "app.services.report_stale_service._load_wp_account_mapping",
        return_value=fake_mapping,
    ), patch(
        "app.services.event_bus.event_bus",
        MagicMock(broadcast_raw=MagicMock()),
    ):
        start = time.perf_counter()
        iterations = 10
        for _ in range(iterations):
            await service.mark_if_mapped(wp_code, project_id, fake_db)
        elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    assert avg_ms < 50, (
        f"Large mapping scenario average time {avg_ms:.2f}ms exceeds 50ms threshold"
    )
