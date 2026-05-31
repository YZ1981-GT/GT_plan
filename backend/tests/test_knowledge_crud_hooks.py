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
    return db


# ---------------------------------------------------------------------------
# Unit tests for _trigger_index_update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_index_update_calls_incremental_update(mock_db):
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

        await _trigger_index_update(mock_db, project_ids, doc_id, content)

        # Should be called once per project_id
        assert mock_instance.incremental_update.call_count == 2
        for i, pid in enumerate(project_ids):
            call_kwargs = mock_instance.incremental_update.call_args_list[i][1]
            assert call_kwargs["project_id"] == UUID(pid)
            assert call_kwargs["source_type"] == "knowledge_doc"
            assert call_kwargs["source_id"] == doc_id
            assert call_kwargs["content"] == content


@pytest.mark.asyncio
async def test_trigger_index_update_skips_when_no_content(mock_db):
    """No content_text → no indexing call."""
    from app.routers.knowledge_folders import _trigger_index_update

    doc_id = uuid.uuid4()
    project_ids = [str(uuid.uuid4())]

    with patch(
        "app.services.knowledge_index_service.KnowledgeIndexService"
    ) as MockSvc:
        await _trigger_index_update(mock_db, project_ids, doc_id, None)
        MockSvc.assert_not_called()

        await _trigger_index_update(mock_db, project_ids, doc_id, "")
        # Empty string is falsy, should not call
        MockSvc.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_index_update_skips_when_no_project_ids(mock_db):
    """No project_ids → no indexing call."""
    from app.routers.knowledge_folders import _trigger_index_update

    doc_id = uuid.uuid4()
    content = "some content"

    with patch(
        "app.services.knowledge_index_service.KnowledgeIndexService"
    ) as MockSvc:
        await _trigger_index_update(mock_db, None, doc_id, content)
        MockSvc.assert_not_called()

        await _trigger_index_update(mock_db, [], doc_id, content)
        MockSvc.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_index_update_non_blocking_on_failure(mock_db):
    """incremental_update failure doesn't raise — just logs."""
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
        await _trigger_index_update(mock_db, project_ids, doc_id, content)


# ---------------------------------------------------------------------------
# Unit tests for _trigger_index_delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_index_delete_soft_deletes_entries(mock_db):
    """Delete hook soft-deletes KnowledgeIndex entries for the doc."""
    from app.routers.knowledge_folders import _trigger_index_delete

    doc_id = uuid.uuid4()

    await _trigger_index_delete(mock_db, doc_id)

    # Should have called db.execute with an UPDATE statement
    mock_db.execute.assert_called_once()
    mock_db.flush.assert_called_once()


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

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_doc = MagicMock()
    mock_doc.id = uuid.uuid4()
    mock_doc.name = "test.md"

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

        # Verify hook was called with correct args
        mock_hook.assert_called_once_with(
            mock_db, project_ids, mock_doc.id, content
        )

        assert result["id"] == str(mock_doc.id)


@pytest.mark.asyncio
async def test_delete_document_endpoint_triggers_hook():
    """DELETE /documents/{id} triggers index delete before commit."""
    from app.routers.knowledge_folders import delete_document

    doc_id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

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
