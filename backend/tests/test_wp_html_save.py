"""Tests for POST /api/workpapers/{wp_id}/save endpoint.

Validates: Requirements 2.2 原则 4（决策可追踪）+ 3.11.4（跨底稿引用传播）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User, UserRole
from app.routers.wp_html_save import router
from app.services.cross_ref_service import CrossRefChange, CrossRefService


# ─── Fixtures ────────────────────────────────────────────────────────────────

_USER_ID = uuid.uuid4()
_WP_ID = uuid.uuid4()
_PROJECT_ID = uuid.uuid4()


class _FakeUser:
    id = _USER_ID
    username = "test_user"
    role = UserRole.admin


class _FakeWorkingPaper:
    """Simulates a WorkingPaper ORM object."""

    def __init__(self, parsed_data=None, is_deleted=False):
        self.id = _WP_ID
        self.project_id = _PROJECT_ID
        self.parsed_data = parsed_data
        self.is_deleted = is_deleted
        self.updated_by = None
        self.updated_at = None


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with the save router."""
    app = FastAPI()
    app.include_router(router)

    async def _user():
        return _FakeUser()

    app.dependency_overrides[get_current_user] = _user
    return app


# ─── Unit tests for CrossRefService ─────────────────────────────────────────


class TestCrossRefService:
    """Test cross_ref_service.detect_changes logic."""

    def test_no_references_returns_empty(self):
        svc = CrossRefService()
        svc._references = []
        result = svc.detect_changes("D2", "sheet1", None, {"rows": []})
        assert result == []

    def test_first_save_with_matching_ref(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-001",
                "source_wp": "D2",
                "source_sheet": "sheet1",
                "target_wp": "A1",
                "target_sheet": "BS",
                "target_cell": "B7",
            }
        ]
        result = svc.detect_changes("D2", "sheet1", None, {"rows": [1, 2]})
        assert len(result) == 1
        assert result[0].ref_id == "CW-001"
        assert result[0].target_wp_code == "A1"

    def test_no_change_returns_empty(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-001",
                "source_wp": "D2",
                "source_sheet": "sheet1",
                "target_wp": "A1",
            }
        ]
        same_data = {"rows": [1, 2]}
        result = svc.detect_changes("D2", "sheet1", same_data, same_data)
        assert result == []

    def test_data_change_with_matching_ref(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-002",
                "source_wp": "D2",
                "target_wp": "E1",
                "target_sheet": "控制测试",
            }
        ]
        old = {"rows": [1]}
        new = {"rows": [1, 2]}
        result = svc.detect_changes("D2", "sheet1", old, new)
        assert len(result) == 1
        assert result[0].target_wp_code == "E1"

    def test_unrelated_wp_code_not_matched(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-003",
                "source_wp": "E1",
                "target_wp": "A1",
            }
        ]
        result = svc.detect_changes("D2", "sheet1", None, {"rows": []})
        assert result == []

    def test_changed_cells_filter(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-004",
                "source_wp": "D2",
                "source_cell": "B17",
                "target_wp": "A1",
            }
        ]
        # changed_cells does NOT include B17
        result = svc.detect_changes(
            "D2", "sheet1", None, {"rows": []}, changed_cells=["C5", "D10"]
        )
        assert result == []

        # changed_cells includes B17
        result = svc.detect_changes(
            "D2", "sheet1", None, {"rows": []}, changed_cells=["B17", "C5"]
        )
        assert len(result) == 1

    def test_source_sheet_filter(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-005",
                "source_wp": "D2",
                "source_sheet": "审定表D2-1",
                "target_wp": "A1",
            }
        ]
        # Different sheet name
        result = svc.detect_changes("D2", "程序表D2A", None, {"rows": []})
        assert result == []

        # Matching sheet name
        result = svc.detect_changes("D2", "审定表D2-1", None, {"rows": []})
        assert len(result) == 1

    def test_to_dict(self):
        change = CrossRefChange(
            ref_id="CW-001",
            source_wp_code="D2",
            source_sheet="sheet1",
            target_wp_code="A1",
            target_sheet="BS",
            target_cell="B7",
        )
        d = change.to_dict()
        assert d["ref_id"] == "CW-001"
        assert d["source_wp_code"] == "D2"
        assert d["target_wp_code"] == "A1"


# ─── Endpoint integration tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_404_when_wp_not_found():
    """Non-existent wp_id returns 404."""
    app = _make_app()

    # Mock db that returns no working paper
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/workpapers/{uuid.uuid4()}/save",
            json={
                "sheet_name": "测试sheet",
                "html_data": {"rows": []},
                "schema_version": "v2025-R5",
            },
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_save_409_schema_version_conflict():
    """schema_version mismatch returns 409."""
    app = _make_app()

    fake_wp = _FakeWorkingPaper(parsed_data={"schema_version": "v2025-R5"})

    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = fake_wp
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/workpapers/{_WP_ID}/save",
            json={
                "sheet_name": "测试sheet",
                "html_data": {"rows": []},
                "schema_version": "v2024-R3",  # Different version
            },
        )
    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["error"] == "schema_version_conflict"
    assert data["detail"]["server_version"] == "v2025-R5"
    assert data["detail"]["client_version"] == "v2024-R3"


