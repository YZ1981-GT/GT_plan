"""附件列表分页、汇总、稳定排序和 resolved capabilities。"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.attachment_models import Attachment  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole  # noqa: E402
from app.routers import attachments as router_module  # noqa: E402
from app.services.attachment_service import AttachmentService  # noqa: E402


@pytest_asyncio.fixture
async def world() -> AsyncIterator[dict]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[User.__table__, Project.__table__, Attachment.__table__],
        ))
        await conn.execute(sa.text(
            "CREATE TABLE attachment_working_paper (id CHAR(32), attachment_id CHAR(32), wp_id CHAR(32), "
            "association_type VARCHAR(32), notes TEXT, created_by CHAR(32), created_at DATETIME)"
        ))
        await conn.execute(sa.text(
            "CREATE TABLE evidence_links (id CHAR(32), attachment_id CHAR(32), wp_id CHAR(32), "
            "sheet_name TEXT, cell_ref TEXT, page_ref TEXT, evidence_type TEXT, check_conclusion TEXT, "
            "voucher_key TEXT, contract_key TEXT, created_by CHAR(32), created_at DATETIME)"
        ))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(
            id=uuid.uuid4(), username="page-admin", email="page@example.test",
            hashed_password="x", role=UserRole.admin, is_active=True,
        )
        project = Project(
            id=uuid.uuid4(), name="【测试】分页", client_name="测试", audit_year=2025,
            project_type=ProjectType.annual, status=ProjectStatus.execution,
        )
        db.add_all((user, project))
        await db.flush()
        now = datetime.now(timezone.utc)
        rows = []
        for index in range(55):
            rows.append(Attachment(
                id=uuid.UUID(int=index + 1), project_id=project.id, audit_year=2025,
                file_name=f"证据-{index:02d}.pdf", file_path=f"local-{index}", file_type="pdf",
                file_size=index + 1, attachment_type="evidence", storage_type="local",
                ocr_status="completed" if index < 20 else "pending", state="available",
                created_at=now, updated_at=now,
            ))
        db.add_all(rows)
        await db.flush()
        await db.execute(sa.text(
            "INSERT INTO attachment_working_paper "
            "(id, attachment_id, wp_id, association_type, created_at) "
            "VALUES (:id, :aid, :wid, 'evidence', CURRENT_TIMESTAMP)"
        ), {"id": uuid.uuid4().hex, "aid": rows[0].id.hex, "wid": uuid.uuid4().hex})
        await db.commit()
        yield {"db": db, "user": user, "project": project, "rows": rows}
    await engine.dispose()


@pytest.mark.asyncio
async def test_page_envelope_has_stable_non_overlapping_rows_and_full_summary(world: dict) -> None:
    service = AttachmentService(world["db"])
    first = await service.list_attachments(world["project"].id, page=1, page_size=20)
    second = await service.list_attachments(world["project"].id, page=2, page_size=20)

    assert isinstance(first, dict) and isinstance(second, dict)
    assert first["total"] == second["total"] == 55
    assert (first["page"], first["page_size"]) == (1, 20)
    first_ids = [item["id"] for item in first["items"]]
    second_ids = [item["id"] for item in second["items"]]
    assert len(first_ids) == len(second_ids) == 20
    assert set(first_ids).isdisjoint(second_ids)
    # created_at 相同时由 id DESC 作确定性次序。
    assert first_ids == [str(uuid.UUID(int=value)) for value in range(55, 35, -1)]
    assert first["summary"] == {
        "total_size": sum(range(1, 56)),
        "ocr_completed": 20,
        "linked_count": 1,
    }


@pytest.mark.asyncio
async def test_filtered_page_summary_uses_filtered_full_result_not_current_page(world: dict) -> None:
    result = await AttachmentService(world["db"]).list_attachments(
        world["project"].id, q="证据-0", page=1, page_size=3,
    )
    assert isinstance(result, dict)
    assert len(result["items"]) == 3
    assert result["total"] == 10
    assert result["summary"]["total_size"] == sum(range(1, 11))


@pytest.mark.asyncio
async def test_endpoint_returns_capabilities_and_rejects_oversized_page(world: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(router_module.router)

    async def _db():
        yield world["db"]

    async def _user():
        return world["user"]

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/projects/{world['project'].id}/attachments?page=1&page_size=10"
        )
        too_large = await client.get(
            f"/api/projects/{world['project'].id}/attachments?page=1&page_size=201"
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 55 and len(body["items"]) == 10
    assert body["capabilities"] == {
        "upload": True, "associate": True, "ocr_confirm": True, "ocr_retry": True,
    }
    assert too_large.status_code == 422
