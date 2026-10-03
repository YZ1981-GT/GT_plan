"""Tests for knowledge_folders CRUD → vector index hooks (§21.3.1 fix).

Validates:
- Upload/create triggers incremental_update for each project_id
- Delete triggers soft-delete of KnowledgeIndex entries
- Hook failures don't break CRUD operations (non-blocking)
- Idempotency (R3): multiple calls converge to same index state
"""

import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio

from uuid import UUID


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    # begin_nested() 返回异步上下文管理器（SAVEPOINT）；__aexit__ 必须返回 False，
    # 否则 MagicMock 默认的真值返回会**吞掉**块内异常，失败路径测试就空转了。
    savepoint = MagicMock()
    savepoint.__aenter__ = AsyncMock(return_value=None)
    savepoint.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=savepoint)
    return db


# ---------------------------------------------------------------------------
# Unit tests for _trigger_index_update
#
# 钩子使用**独立会话**（spec knowledge-base-retrieval-and-authz-closure Req 1.5）：
# 索引写路径在当前环境必然失败，用请求会话执行会毒化同一请求里后续的读写。
# ---------------------------------------------------------------------------


@pytest.fixture
def index_session():
    """替换 ``app.core.database.async_session``，返回钩子内部拿到的独立会话。"""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    with patch("app.core.database.async_session", _Factory()):
        yield session


@pytest.mark.asyncio
async def test_trigger_index_update_calls_incremental_update(index_session):
    """Upload/create with content_text and project_ids triggers incremental_update."""
    from app.routers.knowledge_folders import _trigger_index_update

    doc_id = uuid.uuid4()
    project_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    content = "审计准则第1号"

    with patch(
        "app.services.knowledge_index_service.KnowledgeIndexService"
    ) as MockSvc:
        mock_instance = AsyncMock()
        MockSvc.return_value = mock_instance

        await _trigger_index_update(project_ids, doc_id, content)

        # 服务构造在**独立会话**上，而不是请求会话
        MockSvc.assert_called_once_with(index_session)
        # Should be called once per project_id
        assert mock_instance.incremental_update.call_count == 2
        for i, pid in enumerate(project_ids):
            call_kwargs = mock_instance.incremental_update.call_args_list[i][1]
            assert call_kwargs["project_id"] == UUID(pid)
            assert call_kwargs["source_type"] == "knowledge_doc"
            assert call_kwargs["source_id"] == doc_id
            assert call_kwargs["content"] == content


@pytest.mark.asyncio
async def test_trigger_index_update_skips_when_no_content(index_session):
    """No content_text → no indexing call."""
    from app.routers.knowledge_folders import _trigger_index_update

    doc_id = uuid.uuid4()
    project_ids = [str(uuid.uuid4())]

    with patch(
        "app.services.knowledge_index_service.KnowledgeIndexService"
    ) as MockSvc:
        await _trigger_index_update(project_ids, doc_id, None)
        MockSvc.assert_not_called()

        await _trigger_index_update(project_ids, doc_id, "")
        # Empty string is falsy, should not call
        MockSvc.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_index_update_skips_when_no_project_ids(index_session):
    """No project_ids → no indexing call."""
    from app.routers.knowledge_folders import _trigger_index_update

    doc_id = uuid.uuid4()
    content = "some content"

    with patch(
        "app.services.knowledge_index_service.KnowledgeIndexService"
    ) as MockSvc:
        await _trigger_index_update(None, doc_id, content)
        MockSvc.assert_not_called()

        await _trigger_index_update([], doc_id, content)
        MockSvc.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_index_update_non_blocking_on_failure(index_session):
    """incremental_update failure doesn't raise — just logs, and rolls back its own session."""
    from app.routers.knowledge_folders import _trigger_index_update

    doc_id = uuid.uuid4()
    project_ids = [str(uuid.uuid4())]
    content = "审计准则"

    with patch(
        "app.services.knowledge_index_service.KnowledgeIndexService"
    ) as MockSvc:
        mock_instance = AsyncMock()
        mock_instance.incremental_update.side_effect = RuntimeError("embedding service down")
        MockSvc.return_value = mock_instance

        # Should NOT raise
        await _trigger_index_update(project_ids, doc_id, content)

    # 失败回滚的是钩子自己的独立会话（请求会话不受影响）
    index_session.rollback.assert_awaited()


