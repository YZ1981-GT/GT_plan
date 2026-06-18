"""A18-1 prefilled-download — A17 小结注入 + 占位符替换."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from docx import Document
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User, UserRole

ADMIN_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TEST_PROJECT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
TEST_CLIENT_NAME = "北京测试科技有限公司"
TEST_AUDIT_YEAR = "2025"
SAMPLE_SUMMARY = "【审计业务约定范围】\n约定范围测试内容"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _make_fake_project():
    proj = MagicMock()
    proj.id = TEST_PROJECT_ID
    proj.client_name = TEST_CLIENT_NAME
    proj.audit_period_end = date(int(TEST_AUDIT_YEAR), 12, 31)
    return proj


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
    app.dependency_overrides[require_project_access("readonly")] = _override_user
    return app


def _extract_docx_text(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    parts = [p.text for p in doc.paragraphs]
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_a18_1_prefilled_download_valid_docx(db_session: AsyncSession) -> None:
    fake_proj = _make_fake_project()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_proj
    db_session.execute = AsyncMock(return_value=fake_result)

    mock_summary = {
        "summary_sections": [{"title": "审计业务约定范围", "content": "约定范围测试内容"}],
        "formatted_text": SAMPLE_SUMMARY,
        "source": "A17-1",
        "completeness": 0.2,
        "message": None,
        "summary_injected": True,
    }

    app = _make_app(db_session)

    async def _fake_enrich(doc, db, project_id, client_name, audit_year):
        from app.services.a18_summary_generator import (
            apply_replacements_to_document,
            append_summary_to_document,
            build_a18_1_replacements,
        )

        apply_replacements_to_document(
            doc, build_a18_1_replacements(client_name, audit_year)
        )
        append_summary_to_document(doc, mock_summary)
        return mock_summary

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        with patch(
            "app.services.a18_summary_generator.enrich_a18_1_document",
            side_effect=_fake_enrich,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    f"/api/projects/{TEST_PROJECT_ID}/wp-templates/A18-1/prefilled-download"
                )

    assert resp.status_code == 200
    content = resp.content
    assert content[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        assert "[Content_Types].xml" in zf.namelist()

    text = _extract_docx_text(content)
    assert TEST_CLIENT_NAME in text
    assert "约定范围测试内容" in text
    assert "审计情况小结" in text


@pytest.mark.asyncio
async def test_generate_summary_api_shape(db_session: AsyncSession) -> None:
    from app.routers.a18_regulatory import get_a18_generated_summary

    mock_result = {
        "summary_sections": [{"title": "审计结论", "content": "无保留意见"}],
        "formatted_text": "【审计结论】\n无保留意见",
        "completeness": 0.2,
        "source": "A17-1",
        "message": None,
    }

    with patch(
        "app.routers.a18_regulatory.generate_audit_summary",
        new=AsyncMock(return_value=mock_result),
    ):
        result = await get_a18_generated_summary(TEST_PROJECT_ID, db_session, MagicMock())

    assert result["completeness"] == 0.2
    assert "无保留意见" in result["formatted_text"]
