"""deliverable.py 路由 P0 端点测试 — Task 6（预览 URL 与不支持格式降级）

覆盖：
  - 6.4 单元测试：docx/pdf 预览端点（5.1/5.2/5.3）
  - 6.3 PBT Property 15：不支持格式降级提示（5.4）

通过直接调用路由函数验证逻辑（in-process，无需 uvicorn）。

Feature: audit-report-deliverable-center
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.models.report_models import AuditReport
from app.routers.deliverable import preview_version
from app.services.deliverable_service import DeliverableService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_DELIVERABLE_TABLES = [
    User.__table__,
    Project.__table__,
    WordExportTask.__table__,
    WordExportTaskVersion.__table__,
    AuditReport.__table__,
]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    user = User(
        id=user_id,
        username=f"dr_{suffix}",
        email=f"dr_{suffix}@test.com",
        hashed_password="x",
        role=UserRole.manager,
    )
    db_session.add(user)
    project = Project(
        id=project_id,
        name="路由测试项目",
        client_name="客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=user_id,
    )
    db_session.add(project)
    await db_session.flush()
    return {"project_id": project_id, "user_id": user_id, "user": user}


async def _make_version(
    db: AsyncSession, seeded: dict, *, file_path: str | None, html_path: str | None = None
):
    """创建一个 editing 态交付物及一个版本，返回 (task, version)。"""
    svc = DeliverableService(db)
    task = await svc.create_task(
        seeded["project_id"], "audit_report", "soe", seeded["user_id"]
    )
    task.status = WordExportStatus.editing.value
    await db.flush()
    version = await svc.create_version(
        task.id,
        file_path=file_path,
        html_path=html_path,
        user_id=seeded["user_id"],
    )
    return task, version


# ───────────────────────── 6.4 单元测试：docx/pdf 预览端点 ─────────────────────────


@pytest.mark.asyncio
async def test_preview_docx_returns_download_url(db_session, seeded):
    """5.2: .docx 版本预览返回 docx 类型 + 下载链接。"""
    task, version = await _make_version(
        db_session, seeded, file_path="/tmp/report.docx"
    )
    result = await preview_version(
        seeded["project_id"], task.id, version.version_no, db=db_session,
        current_user=seeded["user"],
    )
    assert result["preview_type"] == "docx"
    assert result["url"] is not None
    assert "/download" in result["url"]


@pytest.mark.asyncio
async def test_preview_pdf_returns_download_url(db_session, seeded):
    """5.3: .pdf 版本预览返回 pdf 类型 + 下载链接。"""
    task, version = await _make_version(
        db_session, seeded, file_path="/tmp/report.pdf"
    )
    result = await preview_version(
        seeded["project_id"], task.id, version.version_no, db=db_session,
        current_user=seeded["user"],
    )
    assert result["preview_type"] == "pdf"
    assert result["url"] is not None
    assert "/download" in result["url"]


@pytest.mark.asyncio
async def test_preview_html_path_preferred(db_session, seeded, tmp_path):
    """5.1: 存在 html_path 时优先返回 html 预览。"""
    html_file = tmp_path / "report.html"
    html_file.write_text("<html><body>预览</body></html>", encoding="utf-8")
    task, version = await _make_version(
        db_session, seeded, file_path="/tmp/report.docx", html_path=str(html_file)
    )
    result = await preview_version(
        seeded["project_id"], task.id, version.version_no, db=db_session,
        current_user=seeded["user"],
    )
    assert result["preview_type"] == "html"
    assert result["html_path"] == str(html_file)


# ───────────────────────── 6.3 PBT Property 15：不支持格式降级提示 ─────────────────────────


@settings(max_examples=3, deadline=None)
@given(
    suffix=st.sampled_from([".xlsx", ".txt", ".csv", ".zip", ".pptx", ".odt", ""])
)
@pytest.mark.asyncio
async def test_unsupported_format_downgrade(suffix):
    # Feature: audit-report-deliverable-center, Property 15: 不支持格式降级提示
    """Property 15: 对任一后缀不属于 {.docx,.pdf} 的版本，预览返回降级提示并附下载链接，不渲染。

    Validates: Requirements 5.4
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            user_id = uuid.uuid4()
            project_id = uuid.uuid4()
            user = User(
                id=user_id,
                username=f"pbt_{user_id.hex[:8]}",
                email=f"pbt_{user_id.hex[:8]}@test.com",
                hashed_password="x",
                role=UserRole.manager,
            )
            db.add(user)
            db.add(
                Project(
                    id=project_id,
                    name="PBT项目",
                    client_name="客户",
                    project_type=ProjectType.annual,
                    status=ProjectStatus.planning,
                    created_by=user_id,
                )
            )
            await db.flush()

            seeded = {"project_id": project_id, "user_id": user_id, "user": user}
            task, version = await _make_version(
                db, seeded, file_path=f"/tmp/deliverable{suffix}"
            )
            result = await preview_version(
                project_id, task.id, version.version_no, db=db, current_user=user,
            )
            assert result["preview_type"] == "unsupported"
            assert result.get("url") is not None
            assert "/download" in result["url"]
            assert result.get("message")
    finally:
        await engine.dispose()
