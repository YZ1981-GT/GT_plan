"""Bug condition exploration test: cross-year cache pollution.

**Validates: Requirements 1.1, 1.2**

This test encodes the EXPECTED behavior after fix: cross-year get must return None.
On unfixed code, this test MUST FAIL — confirming the bug exists.

Bug: `_cache_key` constructs key as `report:{project_id}:{report_type}` without year,
so different years share the same cache entry.
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


@pytest.mark.asyncio
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    year_a=YEARS,
    year_b=YEARS,
    report_type=REPORT_TYPES,
)
async def test_cross_year_cache_isolation(year_a, year_b, report_type):
    """Property 1: Bug Condition — cross-year cache must NOT return stale data.

    For any (project_id, year_A, year_B, report_type) where year_A ≠ year_B,
    setting cache with year_A then getting with year_B should return None.

    **Validates: Requirements 1.1, 1.2**

    EXPECTED: This test FAILS on unfixed code (proves the bug exists).
    After fix, this test will PASS.
    """
    from hypothesis import assume
    assume(year_a != year_b)

    redis = fakeredis.aioredis.FakeRedis()
    try:
        project_id = uuid.uuid4()
        db = AsyncMock()

        engine = ReportEngine(db=db, redis=redis)

        # Write cache for year_A
        data_year_a = [{"row_code": "BS-001", "amount": "100.00", "year": year_a}]
        await engine._set_cached_report(project_id, year_a, report_type, data_year_a)

        # Read cache for year_B — should return None (different year)
        result = await engine._get_cached_report(project_id, year_b, report_type)

        # BUG: On unfixed code, _get_cached_report has no year param, so it returns
        # data_year_a regardless of which year we want. The assertion below encodes
        # the EXPECTED behavior: cross-year read should be a cache miss (None).
        assert result is None, (
            f"Cross-year cache pollution detected! "
            f"Set cache for year={year_a}, got data back when requesting year={year_b}. "
            f"Expected None but got: {result}"
        )
    finally:
        await redis.flushall()
        await redis.aclose()
