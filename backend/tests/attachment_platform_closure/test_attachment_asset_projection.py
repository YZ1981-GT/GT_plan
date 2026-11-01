"""普通附件新写的稳定根、不可变版本、精确 alias 与阶段降级。"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.config import settings  # noqa: E402
from app.models.asset_blob_models import AssetBlob  # noqa: E402
from app.models.attachment_models import Attachment  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole  # noqa: E402
from app.models.evidence_governance_models import AttachmentVersion, LegacyAttachmentAlias  # noqa: E402
from app.services.asset_blob_service import AssetBlobService  # noqa: E402
from app.services.attachment_service import AttachmentService  # noqa: E402


_TABLES = [
    User.__table__, Project.__table__, AssetBlob.__table__, Attachment.__table__,
    AttachmentVersion.__table__, LegacyAttachmentAlias.__table__,
]


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[dict]:
    monkeypatch.setenv("ATTACHMENT_ASSET_PHASE", "M2")
    root = tmp_path / "attachments"
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(root))
    monkeypatch.setattr(settings, "ATTACHMENT_PRIMARY_STORAGE", "local")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(
            id=uuid.uuid4(), username="asset-writer", email="asset@example.test",
            hashed_password="x", role=UserRole.auditor, is_active=True,
        )
        project = Project(
            id=uuid.uuid4(), name="【测试】附件资产_2025", client_name="测试",
            audit_year=2025, status=ProjectStatus.execution,
            project_type=ProjectType.annual, created_by=user.id,
        )
        db.add_all((user, project))
        await db.commit()
        yield {"db": db, "user": user, "project": project, "root": root}
    await engine.dispose()


@pytest.mark.asyncio
async def test_two_legacy_upload_ids_share_stable_root_but_keep_exact_bytes(world: dict) -> None:
    db: AsyncSession = world["db"]
    service = AttachmentService(db, primary_storage="local", local_storage_root=str(world["root"]))
    first_bytes = b"%PDF-1.4\nfirst-version"
    second_bytes = b"%PDF-1.4\nsecond-version"

    first = await service.upload_attachment_file(
        world["project"].id, "合同.pdf", first_bytes,
        metadata={"attachment_type": "contract"}, created_by=world["user"].id,
    )
    second = await service.upload_attachment_file(
        world["project"].id, "合同.pdf", second_bytes,
        metadata={"attachment_type": "contract"}, created_by=world["user"].id,
    )
    await db.commit()

    first_id, second_id = uuid.UUID(first["id"]), uuid.UUID(second["id"])
    assert first_id != second_id
    aliases = list((await db.execute(
        sa.select(LegacyAttachmentAlias).order_by(LegacyAttachmentAlias.created_at)
    )).scalars())
    assert len(aliases) == 2
    by_old = {row.old_attachment_id: row for row in aliases}
    assert by_old[first_id].attachment_id == first_id
    assert by_old[first_id].resolution_kind == "root"
    assert by_old[second_id].attachment_id == first_id
    assert by_old[second_id].resolution_kind == "current_version"

    versions = list((await db.execute(
        sa.select(AttachmentVersion)
        .where(AttachmentVersion.attachment_id == first_id)
        .order_by(AttachmentVersion.version_no)
    )).scalars())
    assert [row.version_no for row in versions] == [1, 2]
    assert versions[1].previous_version_id == versions[0].id
    root = await db.get(Attachment, first_id)
    assert root.current_version_id == versions[1].id

    reader = AssetBlobService(db)
    first_blob = await reader.read_current_attachment_blob(first_id, project_id=world["project"].id)
    second_blob = await reader.read_current_attachment_blob(second_id, project_id=world["project"].id)
    assert first_blob is not None and first_blob.content == first_bytes
    assert second_blob is not None and second_blob.content == second_bytes


@pytest.mark.asyncio
async def test_m1_schema_absence_keeps_legacy_upload_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATTACHMENT_ASSET_PHASE", "M1")
    root = tmp_path / "attachments"
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(root))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[User.__table__, Project.__table__, Attachment.__table__],
        ))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(
            id=uuid.uuid4(), username="shadow", email="shadow@example.test",
            hashed_password="x", role=UserRole.auditor, is_active=True,
        )
        project = Project(
            id=uuid.uuid4(), name="【测试】shadow", client_name="测试", audit_year=2025,
            status=ProjectStatus.execution, project_type=ProjectType.annual,
        )
        db.add_all((user, project))
        await db.commit()
        result = await AttachmentService(
            db, primary_storage="local", local_storage_root=str(root),
        ).upload_attachment_file(
            project.id, "证据.pdf", b"%PDF-shadow",
            metadata={"attachment_type": "evidence"}, created_by=user.id,
        )
        await db.commit()
        assert await db.get(Attachment, uuid.UUID(result["id"])) is not None
        assert len(list(root.rglob("*.pdf"))) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_m2_projection_failure_removes_new_local_object(
    world: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.attachment_asset_projection import AttachmentAssetProjectionService

    async def _fail(*_args, **_kwargs):
        raise RuntimeError("projection failed")

    monkeypatch.setattr(AttachmentAssetProjectionService, "project_if_enabled", _fail)
    service = AttachmentService(
        world["db"], primary_storage="local", local_storage_root=str(world["root"]),
    )
    with pytest.raises(RuntimeError, match="projection failed"):
        await service.upload_attachment_file(
            world["project"].id, "失败.pdf", b"%PDF-failure",
            metadata={"attachment_type": "evidence"}, created_by=world["user"].id,
        )
    await world["db"].rollback()

    assert list(world["root"].rglob("*.pdf")) == []
    assert (await world["db"].execute(sa.select(sa.func.count()).select_from(Attachment))).scalar_one() == 0


def test_phase_parser_rejects_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.attachment_asset_projection import attachment_asset_phase

    monkeypatch.setenv("ATTACHMENT_ASSET_PHASE", "M9")
    with pytest.raises(RuntimeError, match="ATTACHMENT_ASSET_PHASE 非法"):
        attachment_asset_phase()
