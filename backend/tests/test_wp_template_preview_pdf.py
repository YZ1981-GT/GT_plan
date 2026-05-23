"""WpTemplate PDF 预览端点测试 — 模板库实时预览（AT-2 扩展）

覆盖：
- LibreOffice 不可用 → 503 + reason="libreoffice_unavailable"
- 模板不存在 → 404
- 转换成功 → 200 + application/pdf + X-Preview-Cache=miss/hit
- 缓存命中 → 第 2 次调用 X-Preview-Cache=hit 且 subprocess.run 仅调一次

绕开：
- set_rls_context 在 SQLite 测试环境下 mock 为 no-op（生产是 PG set_config）
- require_project_access 对 admin 用户走"set RLS + 放行"短路
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User, UserRole

ADMIN_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """空 in-memory engine（端点不查 DB）。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _make_app(db_session: AsyncSession) -> FastAPI:
    from app.routers.wp_template_download import router as wp_dl_router

    app = FastAPI()
    app.include_router(wp_dl_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return User(
            id=ADMIN_USER_ID,
            username="test_admin",
            email="admin@test.com",
            hashed_password="x",
            role=UserRole.admin,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


@pytest.mark.asyncio
async def test_503_when_libreoffice_unavailable(db_session: AsyncSession, tmp_path: Path) -> None:
    """LibreOffice 不可用 → 503 + reason=libreoffice_unavailable。"""
    fake_xlsx = tmp_path / "D2.xlsx"
    fake_xlsx.write_bytes(b"fake xlsx")

    project_id = str(uuid.uuid4())
    with patch("app.routers.wp_template_download.find_all_template_files", return_value=[fake_xlsx]), \
         patch("app.routers.wp_template_download._find_libreoffice", return_value=None), \
         patch("app.deps.set_rls_context", new=AsyncMock()):
        app = _make_app(db_session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/projects/{project_id}/wp-templates/D2/preview-pdf")

    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["reason"] == "libreoffice_unavailable"


@pytest.mark.asyncio
async def test_404_when_template_not_found(db_session: AsyncSession) -> None:
    """模板不存在 → 404。"""
    project_id = str(uuid.uuid4())
    with patch("app.routers.wp_template_download.find_all_template_files", return_value=[]), \
         patch("app.routers.wp_template_download.find_template_file_any", return_value=None), \
         patch("app.deps.set_rls_context", new=AsyncMock()):
        app = _make_app(db_session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/projects/{project_id}/wp-templates/UNKNOWN/preview-pdf")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_conversion_success_and_cache(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """200 + application/pdf；二次请求命中缓存（subprocess 仅调一次）。"""
    fake_xlsx = tmp_path / "D2.xlsx"
    fake_xlsx.write_bytes(b"fake xlsx content for preview")

    storage_root = tmp_path
    cache_dir = storage_root / "preview_cache"

    from app.core import config as cfg_mod
    monkeypatch.setattr(cfg_mod.settings, "STORAGE_ROOT", str(storage_root))

    fake_pdf_bytes = b"%PDF-1.4 fake content"

    def _fake_subprocess_run(cmd, capture_output=False, timeout=None, **kwargs):
        outdir = Path(cmd[5])
        src = Path(cmd[6])
        (outdir / f"{src.stem}.pdf").write_bytes(fake_pdf_bytes)
        return MagicMock(returncode=0, stderr=b"")

    project_id = str(uuid.uuid4())
    with patch("app.routers.wp_template_download.find_all_template_files", return_value=[fake_xlsx]), \
         patch("app.routers.wp_template_download._find_libreoffice", return_value="/usr/bin/soffice"), \
         patch("app.routers.wp_template_download.subprocess.run", side_effect=_fake_subprocess_run) as mock_run, \
         patch("app.deps.set_rls_context", new=AsyncMock()):
        app = _make_app(db_session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r1 = await client.get(f"/api/projects/{project_id}/wp-templates/D2/preview-pdf")
            r2 = await client.get(f"/api/projects/{project_id}/wp-templates/D2/preview-pdf")

    assert r1.status_code == 200
    assert r1.headers["content-type"] == "application/pdf"
    assert r1.headers["x-preview-cache"] == "miss"
    assert r1.content == fake_pdf_bytes

    assert r2.status_code == 200
    assert r2.headers["x-preview-cache"] == "hit"
    assert mock_run.call_count == 1
    assert cache_dir.exists()
    assert any(p.suffix == ".pdf" for p in cache_dir.iterdir())