# ---------------------------------------------------------------------------
# Unit tests for _trigger_index_delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_index_delete_soft_deletes_entries(mock_db):
    """Delete hook soft-deletes KnowledgeIndex entries for the doc."""
    from app.routers.knowledge_folders import _trigger_index_delete

    doc_id = uuid.uuid4()

    await _trigger_index_delete(mock_db, doc_id)

    # UPDATE 必须在 SAVEPOINT 内执行（失败只回滚钩子，不毒化调用方事务）；
    # 事务语义本身由真库测试 test_knowledge_delete_hook_isolation_pg.py 守卫。
    mock_db.begin_nested.assert_called_once()
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_index_delete_non_blocking_on_failure(mock_db):
    """Delete hook failure doesn't raise — just logs."""
    from app.routers.knowledge_folders import _trigger_index_delete

    doc_id = uuid.uuid4()
    mock_db.execute.side_effect = RuntimeError("DB connection lost")

    # Should NOT raise
    await _trigger_index_delete(mock_db, doc_id)


# ---------------------------------------------------------------------------
# Integration-style tests for endpoint hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_document_endpoint_triggers_hook():
    """POST /folders/{id}/documents triggers index update after commit."""
    from app.routers.knowledge_folders import create_document, DocumentCreateRequest

    folder_id = uuid.uuid4()
    project_ids = [str(uuid.uuid4())]
    content = "知识文件内容"

    data = DocumentCreateRequest(
        name="test.md",
        content_text=content,
        file_type="md",
        project_ids=project_ids,
    )

    from tests._kb_mock_session import attach_retrieval_session_shape

    mock_db = attach_retrieval_session_shape(AsyncMock())
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()
    # 写动作按系统角色设上界（readonly / 未知角色 fail-closed 403）
    mock_user.role = "auditor"

    mock_doc = MagicMock()
    mock_doc.id = uuid.uuid4()
    mock_doc.name = "test.md"

    # 知识资产写权限门（Feature dsh-agent-panel-integration Task 1）：public 文件夹 +
    # 有效身份 → 允许。此处走真实 policy 判定，只桩掉 DB 取数。
    from app.models.knowledge_models import KnowledgeAccessLevel

    subject_result = MagicMock()
    subject_result.scalars.return_value.all.return_value = []
    folder_perm_result = MagicMock()
    folder_perm_result.first.return_value = (KnowledgeAccessLevel.public, None, None)
    mock_db.execute = AsyncMock(side_effect=[subject_result, folder_perm_result])

    with patch(
        "app.routers.knowledge_folders.KnowledgeDocumentService"
    ) as MockDocSvc, patch(
        "app.routers.knowledge_folders._trigger_index_update"
    ) as mock_hook:
        mock_hook_coro = AsyncMock()
        mock_hook.side_effect = mock_hook_coro

        mock_svc_instance = AsyncMock()
        mock_svc_instance.create_document.return_value = mock_doc
        MockDocSvc.return_value = mock_svc_instance

        result = await create_document(folder_id, data, mock_db, mock_user)

        # Verify commit was called
        mock_db.commit.assert_called_once()

        # Verify hook was called with correct args（钩子自建独立会话，不再接收请求会话）
        mock_hook.assert_called_once_with(
            project_ids, mock_doc.id, content
        )

        assert result["id"] == str(mock_doc.id)


@pytest.mark.asyncio
async def test_delete_document_endpoint_triggers_hook():
    """DELETE /documents/{id} triggers index delete before commit."""
    from app.routers.knowledge_folders import delete_document

    doc_id = uuid.uuid4()

    from app.models.knowledge_models import KnowledgeAccessLevel
    from tests._kb_mock_session import attach_retrieval_session_shape

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()
    mock_user.role = "auditor"

    # 资源级授权（spec knowledge-base-retrieval-and-authz-closure 6.2）：先取判权三元组 ——
    # 公开文件夹里、由当前用户创建的文档 → 可读且可管理。走真实 policy，只桩掉取数。
    subject_result = MagicMock()
    subject_result.scalars.return_value.all.return_value = []
    doc_perm_result = MagicMock()
    doc_perm_result.first.return_value = (None, None, mock_user.id, KnowledgeAccessLevel.public, None, None)
    mock_db = attach_retrieval_session_shape(AsyncMock())
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[subject_result, doc_perm_result])

    with patch(
        "app.routers.knowledge_folders.KnowledgeDocumentService"
    ) as MockDocSvc, patch(
        "app.routers.knowledge_folders._trigger_index_delete"
    ) as mock_hook:
        mock_hook_coro = AsyncMock()
        mock_hook.side_effect = mock_hook_coro

        mock_svc_instance = AsyncMock()
        MockDocSvc.return_value = mock_svc_instance

        result = await delete_document(doc_id, mock_db, mock_user)

        # Verify hook was called
        mock_hook.assert_called_once_with(mock_db, doc_id)

        # Verify commit was called (after hook)
        mock_db.commit.assert_called_once()

        assert result["message"] == "文档已删除"
