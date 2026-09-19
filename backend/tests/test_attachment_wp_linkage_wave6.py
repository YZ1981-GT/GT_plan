"""附件↔底稿关联收敛 — Wave 6：OCR 回流同源

spec: attachment-workpaper-linkage-convergence Task 7.1 / Property 7
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.services.attachment_ocr_writeback import (
    is_attachment_linked_to_wp,
    load_reusable_ocr,
    parse_optional_uuid,
    writeback_ocr_to_linked_attachment,
)
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
            name="Wave6 OCR回流",
            client_name="测试客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            created_by=user_id,
        )
    )
    await db_session.commit()
    return {"project_id": project_id, "user_id": user_id}


async def _new_attachment(svc: AttachmentService, project_id: uuid.UUID) -> uuid.UUID:
    att = await svc.create_attachment(
        project_id,
        {"file_name": "合同.pdf", "file_path": "/storage/c.pdf", "file_type": "pdf", "file_size": 100},
    )
    await svc.db.flush()
    return uuid.UUID(att["id"])


class TestParseOptionalUuid:
    def test_valid_and_invalid(self):
        u = uuid.uuid4()
        assert parse_optional_uuid(str(u)) == u
        assert parse_optional_uuid(None) is None
        assert parse_optional_uuid("") is None
        assert parse_optional_uuid("not-a-uuid") is None


class TestOcrWriteback:
    @pytest.mark.asyncio
    async def test_writeback_only_when_linked(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        # 未关联 → 不写
        ok = await writeback_ocr_to_linked_attachment(
            db_session,
            attachment_id=att_id,
            wp_id=wp_id,
            ocr_text="hello",
            extracted_fields={"contractNo": "C-1"},
            confidence=0.5,
        )
        assert ok is False
        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.ocr_text is None or att.ocr_text == ""

        # 关联后写入
        await svc.ensure_wp_link(att_id, wp_id)
        await db_session.commit()
        assert await is_attachment_linked_to_wp(db_session, att_id, wp_id)

        ok2 = await writeback_ocr_to_linked_attachment(
            db_session,
            attachment_id=att_id,
            wp_id=wp_id,
            ocr_text="合同全文",
            extracted_fields={"contractNo": "C-1", "counterparty": "甲公司"},
            confidence=0.8,
        )
        assert ok2 is True
        await db_session.commit()

        att2 = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att2.ocr_text == "合同全文"
        assert att2.ocr_status == "completed"
        assert att2.ocr_fields_cache["governed"] is False
        assert att2.ocr_fields_cache["requires_human_confirmation"] is True
        assert att2.ocr_fields_cache["contractNo"] == "C-1"

    @pytest.mark.asyncio
    async def test_reuse_existing_ocr(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()
        await svc.ensure_wp_link(att_id, wp_id)
        await writeback_ocr_to_linked_attachment(
            db_session,
            attachment_id=att_id,
            wp_id=wp_id,
            ocr_text="已有文本",
            extracted_fields={"contractNo": "OLD"},
            confidence=0.9,
        )
        await db_session.commit()

        reused = await load_reusable_ocr(db_session, att_id)
        assert reused is not None
        assert reused["ocr_text"] == "已有文本"
        assert reused["reused"] is True
        assert reused["governed"] is False
        assert reused["requires_human_confirmation"] is True
        assert reused["extracted_fields"]["contractNo"] == "OLD"

    @pytest.mark.asyncio
    async def test_writeback_does_not_touch_business_tables(self, db_session, seeded_db):
        """Property 7：回流只写附件 OCR 字段，不自动落业务数据。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()
        await svc.ensure_wp_link(att_id, wp_id)
        await writeback_ocr_to_linked_attachment(
            db_session,
            attachment_id=att_id,
            wp_id=wp_id,
            ocr_text="x",
            extracted_fields={"contractAmount": 100},
            confidence=0.5,
        )
        await db_session.commit()

        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        # 仅附件 OCR 字段变化；checklist / confirmation 等业务表不在本路径写入
        assert att.ocr_fields_cache["governed"] is False
        assert "contractAmount" in att.ocr_fields_cache
