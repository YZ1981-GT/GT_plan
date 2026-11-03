"""普通附件下载/预览必须在项目级 realpath 边界内。"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user, get_current_user_stream
from app.models.attachment_models import Attachment
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, UserRole
from app.routers import attachments as attachment_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


class _Admin:
    id = uuid.uuid4()
    role = UserRole.admin
    username = "attachment-boundary-admin"
    email = "attachment-boundary@example.test"
    is_active = True


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "attachments"
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(root))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[Project.__table__, Attachment.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        project = Project(
            id=uuid.uuid4(), name="【测试】附件边界", client_name="测试",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
        )
        db.add(project)
        await db.flush()

        app = FastAPI()
        app.include_router(attachment_router.router)

        async def _db():
            yield db

        async def _user():
            return _Admin()

        async def _visible(*_args, **_kwargs):
            return None

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_current_user_stream] = _user
        monkeypatch.setattr(attachment_router, "enforce_attachment_wp_visibility", _visible)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield db, project, root, client
    await engine.dispose()


async def _attachment(db: AsyncSession, project: Project, path: Path, name: str = "证据.pdf") -> Attachment:
    row = Attachment(
        project_id=project.id, file_name=name, file_path=str(path), file_type=Path(name).suffix.lstrip("."),
        file_size=path.stat().st_size if path.is_file() else 0, attachment_type="evidence",
        storage_type="local", ocr_status="pending",
    )
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_download_and_preview_read_only_own_project_file(world):
    db, project, root, client = world
    path = root / str(project.id) / "evidence" / "证据.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"%PDF-safe")
    row = await _attachment(db, project, path)

    download = await client.get(f"/api/attachments/{row.id}/download")
    preview = await client.get(f"/api/attachments/{row.id}/preview")
    assert download.status_code == preview.status_code == 200
    assert download.content == preview.content == b"%PDF-safe"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert preview.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["outside", "cross_project", "symlink"])
async def test_download_rejects_outside_cross_project_and_symlink(world, shape: str):
    db, project, root, client = world
    if shape == "outside":
        path = root.parent / "secret.pdf"
        path.write_bytes(b"secret")
    elif shape == "cross_project":
        path = root / str(uuid.uuid4()) / "evidence" / "other.pdf"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"other")
    else:
        outside = root.parent / "secret-target.pdf"
        outside.write_bytes(b"secret")
        path = root / str(project.id) / "evidence" / "escape.pdf"
        path.parent.mkdir(parents=True)
        try:
            os.symlink(outside, path)
        except (OSError, NotImplementedError):
            pytest.skip("当前环境不允许创建符号链接")
    row = await _attachment(db, project, path)
    response = await client.get(f"/api/attachments/{row.id}/download")
    assert response.status_code == 404
    assert b"secret" not in response.content and b"other" not in response.content


@pytest.mark.asyncio
async def test_svg_is_download_only_and_never_inline(world):
    db, project, root, client = world
    path = root / str(project.id) / "evidence" / "active.svg"
    path.parent.mkdir(parents=True)
    payload = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    path.write_bytes(payload)
    row = await _attachment(db, project, path, name="active.svg")

    preview = await client.get(f"/api/attachments/{row.id}/preview")
    download = await client.get(f"/api/attachments/{row.id}/download")
    assert preview.status_code == 200
    assert preview.json()["previewable"] is False
    assert payload not in preview.content
    assert download.status_code == 200 and download.content == payload
    assert download.headers["content-disposition"].startswith("attachment;")
