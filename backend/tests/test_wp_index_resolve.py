"""Tests for GET /api/wp-index-resolve endpoint.

Validates: Requirements 3.11.9（11 命名空间）
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User, UserRole
from app.routers.wp_index_resolve import _parse_ref, router


# ─── Unit tests for _parse_ref ───────────────────────────────────────────────


class TestParseRef:
    """Test the ref parsing logic (mirrors frontend parseIndexRef)."""

    def test_strict_mode_wp(self):
        result = _parse_ref("wp:D2")
        assert result == ("wp", 3, "D2")

    def test_strict_mode_sheet(self):
        result = _parse_ref("sheet:D2-1")
        assert result == ("sheet", 2, "D2-1")

    def test_strict_mode_cell(self):
        result = _parse_ref("cell:D2-1!B23")
        assert result == ("cell", 1, "D2-1!B23")

    def test_strict_mode_note(self):
        result = _parse_ref("Note:五-1-1")
        assert result == ("Note", 4, "五-1-1")

    def test_strict_mode_tb(self):
        result = _parse_ref("TB:1122")
        assert result == ("TB", 4, "1122")

    def test_strict_mode_adj(self):
        result = _parse_ref("Adj:AJE-001")
        assert result == ("Adj", 4, "AJE-001")

    def test_strict_mode_att(self):
        result = _parse_ref("Att:some-uuid")
        assert result == ("Att", 4, "some-uuid")

    def test_strict_mode_eqcr(self):
        result = _parse_ref("EQCR:RID")
        assert result == ("EQCR", 4, "RID")

    def test_strict_mode_calc(self):
        result = _parse_ref("Calc:depreciation")
        assert result == ("Calc", 4, "depreciation")

    def test_strict_mode_sample(self):
        result = _parse_ref("Sample:F2-VAL")
        assert result == ("Sample", 4, "F2-VAL")

    def test_strict_mode_confirm(self):
        result = _parse_ref("Confirm:D0-001")
        assert result == ("Confirm", 4, "D0-001")

    def test_strict_mode_case_insensitive(self):
        """Namespace matching is case-insensitive."""
        result = _parse_ref("WP:D2")
        assert result == ("wp", 3, "D2")

        result = _parse_ref("note:五-1-1")
        assert result == ("Note", 4, "五-1-1")

        result = _parse_ref("tb:1122")
        assert result == ("TB", 4, "1122")

    def test_loose_mode_wp_code(self):
        """Main workpaper code (D2, E1) → wp namespace, layer 3."""
        result = _parse_ref("D2")
        assert result == ("wp", 3, "D2")

    def test_loose_mode_sheet_ref_dash(self):
        """Sheet ref with dash (D2-1) → sheet namespace, layer 2."""
        result = _parse_ref("D2-1")
        assert result == ("sheet", 2, "D2-1")

    def test_loose_mode_sheet_ref_letter_suffix(self):
        """Sheet ref with letter suffix (D2A) → sheet namespace, layer 2."""
        result = _parse_ref("D2A")
        assert result == ("sheet", 2, "D2A")

    def test_loose_mode_cell_ref_with_bang(self):
        """Cell ref with ! (D2-1!B23) → cell namespace, layer 1."""
        result = _parse_ref("D2-1!B23")
        assert result == ("cell", 1, "D2-1!B23")

    def test_loose_mode_case_normalization(self):
        """Loose mode normalizes to uppercase."""
        result = _parse_ref("d2")
        assert result == ("wp", 3, "D2")

        result = _parse_ref("d2-1")
        assert result == ("sheet", 2, "D2-1")

    def test_gt_custom_returns_none(self):
        """GT_Custom refs are not resolvable."""
        assert _parse_ref("GT_Custom_something") is None

    def test_empty_string_returns_none(self):
        assert _parse_ref("") is None

    def test_whitespace_only_returns_none(self):
        assert _parse_ref("   ") is None

    def test_spaces_trimmed(self):
        """Leading/trailing spaces are trimmed."""
        result = _parse_ref("  wp:D2  ")
        assert result == ("wp", 3, "D2")

    def test_invalid_ref_returns_none(self):
        """Invalid refs that don't match any pattern return None."""
        assert _parse_ref("invalid") is None
        assert _parse_ref("123") is None
        assert _parse_ref("Z1") is None  # Z is not in A-S range

    def test_strict_mode_empty_target_returns_none(self):
        """Strict mode with empty target returns None."""
        assert _parse_ref("wp:") is None
        assert _parse_ref("wp:   ") is None

    def test_multi_level_sheet_ref(self):
        """Multi-level sheet ref (D2-1-1) → sheet namespace."""
        result = _parse_ref("D2-1-1")
        assert result == ("sheet", 2, "D2-1-1")


