"""附件↔底稿关联收敛 — Wave 4：证据类型声明

spec: attachment-workpaper-linkage-convergence Task 5.1 / Property 6
"""

from __future__ import annotations

import uuid
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
from app.services.workpaper_evidence_requirements import (
    build_evidence_requirements,
    clear_evidence_requirements_cache,
    item_satisfies_type,
    matches_wp_code_prefix,
    resolve_requirements_for_wp_code,
)

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
            name="Wave4 证据声明",
            client_name="测试客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            created_by=user_id,
        )
    )
    await db_session.commit()
    return {"project_id": project_id, "user_id": user_id}


async def _new_attachment(
    svc: AttachmentService,
    project_id: uuid.UUID,
    name: str = "证据.pdf",
    attachment_type: str = "general",
) -> uuid.UUID:
    att = await svc.create_attachment(
        project_id,
        {
            "file_name": name,
            "file_path": f"/storage/{name}",
            "file_type": "pdf",
            "file_size": 100,
            "attachment_type": attachment_type,
        },
    )
    await svc.db.flush()
    return uuid.UUID(att["id"])


class TestPrefixMatch:
    def test_exact_and_hyphen(self):
        assert matches_wp_code_prefix("E1", "E1")
        assert matches_wp_code_prefix("E1-1", "E1")
        assert matches_wp_code_prefix("E1-10", "E1")
        assert matches_wp_code_prefix("E1A", "E1")

    def test_no_false_positive_e10(self):
        assert not matches_wp_code_prefix("E10", "E1")
        assert not matches_wp_code_prefix("E10-1", "E1")

    def test_longest_prefix_wins(self):
        # 配置里若同时有 E / E1，应取 E1（由 resolve 内 max(len) 保证）
        reqs = resolve_requirements_for_wp_code("E1-1")
        assert reqs is not None
        types = {r["type"] for r in reqs}
        assert "bank_statement" in types
        assert "confirmation" in types

    def test_unknown_wp_no_requirements(self):
        assert resolve_requirements_for_wp_code("Z99") == []
        assert resolve_requirements_for_wp_code(None) == []
        assert build_evidence_requirements("Z99", []) is None


class TestSatisfied:
    def test_missing_and_satisfied(self):
        reqs = build_evidence_requirements(
            "E1-1",
            [{"attachment_type": "bank_statement", "sources": ["associated"]}],
        )
        assert reqs is not None
        by_type = {r["type"]: r for r in reqs}
        assert by_type["bank_statement"]["satisfied"] is True
        assert by_type["confirmation"]["satisfied"] is False

    def test_confirmation_via_source(self):
        assert item_satisfies_type(
            {"attachment_type": "general", "sources": ["confirmation"]},
            "confirmation",
        )

    def test_d4_contract(self):
        reqs = build_evidence_requirements("D4", [])
        assert reqs is not None
        assert len(reqs) == 1
        assert reqs[0]["type"] == "contract"
        assert reqs[0]["satisfied"] is False


class TestGetWpAttachmentsEvidenceReq:
    @pytest.mark.asyncio
    async def test_attaches_when_wp_code_resolved(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(
            svc, seeded_db["project_id"], "对账单.pdf", attachment_type="bank_statement"
        )
        wp_id = uuid.uuid4()
        await svc.ensure_wp_link(att_id, wp_id)
        await db_session.commit()

        with patch.object(
            svc,
            "_resolve_wp_meta",
            new_callable=AsyncMock,
            return_value={"wp_code": "E1-3", "project_id": seeded_db["project_id"], "prefill_stale": False, "audit_year": None},
        ):
            result = await svc.get_wp_attachments(wp_id)

        assert "evidence_requirements" in result
        by_type = {r["type"]: r for r in result["evidence_requirements"]}
        assert by_type["bank_statement"]["satisfied"] is True
        assert by_type["confirmation"]["satisfied"] is False

    @pytest.mark.asyncio
    async def test_omits_when_no_declaration(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()
        await svc.ensure_wp_link(att_id, wp_id)
        await db_session.commit()

        with patch.object(
            svc,
            "_resolve_wp_meta",
            new_callable=AsyncMock,
            return_value={"wp_code": "Z99", "project_id": seeded_db["project_id"], "prefill_stale": False, "audit_year": None},
        ):
            result = await svc.get_wp_attachments(wp_id)

        assert "evidence_requirements" not in result

    @pytest.mark.asyncio
    async def test_fail_open_on_build_error(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()
        await svc.ensure_wp_link(att_id, wp_id)
        await db_session.commit()

        with (
            patch.object(
                svc,
                "_resolve_wp_meta",
                new_callable=AsyncMock,
                return_value={"wp_code": "E1", "project_id": seeded_db["project_id"], "prefill_stale": False, "audit_year": None},
            ),
            patch(
                "app.services.workpaper_evidence_requirements.build_evidence_requirements",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = await svc.get_wp_attachments(wp_id)

        assert len(result["items"]) == 1
        assert "evidence_requirements" not in result


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_evidence_requirements_cache()
    yield
    clear_evidence_requirements_cache()
