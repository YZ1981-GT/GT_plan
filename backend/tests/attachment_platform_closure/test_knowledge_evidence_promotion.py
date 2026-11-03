"""知识文档版本显式晋升项目证据的端点与快照契约。"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.config import settings  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user, get_current_user_stream  # noqa: E402
from app.models.asset_blob_models import AssetBlob, KnowledgeEvidencePromotion  # noqa: E402
from app.models.attachment_models import Attachment  # noqa: E402
from app.models.base import Base, PermissionLevel  # noqa: E402
from app.models.core import (  # noqa: E402
    Project,
    ProjectStatus,
    ProjectType,
    ProjectUser,
    ProjectUserRole,
    User,
    UserRole,
)
from app.models.evidence_governance_models import AttachmentVersion  # noqa: E402
from app.models.knowledge_models import KnowledgeAccessLevel, KnowledgeDocument, KnowledgeFolder  # noqa: E402
from app.routers import attachments, knowledge_folders  # noqa: E402


_TABLES = [
    User.__table__, Project.__table__, ProjectUser.__table__,
    KnowledgeFolder.__table__, AssetBlob.__table__, KnowledgeDocument.__table__,
    Attachment.__table__, AttachmentVersion.__table__, KnowledgeEvidencePromotion.__table__,
]


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[dict]:
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(tmp_path / "attachments"))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(
            id=uuid.uuid4(), username="promoter", email="promoter@example.test",
            hashed_password="x", role=UserRole.auditor, is_active=True,
        )
        other = User(
            id=uuid.uuid4(), username="other", email="other@example.test",
            hashed_password="x", role=UserRole.auditor, is_active=True,
        )
        project = Project(
            id=uuid.uuid4(), name="【测试】知识晋升_2025", client_name="测试",
            audit_year=2025, project_type=ProjectType.annual,
            status=ProjectStatus.execution, created_by=user.id,
        )
        db.add_all((user, other, project))
        await db.flush()
        member = ProjectUser(
            project_id=project.id, user_id=user.id, role=ProjectUserRole.auditor,
            permission_level=PermissionLevel.edit,
        )
        folder = KnowledgeFolder(
            id=uuid.uuid4(), name="私有资料", access_level=KnowledgeAccessLevel.private,
            created_by=user.id,
        )
        document = KnowledgeDocument(
            id=uuid.uuid4(), folder_id=folder.id, name="审计政策.md", file_type="md",
            content_text="# 审计政策\n保留原始证据。", file_size=0,
            created_by=user.id, version=1,
        )
        foreign_folder = KnowledgeFolder(
            id=uuid.uuid4(), name="他人私有资料", access_level=KnowledgeAccessLevel.private,
            created_by=other.id,
        )
        foreign_document = KnowledgeDocument(
            id=uuid.uuid4(), folder_id=foreign_folder.id, name="秘密.txt", file_type="txt",
            content_text="不可读取", created_by=other.id, version=1,
        )
        db.add_all((member, folder, document, foreign_folder, foreign_document))
        await db.commit()

        app = FastAPI()
        app.include_router(knowledge_folders.router)
        app.include_router(attachments.router)

        async def _db():
            yield db

        async def _user():
            return user

        async def _visible(*_args, **_kwargs):
            return None

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_current_user_stream] = _user
        monkeypatch.setattr(attachments, "enforce_attachment_wp_visibility", _visible)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield {
                "db": db, "client": client, "user": user, "other": other,
                "project": project, "member": member, "document": document,
                "foreign_document": foreign_document, "tmp_path": tmp_path,
            }
    await engine.dispose()


async def _promote(world: dict, *, key: str = "promote-intent-1", doc_id: uuid.UUID | None = None):
    return await world["client"].post(
        f"/api/knowledge-library/projects/{world['project'].id}/evidence/from-document/{doc_id or world['document'].id}",
        json={"idempotency_key": key},
    )


@pytest.mark.asyncio
async def test_promote_creates_pinned_root_version_provenance_and_download(world: dict) -> None:
    response = await _promote(world)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["replayed"] is False and body["audit_year"] == 2025

    db: AsyncSession = world["db"]
    promotion = (await db.execute(sa.select(KnowledgeEvidencePromotion))).scalar_one()
    attachment = await db.get(Attachment, promotion.target_attachment_id)
    version = await db.get(AttachmentVersion, promotion.target_attachment_version_id)
    blob = await db.get(AssetBlob, promotion.source_blob_id)
    document = await db.get(KnowledgeDocument, world["document"].id)
    expected = world["document"].content_text.encode("utf-8")
    digest = hashlib.sha256(expected).hexdigest()

    assert attachment.current_version_id == version.id
    assert (attachment.project_id, attachment.audit_year, attachment.source_type) == (
        world["project"].id, 2025, "knowledge_document",
    )
    assert attachment.file_path == f"blob://{blob.id}"
    assert version.blob_id == blob.id and version.content_hash == digest
    assert version.version_no == 1 and version.availability == "available"
    assert promotion.source_document_id == document.id
    assert promotion.source_document_version == 1 and promotion.source_hash == digest
    assert document.blob_id == blob.id
    assert document.access_level is None and document.content_text == "# 审计政策\n保留原始证据。"

    download = await world["client"].get(f"/api/attachments/{attachment.id}/download")
    assert download.status_code == 200 and download.content == expected
    assert download.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_same_idempotency_key_replays_without_duplicate_targets(world: dict) -> None:
    first = await _promote(world)
    second = await _promote(world)
    assert first.status_code == second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["attachment_id"] == first.json()["attachment_id"]

    db: AsyncSession = world["db"]
    assert (await db.execute(sa.select(sa.func.count()).select_from(Attachment))).scalar_one() == 1
    assert (await db.execute(sa.select(sa.func.count()).select_from(AttachmentVersion))).scalar_one() == 1
    assert (await db.execute(sa.select(sa.func.count()).select_from(KnowledgeEvidencePromotion))).scalar_one() == 1


@pytest.mark.asyncio
async def test_same_key_cannot_be_reused_for_another_source(world: dict) -> None:
    assert (await _promote(world)).status_code == 200
    response = await _promote(world, doc_id=world["foreign_document"].id)
    # 源文档不可读先按统一知识 ACL 返回 404，不泄露幂等记录或文档存在性。
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_idempotency_key_conflict_for_second_readable_version(world: dict) -> None:
    assert (await _promote(world)).status_code == 200
    db: AsyncSession = world["db"]
    second = KnowledgeDocument(
        id=uuid.uuid4(), folder_id=world["document"].folder_id,
        name="第二份.txt", file_type="txt", content_text="第二份",
        created_by=world["user"].id, version=1,
    )
    db.add(second)
    await db.commit()

    response = await _promote(world, doc_id=second.id)
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "IDEMPOTENCY_KEY_REUSED"
    assert (await db.execute(sa.select(sa.func.count()).select_from(Attachment))).scalar_one() == 1


@pytest.mark.asyncio
async def test_source_acl_and_target_permission_fail_closed(world: dict) -> None:
    hidden = await _promote(world, key="hidden", doc_id=world["foreign_document"].id)
    assert hidden.status_code == 404

    world["member"].permission_level = PermissionLevel.readonly
    await world["db"].commit()
    denied = await _promote(world, key="readonly")
    assert denied.status_code == 403
    assert (await world["db"].execute(sa.select(sa.func.count()).select_from(Attachment))).scalar_one() == 0


@pytest.mark.asyncio
async def test_archived_or_missing_year_project_is_rejected_before_promotion(world: dict) -> None:
    world["project"].status = ProjectStatus.archived
    await world["db"].commit()
    archived = await _promote(world, key="archived")
    assert archived.status_code == 423

    world["project"].status = ProjectStatus.execution
    world["project"].audit_year = None
    world["project"].audit_period_start = None
    world["project"].audit_period_end = None
    world["project"].name = "【测试】无年度项目"
    await world["db"].commit()
    no_year = await _promote(world, key="no-year")
    assert no_year.status_code == 422
    assert "未设置审计年度" in str(no_year.json())
    assert (await world["db"].execute(sa.select(sa.func.count()).select_from(Attachment))).scalar_one() == 0


@pytest.mark.asyncio
async def test_tampered_source_blob_rejected_without_target_rows(world: dict) -> None:
    first = await _promote(world, key="first")
    assert first.status_code == 200
    db: AsyncSession = world["db"]
    document = await db.get(KnowledgeDocument, world["document"].id)
    blob = await db.get(AssetBlob, document.blob_id)
    Path(blob.storage_key).write_bytes(b"tampered")

    response = await _promote(world, key="second")
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "SOURCE_BYTES_UNAVAILABLE"
    assert (await db.execute(sa.select(sa.func.count()).select_from(Attachment))).scalar_one() == 1
