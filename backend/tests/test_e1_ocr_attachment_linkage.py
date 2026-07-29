"""E1 专用 OCR — 临时 id 收敛到真实附件表。

验证：
- 预创建 OCR 附件时会写入 attachments + attachment_working_paper
- E1 statement OCR 返回的 attachment_id 可在附件表中查到，并带 working_paper 关联
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.datastructures import UploadFile

from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import WorkingPaper, WpFileStatus, WpIndex, WpSourceType, WpStatus
from app.routers.wp_render_strategies._e1_statement_ocr import e1_statement_ocr
from app.services.attachment_ocr_writeback import provision_wp_linked_attachment

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_TABLES = [
    User.__table__,
    Project.__table__,
    WpIndex.__table__,
    WorkingPaper.__table__,
    Attachment.__table__,
    AttachmentWorkingPaper.__table__,
]


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=_TABLES))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    user = User(
        id=user_id,
        username="e1_admin",
        email="e1@test.local",
        hashed_password="x",
        role=UserRole.admin,
        is_active=True,
    )
    project = Project(
        id=project_id,
        name="E1 OCR",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=user_id,
        audit_year=2025,
    )
    idx = WpIndex(
        project_id=project_id,
        wp_code="E1-31",
        wp_name="银行流水双向核对",
        status=WpStatus.in_progress,
    )
    db_session.add_all([user, project, idx])
    await db_session.flush()
    wp = WorkingPaper(
        project_id=project_id,
        wp_index_id=idx.id,
        file_path=f"{project_id}/E1-31.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        file_version=1,
        created_by=user_id,
    )
    db_session.add(wp)
    await db_session.commit()
    return {"user": user, "project_id": project_id, "wp": wp}


class TestProvisionWpLinkedAttachment:
    @pytest.mark.asyncio
    async def test_creates_real_attachment_and_link(self, db_session, seeded_db):
        att_id_str, att_id = await provision_wp_linked_attachment(
            db_session,
            wp_id=seeded_db["wp"].id,
            file_name="statement.pdf",
            content=b"fake-pdf",
            attachment_type="bank_statement",
            created_by=seeded_db["user"].id,
        )
        assert att_id is not None
        assert att_id_str == str(att_id)

        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.project_id == seeded_db["project_id"]
        assert att.reference_type == "working_paper"
        assert att.reference_id == seeded_db["wp"].id
        assert att.attachment_type == "bank_statement"

        cnt = (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(AttachmentWorkingPaper)
                .where(
                    AttachmentWorkingPaper.attachment_id == att_id,
                    AttachmentWorkingPaper.wp_id == seeded_db["wp"].id,
                )
            )
        ).scalar()
        assert int(cnt or 0) == 1


class TestE1StatementOcrAttachmentId:
    @pytest.mark.asyncio
    async def test_statement_ocr_returns_real_attachment_id(self, db_session, seeded_db):
        upload = UploadFile(filename="bank.pdf", file=io.BytesIO(b"%PDF-1.4 fake"))

        with patch(
            "app.routers.wp_render_strategies._e1_statement_ocr.UnifiedOCRService.recognize",
            AsyncMock(return_value={"text": "中国银行 账号 123 收入 100"}),
        ), patch(
            "app.routers.wp_render_strategies._e1_statement_ocr.chat_completion",
            AsyncMock(
                return_value='{"bank":"中国银行","accountNo":"123","periodStart":"2025-01-01","periodEnd":"2025-01-31","lines":[{"date":"2025-01-02","summary":"收款","counterparty":"甲公司","amount":100,"direction":"收入"}]}'
            ),
        ):
            resp = await e1_statement_ocr(
                wp_id=str(seeded_db["wp"].id),
                file=upload,
                attachment_id=None,
                force_reocr=False,
                db=db_session,
                _user=seeded_db["user"],
            )

        att_id = uuid.UUID(resp.attachment_id)
        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one_or_none()
        assert att is not None
        assert att.reference_id == seeded_db["wp"].id
        assert att.reference_type == "working_paper"
        assert att.ocr_text
        assert isinstance(att.ocr_fields_cache, dict)
        assert resp.written_back is True
        assert resp.line_count == 1
