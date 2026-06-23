"""Preservation property tests: same-year cache behavior must remain correct.

**Validates: Requirements 3.1, 3.2, 3.3**

These tests verify that existing CORRECT behavior is preserved:
- Same-year set/get roundtrip works
- Cache invalidation clears all entries
- Event handler wildcard `report:{pid}:*` matches current key format

All tests MUST PASS on unfixed code (same-year behavior is correct today).
"""

import json
import uuid

import fakeredis.aioredis
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from unittest.mock import AsyncMock

from app.services.report_engine import ReportEngine, REPORT_CACHE_TTL


REPORT_TYPES = st.sampled_from([
    "balance_sheet", "income_statement", "cash_flow_statement", "equity_statement"
])

YEARS = st.integers(min_value=2000, max_value=2099)

REPORT_DATA = st.lists(
    st.fixed_dictionaries({
        "row_code": st.from_regex(r"[A-Z]{2}-[0-9]{3}", fullmatch=True),
        "amount": st.decimals(min_value=0, max_value=999999, places=2).map(str),
    }),
    min_size=1,
    max_size=3,
)


@pytest.mark.asyncio
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    report_type=REPORT_TYPES,
    data=REPORT_DATA,
)
async def test_same_year_cache_hit(report_type, data):
    """Property 2: Preservation — same-year set/get roundtrip returns original data.

    For any (project_id, year, report_type, data), setting cache then getting
    with the same parameters should return the cached data.

    **Validates: Requirements 3.1, 3.2**

    EXPECTED: This test PASSES on both unfixed and fixed code.
    """
    redis = fakeredis.aioredis.FakeRedis()
    try:
        project_id = uuid.uuid4()
        db = AsyncMock()

        engine = ReportEngine(db=db, redis=redis)

        # Write and read with same parameters (same-year behavior)
        year = 2024  # Fixed year for same-year roundtrip test
        await engine._set_cached_report(project_id, year, report_type, data)
        result = await engine._get_cached_report(project_id, year, report_type)

        assert result == data, (
            f"Same-year cache miss! Set data for {report_type}, "
            f"expected to get it back but got: {result}"
        )
    finally:
        await redis.flushall()
        await redis.aclose()


@pytest.mark.asyncio
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    report_type=REPORT_TYPES,
    data=REPORT_DATA,
)
async def test_invalidation_clears_cache(report_type, data):
    """Preservation — invalidation clears all cached entries for a project.

    **Validates: Requirements 3.2**

    EXPECTED: This test PASSES on both unfixed and fixed code.
    """
    redis = fakeredis.aioredis.FakeRedis()
    try:
        project_id = uuid.uuid4()
        db = AsyncMock()

        engine = ReportEngine(db=db, redis=redis)

        # Set cache
        year = 2024
        await engine._set_cached_report(project_id, year, report_type, data)

        # Invalidate all for this project
        count = await engine._invalidate_report_cache(project_id)

        # Read should now be None
        result = await engine._get_cached_report(project_id, year, report_type)
        assert result is None, (
            f"Cache not invalidated! After invalidation, "
            f"expected None but got: {result}"
        )
    finally:
        await redis.flushall()
        await redis.aclose()


@pytest.mark.asyncio
async def test_event_handler_wildcard_matches_current_key_format():
    """Preservation — event_handler wildcard `report:{pid}:*` matches keys.

    The event handler uses `report:{pid}:*` pattern with SCAN to find and
    delete cache keys. This must match the key format used by ReportEngine.

    **Validates: Requirements 3.3**

    EXPECTED: This test PASSES on both unfixed and fixed code.
    """
    redis = fakeredis.aioredis.FakeRedis()
    try:
        project_id = uuid.uuid4()
        db = AsyncMock()

        engine = ReportEngine(db=db, redis=redis)

        # Set cache entries for multiple report types
        year = 2024
        for rt in ("balance_sheet", "income_statement", "cash_flow_statement", "equity_statement"):
            await engine._set_cached_report(project_id, year, rt, [{"row_code": "X-001"}])

        # Simulate event_handler wildcard pattern: report:{pid}:*
        pattern = f"report:{project_id}:*"
        cursor = 0
        all_keys = []
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=200)
            all_keys.extend(keys)
            if cursor == 0:
                break

        # All 4 report type keys should be matched by the wildcard
        assert len(all_keys) == 4, (
            f"Event handler wildcard `report:{{pid}}:*` should match all cache keys. "
            f"Expected 4 keys, found {len(all_keys)}: {all_keys}"
        )

        # Delete them (simulating event_handler behavior)
        if all_keys:
            await redis.delete(*all_keys)

        # Verify all cleared
        for rt in ("balance_sheet", "income_statement", "cash_flow_statement", "equity_statement"):
            result = await engine._get_cached_report(project_id, year, rt)
            assert result is None, f"Key for {rt} not cleared by wildcard deletion"
    finally:
        await redis.flushall()
        await redis.aclose()
