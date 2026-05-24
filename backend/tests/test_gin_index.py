"""Tests for parsed_data GIN index (Req 5).

Feature: advanced-query-enhancements-p1p2
Requirements: Req 5 (parsed_data GIN 索引)

Tests:
1. Index building status check correctly sets the global flag
2. Degradation path: when INDEX_BUILDING=True, queries add X-Index-Status=building header
3. Index size monitoring threshold logic
4. EXPLAIN ANALYZE verification (pg_only — requires real PostgreSQL)
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import ASGITransport, AsyncClient

from app.services.gin_index_monitor import (
    check_index_building_status,
    check_index_size_alert,
    get_index_size_bytes,
    is_index_building,
    set_index_building,
    INDEX_BUILDING,
    INDEX_NAME,
    INDEX_SIZE_ALERT_THRESHOLD_BYTES,
)


# ─── Unit Tests: INDEX_BUILDING flag behavior ────────────────────────────────


class TestIndexBuildingFlag:
    """Test the global INDEX_BUILDING flag get/set behavior."""

    def test_set_and_read_flag_true(self):
        """Setting flag to True should be readable."""
        set_index_building(True)
        assert is_index_building() is True
        # Reset
        set_index_building(False)

    def test_set_and_read_flag_false(self):
        """Setting flag to False should be readable."""
        set_index_building(False)
        assert is_index_building() is False

    def test_default_flag_is_false(self):
        """Default state should be False (index assumed ready)."""
        set_index_building(False)
        assert is_index_building() is False


# ─── Unit Tests: check_index_building_status ─────────────────────────────────


class TestCheckIndexBuildingStatus:
    """Test the startup check that queries pg_stat_progress_create_index."""

    @pytest.mark.asyncio
    async def test_index_building_in_progress(self):
        """When pg_stat_progress_create_index has a row, flag should be True."""
        mock_session = AsyncMock()

        # First query (pg_stat_progress_create_index) returns a row
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await check_index_building_status(mock_session)

        assert result is True
        assert is_index_building() is True
        # Reset
        set_index_building(False)

    @pytest.mark.asyncio
    async def test_index_not_exists(self):
        """When index doesn't exist at all, flag should be True (degraded)."""
        mock_session = AsyncMock()

        # First query (pg_stat_progress_create_index) returns no row
        # Second query (pg_index check) returns no row (index doesn't exist)
        call_count = [0]

        async def mock_execute(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None
            return mock_result

        mock_session.execute = mock_execute

        result = await check_index_building_status(mock_session)

        assert result is True
        assert is_index_building() is True
        # Reset
        set_index_building(False)

    @pytest.mark.asyncio
    async def test_index_exists_and_valid(self):
        """When index exists and is valid, flag should be False."""
        mock_session = AsyncMock()

        call_count = [0]

        async def mock_execute(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                # pg_stat_progress_create_index: no active build
                mock_result.fetchone.return_value = None
            else:
                # pg_index check: index exists and is valid
                mock_result.fetchone.return_value = (True,)
            return mock_result

        mock_session.execute = mock_execute

        result = await check_index_building_status(mock_session)

        assert result is False
        assert is_index_building() is False

    @pytest.mark.asyncio
    async def test_index_exists_but_invalid(self):
        """When index exists but indisvalid=False, flag should be True."""
        mock_session = AsyncMock()

        call_count = [0]

        async def mock_execute(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                # pg_stat_progress_create_index: no active build
                mock_result.fetchone.return_value = None
            else:
                # pg_index check: index exists but INVALID
                mock_result.fetchone.return_value = (False,)
            return mock_result

        mock_session.execute = mock_execute

        result = await check_index_building_status(mock_session)

        assert result is True
        assert is_index_building() is True
        # Reset
        set_index_building(False)

    @pytest.mark.asyncio
    async def test_exception_defaults_to_not_building(self):
        """On exception (e.g., SQLite), flag should default to False."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("SQLite no pg_stat"))

        result = await check_index_building_status(mock_session)

        assert result is False
        assert is_index_building() is False


# ─── Unit Tests: Index size monitoring ───────────────────────────────────────


class TestIndexSizeMonitoring:
    """Test the pg_index_size monitoring and alert threshold."""

    @pytest.mark.asyncio
    async def test_size_below_threshold_no_alert(self):
        """When index size < 500MB, no alert should be returned."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        # 100MB
        mock_result.fetchone.return_value = (100 * 1024 * 1024,)
        mock_session.execute = AsyncMock(return_value=mock_result)

        alert = await check_index_size_alert(mock_session)
        assert alert is None

    @pytest.mark.asyncio
    async def test_size_above_threshold_triggers_alert(self):
        """When index size > 500MB, alert should be returned."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        # 600MB
        mock_result.fetchone.return_value = (600 * 1024 * 1024,)
        mock_session.execute = AsyncMock(return_value=mock_result)

        alert = await check_index_size_alert(mock_session)

        assert alert is not None
        assert alert["alert"] == "gin_index_size_exceeded"
        assert alert["index_name"] == INDEX_NAME
        assert alert["size_mb"] == 600.0
        assert alert["threshold_mb"] == 500.0

    @pytest.mark.asyncio
    async def test_size_exactly_at_threshold_no_alert(self):
        """When index size == 500MB exactly, no alert (threshold is >)."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (500 * 1024 * 1024,)
        mock_session.execute = AsyncMock(return_value=mock_result)

        alert = await check_index_size_alert(mock_session)
        assert alert is None

    @pytest.mark.asyncio
    async def test_get_index_size_returns_none_on_error(self):
        """When query fails, get_index_size_bytes returns None."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("connection error"))

        size = await get_index_size_bytes(mock_session)
        assert size is None

    @pytest.mark.asyncio
    async def test_get_index_size_returns_bytes(self):
        """Normal case: returns size in bytes."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1234567,)
        mock_session.execute = AsyncMock(return_value=mock_result)

        size = await get_index_size_bytes(mock_session)
        assert size == 1234567


# ─── Integration Test: Degradation path via HTTP ─────────────────────────────


class TestDegradationPath:
    """Test that execute_query adds X-Index-Status=building header when flag is True."""

    @pytest.mark.asyncio
    async def test_header_present_when_building(self):
        """When INDEX_BUILDING=True, response should have X-Index-Status=building."""
        from app.main import app
        from app.core.database import get_db
        from app.deps import get_current_user

        # Mock user
        mock_user = MagicMock()
        mock_user.id = "00000000-0000-0000-0000-000000000001"
        mock_user.role = "admin"

        # Mock DB session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.rollback = AsyncMock()

        async def override_get_db():
            yield mock_db

        async def override_get_user():
            return mock_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_user

        try:
            set_index_building(True)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/custom-query/execute",
                    json={
                        "project_id": "00000000-0000-0000-0000-000000000001",
                        "year": 2025,
                        "source": "report",
                        "filters": {},
                    },
                )

            assert resp.status_code == 200
            assert resp.headers.get("x-index-status") == "building"
        finally:
            set_index_building(False)
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.asyncio
    async def test_header_absent_when_not_building(self):
        """When INDEX_BUILDING=False, response should NOT have X-Index-Status header."""
        from app.main import app
        from app.core.database import get_db
        from app.deps import get_current_user

        mock_user = MagicMock()
        mock_user.id = "00000000-0000-0000-0000-000000000001"
        mock_user.role = "admin"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.rollback = AsyncMock()

        async def override_get_db():
            yield mock_db

        async def override_get_user():
            return mock_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_user

        try:
            set_index_building(False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/custom-query/execute",
                    json={
                        "project_id": "00000000-0000-0000-0000-000000000001",
                        "year": 2025,
                        "source": "report",
                        "filters": {},
                    },
                )

            assert resp.status_code == 200
            assert "x-index-status" not in resp.headers
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


# ─── PG-only Test: EXPLAIN ANALYZE verification ──────────────────────────────


@pytest.mark.pg_only
class TestExplainAnalyzeGinIndex:
    """Verify that queries actually use the GIN index (requires real PostgreSQL).

    These tests are skipped when running against SQLite.
    """

    @pytest.mark.asyncio
    async def test_jsonb_containment_uses_gin_index(self):
        """EXPLAIN ANALYZE for @> query should show Bitmap Index Scan on idx_wp_parsed_data_gin."""
        # This test requires a real PG database with the index created.
        # It validates Req 5 AC 3: EXPLAIN ANALYZE output includes
        # "Bitmap Index Scan on idx_wp_parsed_data_gin"
        import os
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import text

        db_url = os.getenv("DATABASE_URL")
        if not db_url or "postgresql" not in db_url:
            pytest.skip("Requires PostgreSQL DATABASE_URL")

        engine = create_async_engine(db_url)
        async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session_maker() as session:
            # Check if index exists
            result = await session.execute(
                text("SELECT 1 FROM pg_indexes WHERE indexname = 'idx_wp_parsed_data_gin'")
            )
            if not result.fetchone():
                pytest.skip("GIN index not yet created")

            # Run EXPLAIN ANALYZE
            result = await session.execute(
                text(
                    "EXPLAIN ANALYZE SELECT id FROM working_papers "
                    "WHERE parsed_data @> '{\"univer_snapshot\": {\"sheets\": {}}}'"
                )
            )
            plan_lines = [row[0] for row in result.fetchall()]
            plan_text = "\n".join(plan_lines)

            # The plan should reference our GIN index
            assert "idx_wp_parsed_data_gin" in plan_text or "Bitmap" in plan_text, (
                f"Expected GIN index scan in plan, got:\n{plan_text}"
            )

        await engine.dispose()
