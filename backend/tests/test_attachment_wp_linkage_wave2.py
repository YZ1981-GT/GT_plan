"""附件↔底稿关联收敛 — Wave 2：函证只读纳入反查

spec: attachment-workpaper-linkage-convergence Task 3.1

Property：函证附件 source=confirmation；与链表去重合并；查询异常 fail-open。
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base
from app.models.confirmation_models import Confirmation, ConfirmationAttachmentLink
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.services.attachment_service import AttachmentService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_CORE_TABLES = [
    User.__table__,
    Project.__table__,
    Attachment.__table__,
    AttachmentWorkingPaper.__table__,
    Confirmation.__table__,
    ConfirmationAttachmentLink.__table__,
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
            name="Wave2 函证纳入",
            client_name="测试客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            created_by=user_id,
        )
    )
    await db_session.commit()
    return {"project_id": project_id, "user_id": user_id}


async def _new_attachment(svc: AttachmentService, project_id: uuid.UUID, name: str = "回函.pdf") -> uuid.UUID:
    att = await svc.create_attachment(
        project_id,
        {"file_name": name, "file_path": f"/storage/{name}", "file_type": "pdf", "file_size": 100},
    )
    await svc.db.flush()
    return uuid.UUID(att["id"])


def _items(result) -> list[dict]:
    assert isinstance(result, dict) and "items" in result
    return result["items"]


class TestWave2ConfirmationReadonly:
    @pytest.mark.asyncio
    async def test_confirmation_attachment_visible(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()
        conf_id = uuid.uuid4()

        db_session.add(
            Confirmation(
                id=conf_id,
                project_id=seeded_db["project_id"],
                confirm_type="bank",
                counterparty="某某银行",
                status="returned",
                wp_id=wp_id,
            )
        )
        db_session.add(
            ConfirmationAttachmentLink(
                id=uuid.uuid4(),
                confirmation_id=conf_id,
                attachment_id=att_id,
                role="inbound",
                match_status="manual",
            )
        )
        await db_session.commit()

        items = _items(await svc.get_wp_attachments(wp_id))
        assert len(items) == 1
        assert items[0]["id"] == str(att_id)
        assert items[0]["source"] == "confirmation"
        assert items[0]["sources"] == ["confirmation"]
        assert items[0]["association_type"] is None

    @pytest.mark.asyncio
    async def test_confirmation_merged_with_associated(self, db_session, seeded_db):
        """同附件既有权威链又有函证 → 一行，sources 合并，主 source=associated。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()
        conf_id = uuid.uuid4()

        await svc.ensure_wp_link(att_id, wp_id, association_type="evidence")
        db_session.add(
            Confirmation(
                id=conf_id,
                project_id=seeded_db["project_id"],
                confirm_type="bank",
                counterparty="某某银行",
                status="returned",
                wp_id=wp_id,
            )
        )
        db_session.add(
            ConfirmationAttachmentLink(
                id=uuid.uuid4(),
                confirmation_id=conf_id,
                attachment_id=att_id,
                role="inbound",
                match_status="manual",
            )
        )
        await db_session.commit()

        items = _items(await svc.get_wp_attachments(wp_id))
        assert len(items) == 1
        assert items[0]["source"] == "associated"
        assert items[0]["sources"] == ["associated", "confirmation"]

    @pytest.mark.asyncio
    async def test_confirmation_lookup_fail_open(self, db_session, seeded_db):
        """函证查询异常时仍返回权威链表（Property 8）。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"], "证据.pdf")
        wp_id = uuid.uuid4()
        await svc.ensure_wp_link(att_id, wp_id)
        await db_session.commit()

        real_execute = db_session.execute

        async def selective_execute(*args, **kwargs):
            stmt = args[0] if args else None
            sql = str(stmt) if stmt is not None else ""
            if "confirmation_attachment_link" in sql.lower() or (
                "confirmations" in sql.lower() and "attachment" in sql.lower()
            ):
                raise RuntimeError("conf boom")
            return await real_execute(*args, **kwargs)

        with patch.object(db_session, "execute", side_effect=selective_execute):
            items = _items(await svc.get_wp_attachments(wp_id))

        assert len(items) == 1
        assert items[0]["id"] == str(att_id)
        assert items[0]["source"] == "associated"
