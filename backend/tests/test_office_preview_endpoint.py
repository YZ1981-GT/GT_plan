"""AT-2 Office 文件在线预览后端单测

spec proposal-remaining-18 task 5.2

覆盖：
- LibreOffice 不可用 → 503 + reason="libreoffice_unavailable"
- 附件不存在 → 404
- 附件类型非 Office → 400
- 转换成功（mock subprocess）→ 200 + application/pdf
- 缓存命中：第二次调用不再调 subprocess
- 转换超时 → 500
- 转换失败（非零退出码）→ 500
- 健康检查端点：available 字段切换
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.routers.office_preview import router as office_preview_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


PROJECT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    def __init__(self, role: UserRole = UserRole.admin) -> None:
        self.id = USER_ID
        self.role = role
        self.email = "tester@example.com"
        self.username = "tester"
        self.is_active = True


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        tables = [
            User.__table__,
            Project.__table__,
            WpIndex.__table__,
            WorkingPaper.__table__,
            Attachment.__table__,
            AttachmentWorkingPaper.__table__,
        ]
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=tables))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _make_app(db_session: AsyncSession, role: UserRole = UserRole.admin) -> FastAPI:
    app = FastAPI()
    app.include_router(office_preview_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(role=role)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


async def _seed_attachment(
    db: AsyncSession,
    *,
    src_path: Path,
    file_name: str = "test.docx",
) -> uuid.UUID:
    db.add(Project(
        id=PROJECT_ID,
        name="OfficePreview 测试",
        client_name="OP Test",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=USER_ID,
    ))
    await db.flush()
    att = Attachment(
        project_id=PROJECT_ID,
        file_name=file_name,
        file_path=str(src_path),
        file_type=Path(file_name).suffix.lstrip(".").lower(),
        file_size=src_path.stat().st_size if src_path.exists() else 0,
        attachment_type="general",
        storage_type="local",
        ocr_status="completed",
        created_by=USER_ID,
    )
    db.add(att)
    await db.flush()
    return att.id


# ---------------------------------------------------------------------------
# 1. LibreOffice 不可用 → 503
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_503_when_libreoffice_unavailable(db_session: AsyncSession, tmp_path: Path) -> None:
    src = tmp_path / "test.docx"
    src.write_bytes(b"fake docx content")
    aid = await _seed_attachment(db_session, src_path=src)

    app = _make_app(db_session)
    transport = ASGITransport(app=app)

    with patch("app.routers.office_preview._find_libreoffice", return_value=None):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/attachments/{aid}/preview-pdf")

    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["reason"] == "libreoffice_unavailable"
    assert "下载" in body["detail"]["message"] or "LibreOffice" in body["detail"]["message"]


# ---------------------------------------------------------------------------
# 2. 附件不存在 → 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_404_when_attachment_missing(db_session: AsyncSession) -> None:
    db_session.add(Project(
        id=PROJECT_ID, name="x", client_name="x",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=USER_ID,
    ))
    await db_session.flush()

    app = _make_app(db_session)
    transport = ASGITransport(app=app)
    fake_id = uuid.uuid4()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/attachments/{fake_id}/preview-pdf")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. 非 Office 类型 → 400
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_400_when_file_type_not_office(db_session: AsyncSession, tmp_path: Path) -> None:
    src = tmp_path / "image.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n")
    aid = await _seed_attachment(db_session, src_path=src, file_name="image.png")

    app = _make_app(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/attachments/{aid}/preview-pdf")
    assert resp.status_code == 400
    assert "Office" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 4. 转换成功 → 200 + application/pdf（mock subprocess）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_convert_success_returns_pdf(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "test.docx"
    src.write_bytes(b"fake docx content for conversion")
    aid = await _seed_attachment(db_session, src_path=src)

    cache_dir = tmp_path / "preview_cache"
    monkeypatch.setenv("OFFICE_PREVIEW_CACHE_DIR", str(cache_dir))

    fake_pdf_bytes = b"%PDF-1.7\n%fake-pdf-content\n%%EOF\n"

    def _fake_subprocess_run(cmd, capture_output=False, timeout=None, **kwargs):
        # cmd: [soffice, --headless, --convert-to, pdf, --outdir, tmpdir, src_path]
        outdir = Path(cmd[5])
        src_path = Path(cmd[6])
        (outdir / f"{src_path.stem}.pdf").write_bytes(fake_pdf_bytes)
        return MagicMock(returncode=0, stderr=b"", stdout=b"")

    app = _make_app(db_session)
    transport = ASGITransport(app=app)

    with patch("app.routers.office_preview._find_libreoffice", return_value="/usr/bin/libreoffice"), \
         patch("app.routers.office_preview.subprocess.run", side_effect=_fake_subprocess_run) as mock_run:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/attachments/{aid}/preview-pdf")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content == fake_pdf_bytes
    assert mock_run.call_count == 1
    # 缓存文件已写入
    assert cache_dir.exists()
    assert any(p.suffix == ".pdf" for p in cache_dir.iterdir())


# ---------------------------------------------------------------------------
# 5. 缓存命中：第二次调用不再调 subprocess
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_skips_subprocess(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "test.xlsx"
    src.write_bytes(b"fake xlsx content for cache test")
    aid = await _seed_attachment(db_session, src_path=src, file_name="test.xlsx")

    cache_dir = tmp_path / "preview_cache"
    monkeypatch.setenv("OFFICE_PREVIEW_CACHE_DIR", str(cache_dir))

    fake_pdf_bytes = b"%PDF-1.7\nfake\n%%EOF"

    def _fake_subprocess_run(cmd, capture_output=False, timeout=None, **kwargs):
        outdir = Path(cmd[5])
        src_path = Path(cmd[6])
        (outdir / f"{src_path.stem}.pdf").write_bytes(fake_pdf_bytes)
        return MagicMock(returncode=0, stderr=b"")

    app = _make_app(db_session)
    transport = ASGITransport(app=app)

    with patch("app.routers.office_preview._find_libreoffice", return_value="/usr/bin/soffice"), \
         patch("app.routers.office_preview.subprocess.run", side_effect=_fake_subprocess_run) as mock_run:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 第一次：转换
            r1 = await client.get(f"/api/attachments/{aid}/preview-pdf")
            assert r1.status_code == 200
            assert r1.content == fake_pdf_bytes
            # 第二次：缓存命中
            r2 = await client.get(f"/api/attachments/{aid}/preview-pdf")
            assert r2.status_code == 200
            assert r2.content == fake_pdf_bytes

    # subprocess 仅调用 1 次（缓存命中第二次跳过）
    assert mock_run.call_count == 1


# ---------------------------------------------------------------------------
# 6. 转换超时 → 500
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_500_on_conversion_timeout(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "huge.docx"
    src.write_bytes(b"fake")
    aid = await _seed_attachment(db_session, src_path=src)

    monkeypatch.setenv("OFFICE_PREVIEW_CACHE_DIR", str(tmp_path / "preview_cache"))

    def _timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=90)

    app = _make_app(db_session)
    transport = ASGITransport(app=app)
    with patch("app.routers.office_preview._find_libreoffice", return_value="/usr/bin/libreoffice"), \
         patch("app.routers.office_preview.subprocess.run", side_effect=_timeout):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/attachments/{aid}/preview-pdf")

    assert resp.status_code == 500
    assert "超时" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 7. 转换失败（非零退出码）→ 500
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_500_on_nonzero_exit(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "broken.docx"
    src.write_bytes(b"corrupt")
    aid = await _seed_attachment(db_session, src_path=src)

    monkeypatch.setenv("OFFICE_PREVIEW_CACHE_DIR", str(tmp_path / "preview_cache"))

    app = _make_app(db_session)
    transport = ASGITransport(app=app)
    with patch("app.routers.office_preview._find_libreoffice", return_value="/usr/bin/libreoffice"), \
         patch(
             "app.routers.office_preview.subprocess.run",
             return_value=MagicMock(returncode=1, stderr=b"file format error"),
         ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/attachments/{aid}/preview-pdf")

    assert resp.status_code == 500
    assert "PDF 转换失败" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 8. 源文件不存在 → 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_404_when_source_file_missing(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    fake_path = tmp_path / "ghost.docx"
    # 不写入文件
    db_session.add(Project(
        id=PROJECT_ID, name="x", client_name="x",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=USER_ID,
    ))
    await db_session.flush()
    att = Attachment(
        project_id=PROJECT_ID, file_name="ghost.docx",
        file_path=str(fake_path),
        file_type="docx", file_size=100,
        attachment_type="general", storage_type="local",
        ocr_status="pending", created_by=USER_ID,
    )
    db_session.add(att)
    await db_session.flush()

    app = _make_app(db_session)
    transport = ASGITransport(app=app)
    with patch("app.routers.office_preview._find_libreoffice", return_value="/usr/bin/libreoffice"):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/attachments/{att.id}/preview-pdf")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 9. 健康检查端点：available 切换
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_endpoint_unavailable(db_session: AsyncSession) -> None:
    app = _make_app(db_session)
    transport = ASGITransport(app=app)
    with patch("app.routers.office_preview._find_libreoffice", return_value=None):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/office-preview/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["reason"] == "libreoffice_unavailable"


@pytest.mark.asyncio
async def test_health_endpoint_available(db_session: AsyncSession) -> None:
    app = _make_app(db_session)
    transport = ASGITransport(app=app)
    with patch("app.routers.office_preview._find_libreoffice", return_value="/usr/bin/libreoffice"):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/office-preview/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["soffice_path"] == "/usr/bin/libreoffice"


# ---------------------------------------------------------------------------
# 10. 路由注册：office_preview 在 router_registry.system 中
# ---------------------------------------------------------------------------

def test_router_registered_in_system_registry() -> None:
    """新增路由必须注册到 router_registry.system §118"""
    import inspect
    import app.router_registry.system as mod

    src = inspect.getsource(mod)
    assert "office_preview" in src, "office_preview 必须在 router_registry.system 中注册"
    assert "§118" in src, "应包含 §118 编号"
