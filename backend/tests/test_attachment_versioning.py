"""AT-3 附件版本管理测试（spec proposal-remaining-18 task 5.3）

验证：
1. 同 (project_id, reference_id, reference_type, file_name) 第二次上传 → version=2 + previous_version_id 链
2. list_versions 返回完整版本链（按 version 升序）
3. rollback_to_version 创建新 version=N+1，previous_version_id 指向当前最新
4. 回滚后旧版本仍存在（不真删）
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.services.attachment_service import AttachmentService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        tables = [
            User.__table__,
            Project.__table__,
            Attachment.__table__,
            AttachmentWorkingPaper.__table__,
        ]
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=tables))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project = Project(
        id=project_id,
        name="AT-3 版本测试",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=user_id,
    )
    db_session.add(project)
    await db_session.commit()
    return {"project_id": project_id, "user_id": user_id}


class TestAttachmentVersioning:
    """同名附件自动建版本链"""

    @pytest.mark.asyncio
    async def test_first_upload_version_is_one(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        result = await svc.create_attachment(
            seeded_db["project_id"],
            {
                "file_name": "合同.pdf",
                "file_path": "/storage/合同_v1.pdf",
                "file_type": "pdf",
                "file_size": 1024,
            },
        )
        assert result["version"] == 1
        assert result["previous_version_id"] is None

    @pytest.mark.asyncio
    async def test_same_name_creates_new_version(self, db_session, seeded_db):
        """连续上传同名 + 同 reference 文件 → version=1, 2"""
        svc = AttachmentService(db_session)
        ref_id = uuid.uuid4()

        v1 = await svc.create_attachment(
            seeded_db["project_id"],
            {
                "file_name": "合同.pdf",
                "file_path": "/storage/合同_v1.pdf",
                "file_type": "pdf",
                "file_size": 1024,
                "reference_id": ref_id,
                "reference_type": "contract",
            },
        )
        v2 = await svc.create_attachment(
            seeded_db["project_id"],
            {
                "file_name": "合同.pdf",
                "file_path": "/storage/合同_v2.pdf",
                "file_type": "pdf",
                "file_size": 2048,
                "reference_id": ref_id,
                "reference_type": "contract",
            },
        )
        assert v1["version"] == 1
        assert v1["previous_version_id"] is None
        assert v2["version"] == 2
        assert v2["previous_version_id"] == v1["id"]

    @pytest.mark.asyncio
    async def test_three_versions_chain(self, db_session, seeded_db):
        """连上 3 次 → version=1,2,3，链条正确"""
        svc = AttachmentService(db_session)
        results = []
        for i in range(3):
            r = await svc.create_attachment(
                seeded_db["project_id"],
                {
                    "file_name": "测试.docx",
                    "file_path": f"/storage/测试_{i}.docx",
                    "file_type": "docx",
                    "file_size": 100 + i,
                },
            )
            results.append(r)
        assert [r["version"] for r in results] == [1, 2, 3]
        assert results[0]["previous_version_id"] is None
        assert results[1]["previous_version_id"] == results[0]["id"]
        assert results[2]["previous_version_id"] == results[1]["id"]

    @pytest.mark.asyncio
    async def test_different_reference_starts_new_chain(self, db_session, seeded_db):
        """不同 reference_id 同名 → 独立链，都从 version=1 开始"""
        svc = AttachmentService(db_session)
        ref_a = uuid.uuid4()
        ref_b = uuid.uuid4()

        a = await svc.create_attachment(
            seeded_db["project_id"],
            {
                "file_name": "evidence.pdf",
                "file_path": "/a.pdf",
                "file_type": "pdf",
                "file_size": 100,
                "reference_id": ref_a,
                "reference_type": "wp",
            },
        )
        b = await svc.create_attachment(
            seeded_db["project_id"],
            {
                "file_name": "evidence.pdf",
                "file_path": "/b.pdf",
                "file_type": "pdf",
                "file_size": 200,
                "reference_id": ref_b,
                "reference_type": "wp",
            },
        )
        assert a["version"] == 1 and b["version"] == 1
        assert a["previous_version_id"] is None
        assert b["previous_version_id"] is None

    @pytest.mark.asyncio
    async def test_list_versions_returns_chain(self, db_session, seeded_db):
        """list_versions 返回完整链，按 version 升序"""
        svc = AttachmentService(db_session)
        v1 = await svc.create_attachment(
            seeded_db["project_id"],
            {"file_name": "x.pdf", "file_path": "/a.pdf", "file_type": "pdf", "file_size": 1},
        )
        v2 = await svc.create_attachment(
            seeded_db["project_id"],
            {"file_name": "x.pdf", "file_path": "/b.pdf", "file_type": "pdf", "file_size": 2},
        )

        versions = await svc.list_versions(uuid.UUID(v1["id"]))
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2
        assert versions[0]["id"] == v1["id"]
        assert versions[1]["id"] == v2["id"]

        # 从 v2 入口看也是同样的链
        versions2 = await svc.list_versions(uuid.UUID(v2["id"]))
        assert [v["version"] for v in versions2] == [1, 2]

    @pytest.mark.asyncio
    async def test_list_versions_unknown_returns_empty(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        result = await svc.list_versions(uuid.uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_rollback_creates_new_version(self, db_session, seeded_db):
        """回滚到 v1 → 创建 v3，previous_version_id 指向 v2，旧版本不删"""
        svc = AttachmentService(db_session)
        v1 = await svc.create_attachment(
            seeded_db["project_id"],
            {
                "file_name": "doc.pdf",
                "file_path": "/v1.pdf",
                "file_type": "pdf",
                "file_size": 100,
                "ocr_text": "原始内容",
            },
        )
        v2 = await svc.create_attachment(
            seeded_db["project_id"],
            {
                "file_name": "doc.pdf",
                "file_path": "/v2.pdf",
                "file_type": "pdf",
                "file_size": 200,
                "ocr_text": "新版内容",
            },
        )

        # 回滚 v2 → 取 v1 重建为 v3
        v3 = await svc.rollback_to_version(
            attachment_id=uuid.UUID(v2["id"]),
            version_id=uuid.UUID(v1["id"]),
            created_by=seeded_db["user_id"],
        )

        assert v3["version"] == 3
        assert v3["previous_version_id"] == v2["id"]
        # 复制了 v1 的内容
        assert v3["file_path"] == "/v1.pdf"
        assert v3["file_size"] == 100

        # 旧版本仍在
        all_versions = await svc.list_versions(uuid.UUID(v1["id"]))
        assert len(all_versions) == 3
        assert [v["version"] for v in all_versions] == [1, 2, 3]
        # 旧 v1/v2 仍未被删除
        v1_after = await svc.get_attachment(uuid.UUID(v1["id"]))
        v2_after = await svc.get_attachment(uuid.UUID(v2["id"]))
        assert v1_after is not None and v1_after["is_deleted"] is False
        assert v2_after is not None and v2_after["is_deleted"] is False

    @pytest.mark.asyncio
    async def test_rollback_unknown_version_raises(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        v1 = await svc.create_attachment(
            seeded_db["project_id"],
            {"file_name": "x.pdf", "file_path": "/a.pdf", "file_type": "pdf", "file_size": 1},
        )
        with pytest.raises(ValueError):
            await svc.rollback_to_version(
                attachment_id=uuid.UUID(v1["id"]),
                version_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_rollback_cross_chain_rejected(self, db_session, seeded_db):
        """回滚目标必须与 attachment_id 同链，不允许跨链"""
        svc = AttachmentService(db_session)
        a = await svc.create_attachment(
            seeded_db["project_id"],
            {"file_name": "a.pdf", "file_path": "/a", "file_type": "pdf", "file_size": 1},
        )
        b = await svc.create_attachment(
            seeded_db["project_id"],
            {"file_name": "b.pdf", "file_path": "/b", "file_type": "pdf", "file_size": 1},
        )
        with pytest.raises(ValueError):
            await svc.rollback_to_version(
                attachment_id=uuid.UUID(a["id"]),
                version_id=uuid.UUID(b["id"]),
            )