@pytest.mark.asyncio
async def test_save_422_empty_sheet_name():
    """Empty sheet_name returns 422."""
    app = _make_app()

    fake_wp = _FakeWorkingPaper(parsed_data={})

    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = fake_wp
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/workpapers/{_WP_ID}/save",
            json={
                "sheet_name": "   ",
                "html_data": {"rows": []},
                "schema_version": "v2025-R5",
            },
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_save_200_success():
    """Successful save returns 200 with saved_at."""
    app = _make_app()

    fake_wp = _FakeWorkingPaper(parsed_data={"schema_version": "v2025-R5"})

    # We need to mock multiple db.execute calls
    call_count = [0]

    mock_db = AsyncMock(spec=AsyncSession)

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()
        if call_count[0] == 1:
            # First call: SELECT working_paper
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = fake_wp
            mock_result.scalars.return_value = mock_scalars
        elif call_count[0] == 2:
            # Second call: get_wp_code_for_wp_id
            mock_result.scalar_one_or_none.return_value = "D2"
        else:
            # Third call: UPDATE
            pass
        return mock_result

    mock_db.execute.side_effect = _execute_side_effect
    mock_db.commit = AsyncMock()

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    with patch(
        "app.routers.wp_html_save.cross_ref_service"
    ) as mock_crs:
        mock_crs.get_wp_code_for_wp_id = AsyncMock(return_value="D2")
        mock_crs.detect_changes.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                f"/api/workpapers/{_WP_ID}/save",
                json={
                    "sheet_name": "应收账款实质性程序表D2A",
                    "html_data": {"rows": [{"cell": "B17", "value": 100}]},
                    "schema_version": "v2025-R5",
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "saved_at" in data
    assert data["stale_impact"] == []


@pytest.mark.asyncio
async def test_save_200_with_cross_ref_changes():
    """Save with cross-ref changes returns stale_impact list."""
    app = _make_app()

    fake_wp = _FakeWorkingPaper(
        parsed_data={
            "schema_version": "v2025-R5",
            "html_data": {"程序表D2A": {"rows": [{"cell": "B17", "value": 50}]}},
        }
    )

    call_count = [0]
    mock_db = AsyncMock(spec=AsyncSession)

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()
        if call_count[0] == 1:
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = fake_wp
            mock_result.scalars.return_value = mock_scalars
        elif call_count[0] == 2:
            mock_result.scalar_one_or_none.return_value = "D2"
        else:
            pass
        return mock_result

    mock_db.execute.side_effect = _execute_side_effect
    mock_db.commit = AsyncMock()

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    mock_changes = [
        CrossRefChange(
            ref_id="CW-136",
            source_wp_code="D2",
            source_sheet="程序表D2A",
            target_wp_code="A1",
            target_sheet="BS",
            target_cell="B7",
        )
    ]

    with patch(
        "app.routers.wp_html_save.cross_ref_service"
    ) as mock_crs:
        mock_crs.get_wp_code_for_wp_id = AsyncMock(return_value="D2")
        mock_crs.detect_changes.return_value = mock_changes

        with patch("app.routers.wp_html_save._publish_cross_ref_updated") as mock_pub:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    f"/api/workpapers/{_WP_ID}/save",
                    json={
                        "sheet_name": "程序表D2A",
                        "html_data": {"rows": [{"cell": "B17", "value": 100}]},
                        "schema_version": "v2025-R5",
                    },
                )

            # Verify SSE was published
            mock_pub.assert_called_once()
            call_args = mock_pub.call_args
            assert call_args[1]["source_wp_code"] == "D2"
            assert "A1" in call_args[1]["affected_targets"]

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["stale_impact"]) == 1
    assert data["stale_impact"][0]["ref_id"] == "CW-136"
    assert data["stale_impact"][0]["target_wp_code"] == "A1"


@pytest.mark.asyncio
async def test_save_schema_version_none_allows_any():
    """When server has no schema_version yet, any version is accepted."""
    app = _make_app()

    # parsed_data without schema_version
    fake_wp = _FakeWorkingPaper(parsed_data={"html_data": {}})

    call_count = [0]
    mock_db = AsyncMock(spec=AsyncSession)

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()
        if call_count[0] == 1:
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = fake_wp
            mock_result.scalars.return_value = mock_scalars
        elif call_count[0] == 2:
            mock_result.scalar_one_or_none.return_value = "D2"
        else:
            pass
        return mock_result

    mock_db.execute.side_effect = _execute_side_effect
    mock_db.commit = AsyncMock()

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    with patch(
        "app.routers.wp_html_save.cross_ref_service"
    ) as mock_crs:
        mock_crs.get_wp_code_for_wp_id = AsyncMock(return_value="D2")
        mock_crs.detect_changes.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                f"/api/workpapers/{_WP_ID}/save",
                json={
                    "sheet_name": "新sheet",
                    "html_data": {"rows": []},
                    "schema_version": "v2025-R5",
                },
            )

    assert resp.status_code == 200
