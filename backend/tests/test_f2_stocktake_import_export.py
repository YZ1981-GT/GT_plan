import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.main import app
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_f2_st_export_rejects_f2_21():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/workpapers/test-wp/f2-st/export-template?sheet=F2-21",
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_f2_st_export_template_f2_24():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/workpapers/test-wp/f2-st/export-template?sheet=F2-24",
        )
    assert response.status_code == 200
    assert "spreadsheet" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_f2_st_supported_sheets():
    from app.routers.wp_render_strategies._f2_stocktake_import_export import _SUPPORTED

    assert _SUPPORTED == {"F2-24", "F2-24-count", "F2-25", "F2-25-floor", "F2-26", "F2-26-after"}
