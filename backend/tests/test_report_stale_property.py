"""PBT P-2：报表 stale 传播正确性

Property P-2 from requirements:
- If wp_code has mapping → affected rows marked is_stale=true
- If wp_code has no mapping → no stale marks
- Stale marking is idempotent (repeated saves don't accumulate)

**Validates: Requirements US-2 P-2**
"""

from __future__ import annotations

import uuid
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.report_stale_service import ReportStaleService, _load_wp_account_mapping


# ─── Strategies ──────────────────────────────────────────────────────────────

# Generate realistic wp_codes (e.g. D2, E1, F2-21, A1-11)
wp_code_strategy = st.from_regex(r"[A-N][0-9](-[0-9]{1,2})?", fullmatch=True)

# Generate realistic account codes (4-6 digit numeric strings)
account_code_strategy = st.from_regex(r"[0-9]{4,6}", fullmatch=True)

# Generate realistic report_line_codes
report_line_code_strategy = st.from_regex(r"[A-Z]{2}[0-9]{3}", fullmatch=True)


# ─── Fake DB session ─────────────────────────────────────────────────────────


class FakeResult:
    """Simulates SQLAlchemy result for SELECT queries."""

    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeDB:
    """Minimal async DB session mock that tracks execute calls."""

    def __init__(self, select_results: list[tuple] | None = None):
        self._select_results = select_results or []
        self.execute_calls: list = []

    async def execute(self, stmt):
        self.execute_calls.append(stmt)
        # If it's a SELECT (has .fetchall), return fake results
        if hasattr(stmt, "whereclause") or "select" in str(type(stmt)).lower():
            return FakeResult(self._select_results)
        # UPDATE returns None
        return None


# ─── Property Tests ──────────────────────────────────────────────────────────


class TestReportStaleProperty:
    """PBT P-2: stale 传播正确性"""

    @given(
        wp_code=wp_code_strategy,
        account_codes=st.lists(account_code_strategy, min_size=1, max_size=5, unique=True),
        report_line_codes=st.lists(report_line_code_strategy, min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=30, deadline=None)
    @pytest.mark.asyncio
    async def test_mapped_wp_code_marks_stale(
        self, wp_code: str, account_codes: list[str], report_line_codes: list[str]
    ):
        """If wp_code has mapping → affected rows marked is_stale=true.

        **Validates: Requirements US-2 P-2** (mapping hit)
        """
        project_id = uuid.uuid4()
        service = ReportStaleService()

        # Mock wp_account_mapping to return account_codes for this wp_code
        fake_mapping = {wp_code: account_codes}

        # Mock DB: SELECT returns report_line_codes
        fake_db = FakeDB(select_results=[(code,) for code in report_line_codes])

        with patch(
            "app.services.report_stale_service._load_wp_account_mapping",
            return_value=fake_mapping,
        ), patch(
            "app.services.event_bus.event_bus",
            MagicMock(broadcast_raw=MagicMock()),
        ):
            result = await service.mark_if_mapped(wp_code, project_id, fake_db)

        # Property: result contains all affected line codes
        assert set(result) == set(report_line_codes)
        # Property: at least 2 DB calls (SELECT + UPDATE)
        assert len(fake_db.execute_calls) >= 2

    @given(
        wp_code=wp_code_strategy,
    )
    @settings(max_examples=30, deadline=None)
    @pytest.mark.asyncio
    async def test_unmapped_wp_code_no_stale(self, wp_code: str):
        """If wp_code has no mapping → no stale marks.

        **Validates: Requirements US-2 P-2** (mapping miss)
        """
        project_id = uuid.uuid4()
        service = ReportStaleService()

        # Mock wp_account_mapping with empty mapping for this wp_code
        fake_mapping: dict[str, list[str]] = {}  # No mapping at all

        fake_db = FakeDB()

        with patch(
            "app.services.report_stale_service._load_wp_account_mapping",
            return_value=fake_mapping,
        ):
            result = await service.mark_if_mapped(wp_code, project_id, fake_db)

        # Property: no affected rows
        assert result == []
        # Property: no DB calls (early return)
        assert len(fake_db.execute_calls) == 0

    @given(
        wp_code=wp_code_strategy,
        account_codes=st.lists(account_code_strategy, min_size=1, max_size=3, unique=True),
        report_line_codes=st.lists(report_line_code_strategy, min_size=1, max_size=3, unique=True),
        repeat_count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=20, deadline=None)
    @pytest.mark.asyncio
    async def test_stale_marking_idempotent(
        self,
        wp_code: str,
        account_codes: list[str],
        report_line_codes: list[str],
        repeat_count: int,
    ):
        """Stale marking is idempotent (repeated saves don't accumulate).

        **Validates: Requirements US-2 P-2** (idempotent)
        """
        project_id = uuid.uuid4()
        service = ReportStaleService()

        fake_mapping = {wp_code: account_codes}

        # Call mark_if_mapped multiple times
        results = []
        for _ in range(repeat_count):
            fake_db = FakeDB(select_results=[(code,) for code in report_line_codes])
            with patch(
                "app.services.report_stale_service._load_wp_account_mapping",
                return_value=fake_mapping,
            ), patch(
                "app.services.event_bus.event_bus",
                MagicMock(broadcast_raw=MagicMock()),
            ):
                result = await service.mark_if_mapped(wp_code, project_id, fake_db)
            results.append(result)

        # Property: all calls return the same affected rows (idempotent)
        for r in results:
            assert set(r) == set(report_line_codes)

        # Property: result set doesn't grow with repeated calls
        assert len(results[-1]) == len(results[0])

    @given(
        wp_code=wp_code_strategy,
        account_codes=st.lists(account_code_strategy, min_size=1, max_size=3, unique=True),
    )
    @settings(max_examples=20, deadline=None)
    @pytest.mark.asyncio
    async def test_mapped_accounts_but_no_report_lines(
        self, wp_code: str, account_codes: list[str]
    ):
        """wp_code has account mapping but no report_line_mapping → no stale marks.

        **Validates: Requirements US-2 P-2** (mapping miss at report level)
        """
        project_id = uuid.uuid4()
        service = ReportStaleService()

        fake_mapping = {wp_code: account_codes}
        # DB returns empty result for SELECT (no report_line_mapping rows)
        fake_db = FakeDB(select_results=[])

        with patch(
            "app.services.report_stale_service._load_wp_account_mapping",
            return_value=fake_mapping,
        ):
            result = await service.mark_if_mapped(wp_code, project_id, fake_db)

        # Property: no affected rows
        assert result == []
        # Property: only 1 DB call (SELECT, no UPDATE)
        assert len(fake_db.execute_calls) == 1
