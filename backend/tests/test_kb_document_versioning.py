"""AT-3 KB 接入扩展：knowledge_documents 版本管理测试

验证：
1. 同 (folder_id, name) 第二次 create_document → version=2 + previous_version_id 链
2. 三次 create → version 1/2/3，previous_version_id 链正确
3. 不同 folder_id 同名 → 各自独立链都从 v1 开始
4. list_versions(doc_id) 返回 doc_id 所属链（按 version 升序）
5. list_versions 不存在的 doc_id → 返回 []
6. rollback_to_version：复制目标版本元数据 + version=N+1 + previous_version_id 指向当前最新
7. rollback 不存在的 version_id → ValueError
8. rollback 跨链（version_id 不属于 doc_id 所在链）→ ValueError

Validates: spec proposal-remaining-18 task 5.3 AT-3 KB 接入
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.models.base import Base
from app.models.knowledge_models import (  # noqa: F401
    KnowledgeDocument,
    KnowledgeFolder,
)
from app.services.knowledge_folder_service import (
    KnowledgeDocumentService,
    KnowledgeFolderService,
)

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def folder(db_session: AsyncSession) -> KnowledgeFolder:
    """创建一个测试文件夹"""
    fsvc = KnowledgeFolderService(db_session)
    f = await fsvc.create_folder(name="测试文件夹", access_level="public")
    await db_session.commit()
    return f


@pytest_asyncio.fixture
async def folder2(db_session: AsyncSession) -> KnowledgeFolder:
    fsvc = KnowledgeFolderService(db_session)
    f = await fsvc.create_folder(name="测试文件夹2", access_level="public")
    await db_session.commit()
    return f


# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_create_version_1(db_session, folder):
    svc = KnowledgeDocumentService(db_session)
    d = await svc.create_document(folder.id, name="审计指引.md", file_size=100)
    assert d.version == 1
    assert d.previous_version_id is None


@pytest.mark.asyncio
async def test_second_create_same_name_version_2(db_session, folder):
    svc = KnowledgeDocumentService(db_session)
    v1 = await svc.create_document(folder.id, name="审计指引.md", file_size=100)
    v2 = await svc.create_document(folder.id, name="审计指引.md", file_size=200)
    assert v1.version == 1 and v1.previous_version_id is None
    assert v2.version == 2
    assert v2.previous_version_id == v1.id


@pytest.mark.asyncio
async def test_three_versions_chain(db_session, folder):
    svc = KnowledgeDocumentService(db_session)
    docs = []
    for i in range(1, 4):
        d = await svc.create_document(folder.id, name="x.md", file_size=i * 10)
        docs.append(d)
    assert [d.version for d in docs] == [1, 2, 3]
    assert docs[0].previous_version_id is None
    assert docs[1].previous_version_id == docs[0].id
    assert docs[2].previous_version_id == docs[1].id


@pytest.mark.asyncio
async def test_different_folders_independent_chains(db_session, folder, folder2):
    svc = KnowledgeDocumentService(db_session)
    a = await svc.create_document(folder.id, name="同名.md", file_size=1)
    b = await svc.create_document(folder2.id, name="同名.md", file_size=2)
    assert a.version == 1 and b.version == 1
    assert a.previous_version_id is None
    assert b.previous_version_id is None


@pytest.mark.asyncio
async def test_list_versions_returns_chain(db_session, folder):
    svc = KnowledgeDocumentService(db_session)
    v1 = await svc.create_document(folder.id, name="x.md", file_size=10)
    v2 = await svc.create_document(folder.id, name="x.md", file_size=20)

    versions = await svc.list_versions(v1.id)
    assert len(versions) == 2
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["id"] == str(v1.id)
    assert versions[1]["id"] == str(v2.id)

    # 从 v2 入口看也是同样的链
    versions2 = await svc.list_versions(v2.id)
    assert [v["version"] for v in versions2] == [1, 2]


@pytest.mark.asyncio
async def test_list_versions_unknown_returns_empty(db_session, folder):
    svc = KnowledgeDocumentService(db_session)
    result = await svc.list_versions(uuid.uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_rollback_creates_new_version(db_session, folder):
    svc = KnowledgeDocumentService(db_session)
    v1 = await svc.create_document(
        folder.id, name="doc.md", file_size=100, content_text="原始"
    )
    v2 = await svc.create_document(
        folder.id, name="doc.md", file_size=200, content_text="新版"
    )

    v3 = await svc.rollback_to_version(doc_id=v2.id, version_id=v1.id)
    assert v3["version"] == 3
    assert v3["previous_version_id"] == str(v2.id)
    assert v3["file_size"] == 100  # 复制了 v1 的内容

    # 旧版本仍存在
    versions = await svc.list_versions(v1.id)
    assert [v["version"] for v in versions] == [1, 2, 3]


@pytest.mark.asyncio
async def test_rollback_unknown_version_raises(db_session, folder):
    svc = KnowledgeDocumentService(db_session)
    v1 = await svc.create_document(folder.id, name="x.md", file_size=10)
    with pytest.raises(ValueError):
        await svc.rollback_to_version(doc_id=v1.id, version_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_rollback_cross_chain_rejected(db_session, folder):
    svc = KnowledgeDocumentService(db_session)
    a = await svc.create_document(folder.id, name="a.md", file_size=1)
    b = await svc.create_document(folder.id, name="b.md", file_size=2)
    with pytest.raises(ValueError):
        await svc.rollback_to_version(doc_id=a.id, version_id=b.id)


@pytest.mark.asyncio
async def test_rollback_unknown_doc_raises(db_session, folder):
    svc = KnowledgeDocumentService(db_session)
    v1 = await svc.create_document(folder.id, name="x.md", file_size=10)
    with pytest.raises(ValueError):
        await svc.rollback_to_version(doc_id=uuid.uuid4(), version_id=v1.id)
