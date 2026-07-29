"""附件↔底稿关联收敛 — Wave 3：解除关联

spec: attachment-workpaper-linkage-convergence Task 4.1 / Property 5
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.services.attachment_service import AttachmentService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_CORE_TABLES = [
    User.__table__,
    Project.__table__,
    Attachment.__table__,
    AttachmentWorkingPaper.__table__,
]


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=_CORE_TABLES))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_CORE_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db_session.add(
        Project(
            id=project_id,
            name="Wave3 解除关联",
            client_name="测试客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            created_by=user_id,
        )
    )
    await db_session.commit()
    return {"project_id": project_id, "user_id": user_id}


async def _new_attachment(svc: AttachmentService, project_id: uuid.UUID, name: str = "证据.pdf") -> uuid.UUID:
    att = await svc.create_attachment(
        project_id,
        {"file_name": name, "file_path": f"/storage/{name}", "file_type": "pdf", "file_size": 100},
    )
    await svc.db.flush()
    return uuid.UUID(att["id"])


def _items(result) -> list[dict]:
    return result["items"]


class TestWave3Unlink:
    @pytest.mark.asyncio
    async def test_unlink_removes_link_and_reference(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        await svc.ensure_wp_link(att_id, wp_id, association_type="evidence")
        await db_session.execute(
            sa.update(Attachment)
            .where(Attachment.id == att_id)
            .values(reference_type="working_paper", reference_id=wp_id)
        )
        await db_session.commit()

        result = await svc.unlink_wp_attachment(wp_id, att_id)
        await db_session.commit()
        assert result["ok"] is True
        assert result["link_removed"] == 1
        assert result["reference_cleared"] is True

        items = _items(await svc.get_wp_attachments(wp_id))
        assert items == []

        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.reference_type is None
        assert att.reference_id is None
        # 附件本身仍在
        assert att.is_deleted is False

    @pytest.mark.asyncio
    async def test_unlink_idempotent(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()
        await svc.ensure_wp_link(att_id, wp_id)
        await db_session.commit()

        first = await svc.unlink_wp_attachment(wp_id, att_id)
        second = await svc.unlink_wp_attachment(wp_id, att_id)
        assert first["ok"] is True
        assert second["ok"] is True
        assert second["link_removed"] == 0
        assert second["reference_cleared"] is False

    @pytest.mark.asyncio
    async def test_unlink_does_not_clear_other_wp_reference(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_a = uuid.uuid4()
        wp_b = uuid.uuid4()
        await svc.ensure_wp_link(att_id, wp_a)
        await db_session.execute(
            sa.update(Attachment)
            .where(Attachment.id == att_id)
            .values(reference_type="working_paper", reference_id=wp_b)
        )
        await db_session.commit()

        result = await svc.unlink_wp_attachment(wp_a, att_id)
        assert result["link_removed"] == 1
        assert result["reference_cleared"] is False

        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.reference_id == wp_b


class TestWave3UnlinkAuth:
    """路由层权限：authorize_wp_edit → 403（用 mock 隔离，不启全量 FastAPI）。"""

    @pytest.mark.asyncio
    async def test_authorize_wp_edit_403_blocks_unlink_flow(self):
        from app.routers import attachments as att_router

        wp_id = uuid.uuid4()
        att_id = uuid.uuid4()
        user = AsyncMock()
        user.id = uuid.uuid4()
        db = AsyncMock()

        with (
            patch.object(att_router, "gate_wp", new_callable=AsyncMock) as gate,
            patch.object(
                att_router,
                "authorize_wp_edit",
                new_callable=AsyncMock,
                side_effect=HTTPException(status_code=403, detail="无底稿编辑权限"),
            ),
            patch.object(att_router, "_svc") as svc_factory,
        ):
            with pytest.raises(HTTPException) as ei:
                await att_router.unlink_wp_attachment(wp_id, att_id, db, user)
            assert ei.value.status_code == 403
            gate.assert_awaited_once()
            svc_factory.assert_not_called()
