"""Unit tests for wp_template_version_service.

Tests get_current_version / list_versions / get_version_by_id.
Requirements: 3.0.4（模板版本管理）
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wp_template_version_service import WpTemplateVersionService


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_version(
    version: str = "v2025-R5",
    is_current: bool = False,
    release_date: date | None = None,
    version_id: uuid.UUID | None = None,
):
    """Create a mock WorkpaperTemplateVersion object."""
    mock = MagicMock()
    mock.id = version_id or uuid.uuid4()
    mock.version = version
    mock.release_date = release_date or date(2025, 5, 1)
    mock.source = "致同总所"
    mock.is_current = is_current
    mock.parent_version_id = None
    mock.changelog = None
    mock.created_at = datetime(2025, 5, 1, 0, 0, 0)
    return mock


def _mock_db_session(scalars_result):
    """Create a mock AsyncSession that returns given scalars result."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = scalars_result if not isinstance(scalars_result, list) else (scalars_result[0] if scalars_result else None)
    mock_scalars.all.return_value = scalars_result if isinstance(scalars_result, list) else [scalars_result]
    mock_result.scalars.return_value = mock_scalars
    db.execute = AsyncMock(return_value=mock_result)
    return db


# ─── get_current_version ─────────────────────────────────────────────────────


class TestGetCurrentVersion:
    """Test get_current_version returns the active version."""

    @pytest.mark.asyncio
    async def test_returns_current_version(self):
        """Should return the version with is_current=TRUE."""
        current = _make_version("v2025-R5", is_current=True)
        db = _mock_db_session(current)

        service = WpTemplateVersionService(db)
        result = await service.get_current_version()

        assert result.version == "v2025-R5"
        assert result.is_current is True

    @pytest.mark.asyncio
    async def test_raises_404_when_no_current(self):
        """Should raise HTTPException 404 when no is_current=TRUE version exists."""
        from fastapi import HTTPException

        db = _mock_db_session(None)

        service = WpTemplateVersionService(db)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_current_version()

        assert exc_info.value.status_code == 404


# ─── list_versions ───────────────────────────────────────────────────────────


class TestListVersions:
    """Test list_versions returns all versions ordered by release_date DESC."""

    @pytest.mark.asyncio
    async def test_returns_all_versions(self):
        """Should return all versions as a list."""
        versions = [
            _make_version("v2025-R5", release_date=date(2025, 5, 1)),
            _make_version("v2024-R3", release_date=date(2024, 3, 1)),
        ]
        db = _mock_db_session(versions)

        service = WpTemplateVersionService(db)
        result = await service.list_versions()

        assert len(result) == 2
        assert result[0].version == "v2025-R5"
        assert result[1].version == "v2024-R3"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_versions(self):
        """Should return empty list when no versions exist."""
        db = _mock_db_session([])

        service = WpTemplateVersionService(db)
        result = await service.list_versions()

        assert result == []


# ─── get_version_by_id ───────────────────────────────────────────────────────


class TestGetVersionById:
    """Test get_version_by_id returns specific version or raises 404."""

    @pytest.mark.asyncio
    async def test_returns_version_by_id(self):
        """Should return the version matching the given ID."""
        vid = uuid.uuid4()
        version = _make_version("v2025-R5", version_id=vid)
        db = _mock_db_session(version)

        service = WpTemplateVersionService(db)
        result = await service.get_version_by_id(vid)

        assert result.id == vid
        assert result.version == "v2025-R5"

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise HTTPException 404 when version ID doesn't exist."""
        from fastapi import HTTPException

        db = _mock_db_session(None)

        service = WpTemplateVersionService(db)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_version_by_id(uuid.uuid4())

        assert exc_info.value.status_code == 404
