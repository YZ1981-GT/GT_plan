"""附件↔底稿关联收敛 — Wave 1：双写 + 反查去重 + 回填脚本

spec: attachment-workpaper-linkage-convergence Tasks 2.1 / 2.2 / 2.3

Property 覆盖：
  - P1 双写幂等（linkAttachment → 权威链表一行）
  - P2 反查去重（链表 ∪ reference 同附件一行）
  - P3 reference 关联可见
  - P4 来源标注（associated / referenced）
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.services.attachment_service import AttachmentService
from app.services.process_record_service import AttachmentLinkService

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
            name="Wave1 关联收敛",
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
    assert isinstance(result, dict) and "items" in result
    return result["items"]


class TestWave1DualWrite:
    """Task 2.1：linkAttachment 双写权威真源。"""

    @pytest.mark.asyncio
    async def test_link_writes_authority_link_and_visible(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        ok = await AttachmentLinkService().link_attachment_to_workpaper(db_session, att_id, wp_id)
        assert ok is True
        await db_session.commit()

        # reference 仍写
        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.reference_type == "working_paper"
        assert att.reference_id == wp_id

        # 权威链表有行
        cnt = (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(AttachmentWorkingPaper)
                .where(
                    AttachmentWorkingPaper.attachment_id == att_id,
                    AttachmentWorkingPaper.wp_id == wp_id,
                )
            )
        ).scalar()
        assert cnt == 1

        # 反查可见，主 source=associated，sources 含两边
        items = _items(await svc.get_wp_attachments(wp_id))
        assert len(items) == 1
        assert items[0]["id"] == str(att_id)
        assert items[0]["source"] == "associated"
        assert "associated" in items[0]["sources"]
        assert "referenced" in items[0]["sources"]
        assert items[0]["association_type"] == "evidence"

    @pytest.mark.asyncio
    async def test_link_dual_write_idempotent(self, db_session, seeded_db):
        """连续两次 linkAttachment → 权威链表仍一行（P1）。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        await AttachmentLinkService().link_attachment_to_workpaper(db_session, att_id, wp_id)
        await AttachmentLinkService().link_attachment_to_workpaper(db_session, att_id, wp_id)
        await db_session.commit()

        cnt = (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(AttachmentWorkingPaper)
                .where(
                    AttachmentWorkingPaper.attachment_id == att_id,
                    AttachmentWorkingPaper.wp_id == wp_id,
                )
            )
        ).scalar()
        assert cnt == 1

    @pytest.mark.asyncio
    async def test_link_fail_open_when_ensure_wp_link_raises(self, db_session, seeded_db):
        """权威写入失败不阻断 reference UPDATE（Req1.5）。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        with patch.object(
            AttachmentService,
            "ensure_wp_link",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            ok = await AttachmentLinkService().link_attachment_to_workpaper(
                db_session, att_id, wp_id
            )
        assert ok is True
        await db_session.commit()

        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.reference_type == "working_paper"
        assert att.reference_id == wp_id

        # 无链行，但反查仍可通过 reference 看见（Task 2.2）
        link_cnt = (
            await db_session.execute(
                sa.select(sa.func.count()).select_from(AttachmentWorkingPaper)
            )
        ).scalar()
        assert link_cnt == 0
        items = _items(await svc.get_wp_attachments(wp_id))
        assert len(items) == 1
        assert items[0]["source"] == "referenced"
        assert items[0]["association_type"] is None


class TestWave1UnifiedLookup:
    """Task 2.2：反查统一去重 + 来源标注 + envelope。"""

    @pytest.mark.asyncio
    async def test_reference_only_visible_with_source(self, db_session, seeded_db):
        """仅 reference、无链行 → 反查可见 source=referenced（P3/P4）。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        await db_session.execute(
            sa.update(Attachment)
            .where(Attachment.id == att_id)
            .values(reference_type="working_paper", reference_id=wp_id)
        )
        await db_session.commit()

        items = _items(await svc.get_wp_attachments(wp_id))
        assert len(items) == 1
        assert items[0]["id"] == str(att_id)
        assert items[0]["source"] == "referenced"
        assert items[0]["sources"] == ["referenced"]
        assert items[0]["association_type"] is None

    @pytest.mark.asyncio
    async def test_associate_and_reference_deduped(self, db_session, seeded_db):
        """同附件既有链行又有 reference → 反查一行，sources 合并（P2）。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        await svc.ensure_wp_link(att_id, wp_id, association_type="support")
        await db_session.execute(
            sa.update(Attachment)
            .where(Attachment.id == att_id)
            .values(reference_type="working_paper", reference_id=wp_id)
        )
        await db_session.commit()

        items = _items(await svc.get_wp_attachments(wp_id))
        assert len(items) == 1
        assert items[0]["source"] == "associated"
        assert items[0]["sources"] == ["associated", "referenced"]
        assert items[0]["association_type"] == "support"

    @pytest.mark.asyncio
    async def test_envelope_shape_and_existing_fields(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"], "银行对账单.pdf")
        wp_id = uuid.uuid4()
        await svc.associate_with_wp(att_id, wp_id)
        await db_session.commit()

        result = await svc.get_wp_attachments(wp_id)
        assert "items" in result
        row = result["items"][0]
        for key in ("id", "file_name", "file_type", "file_size", "created_at", "source", "sources"):
            assert key in row
        assert row["file_name"] == "银行对账单.pdf"
        assert row["association_type"] == "evidence"
        # 无 wp_index 时不附加 evidence_requirements（fail-open / 无声明）
        assert "evidence_requirements" not in result


class TestWave1BackfillScript:
    """Task 2.3：存量 reference 回填脚本（幂等 / 回滚）。"""

    @pytest.mark.asyncio
    async def test_backfill_apply_idempotent_and_rollback(self, db_session, seeded_db):
        from scripts.backfill_attachment_wp_reference_links import (
            run_apply,
            run_dry,
            run_rollback,
        )

        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()
        await db_session.execute(
            sa.update(Attachment)
            .where(Attachment.id == att_id)
            .values(reference_type="working_paper", reference_id=wp_id)
        )
        await db_session.commit()

        dry = await run_dry(db_session)
        assert dry["would_insert"] == 1

        first = await run_apply(db_session)
        assert first["inserted"] == 1
        second = await run_apply(db_session)
        assert second["inserted"] == 0
        assert second["skipped"] >= 1

        cnt = (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(AttachmentWorkingPaper)
                .where(
                    AttachmentWorkingPaper.attachment_id == att_id,
                    AttachmentWorkingPaper.wp_id == wp_id,
                )
            )
        ).scalar()
        assert cnt == 1

        rb = await run_rollback(db_session)
        assert rb["deleted"] >= 1
        cnt2 = (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(AttachmentWorkingPaper)
                .where(
                    AttachmentWorkingPaper.attachment_id == att_id,
                    AttachmentWorkingPaper.wp_id == wp_id,
                )
            )
        ).scalar()
        assert cnt2 == 0