# ─── Integration tests (endpoint) ───────────────────────────────────────────


_USER_ID = uuid.uuid4()


class _FakeUser:
    id = _USER_ID
    username = "test_user"
    role = UserRole.admin


def _make_app(db_session: AsyncSession | None = None) -> FastAPI:
    """Create a minimal FastAPI app with the wp-index-resolve router."""
    app = FastAPI()
    app.include_router(router)

    async def _user():
        return _FakeUser()

    app.dependency_overrides[get_current_user] = _user

    if db_session:
        async def _db():
            yield db_session
        app.dependency_overrides[get_db] = _db

    return app


@pytest.mark.asyncio
async def test_external_namespace_always_exists():
    """External module namespaces (Note/TB/Adj/etc.) always return exists=true."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "Note:五-1-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["trimmed"] is False
    assert data["ns"] == "Note"
    assert data["layer"] == 4
    assert data["target"] == "五-1-1"


@pytest.mark.asyncio
async def test_external_namespace_tb():
    """TB namespace returns exists=true."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "TB:1122"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["ns"] == "TB"
    assert data["layer"] == 4


@pytest.mark.asyncio
async def test_external_namespace_adj():
    """Adj namespace returns exists=true."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "Adj:AJE-001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["ns"] == "Adj"
    assert data["layer"] == 4


@pytest.mark.asyncio
async def test_external_namespace_eqcr():
    """EQCR namespace returns exists=true."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "EQCR:RID"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["ns"] == "EQCR"
    assert data["layer"] == 4


@pytest.mark.asyncio
async def test_external_namespace_calc():
    """Calc namespace returns exists=true."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "Calc:depreciation"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["ns"] == "Calc"
    assert data["layer"] == 4


@pytest.mark.asyncio
async def test_external_namespace_sample():
    """Sample namespace returns exists=true."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "Sample:F2-VAL"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["ns"] == "Sample"
    assert data["layer"] == 4


@pytest.mark.asyncio
async def test_external_namespace_confirm():
    """Confirm namespace returns exists=true."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "Confirm:D0-001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["ns"] == "Confirm"
    assert data["layer"] == 4


@pytest.mark.asyncio
async def test_invalid_ref_returns_422():
    """Invalid ref format returns 422."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "invalid_ref_xyz"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_gt_custom_returns_422():
    """GT_Custom refs return 422 (not resolvable)."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "GT_Custom_test"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_wp_namespace_without_project_id():
    """wp namespace without project_id returns exists=true (cannot validate)."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "wp:D2"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["ns"] == "wp"
    assert data["layer"] == 3
    assert data["target"] == "D2"


@pytest.mark.asyncio
async def test_loose_mode_wp_code():
    """Loose mode workpaper code resolves correctly."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "D2"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ns"] == "wp"
    assert data["layer"] == 3
    assert data["target"] == "D2"


@pytest.mark.asyncio
async def test_loose_mode_sheet_ref():
    """Loose mode sheet ref resolves correctly."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "D2-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ns"] == "sheet"
    assert data["layer"] == 2
    assert data["target"] == "D2-1"


@pytest.mark.asyncio
async def test_loose_mode_cell_ref():
    """Loose mode cell ref resolves correctly."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "D2-1!B23"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ns"] == "cell"
    assert data["layer"] == 1
    assert data["target"] == "D2-1!B23"


@pytest.mark.asyncio
async def test_case_insensitive_namespace():
    """Namespace matching is case-insensitive in strict mode."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve", params={"ref": "WP:D2"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ns"] == "wp"
    assert data["target"] == "D2"


@pytest.mark.asyncio
async def test_missing_ref_param_returns_422():
    """Missing required ref param returns 422."""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/wp-index-resolve")
    assert resp.status_code == 422
