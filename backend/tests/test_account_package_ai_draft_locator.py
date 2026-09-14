"""
test_account_package_ai_draft_locator.py — AI 草稿定位测试

Spec: workpaper-account-package-d1-d2-pilot Task 7.4

验证:
- pending AI 草稿定位必须包含 account_package_id、wp_id、sheet_type、field_id
- 从 ai_content_log 读取，不创建新表

Requirements: 2.5, 3.4
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.account_package_conclusion_context_service import (
    AccountPackageConclusionContextService,
    ConclusionContext,
)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def project_id():
    return uuid.uuid4()


@pytest.fixture
def wp_id():
    return uuid.uuid4()


class TestAiDraftLocator:
    """验证 pending AI 草稿定位包含所有必需字段"""

    @pytest.mark.asyncio
    async def test_draft_locator_contains_required_fields(self, mock_db, project_id, wp_id):
        """每个 pending draft 必须包含 account_package_id, wp_id, sheet_type, field_id"""
        # Create a mock AiContentLog record
        mock_record = MagicMock()
        mock_record.id = uuid.uuid4()
        mock_record.wp_id = wp_id
        mock_record.target_cell = f"workpaper:{wp_id}:conclusion_narrative"
        mock_record.generated_content = "AI 生成的结论草稿内容"
        mock_record.model = "qwen3.5-27b"
        mock_record.confidence = Decimal("0.85")
        mock_record.generated_at = datetime.now(timezone.utc)
        mock_record.confirm_action = "pending"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_record]

        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AccountPackageConclusionContextService(mock_db)
        drafts = await service.get_pending_ai_drafts(
            project_id, "D2_accounts_receivable", wp_id=wp_id
        )

        assert len(drafts) == 1
        draft = drafts[0]

        # 核心断言：4 个必需定位字段
        assert "account_package_id" in draft, "缺少 account_package_id 字段"
        assert "wp_id" in draft, "缺少 wp_id 字段"
        assert "sheet_type" in draft, "缺少 sheet_type 字段"
        assert "field_id" in draft, "缺少 field_id 字段"

        # 验证具体值
        assert draft["account_package_id"] == "D2_accounts_receivable"
        assert draft["wp_id"] == str(wp_id)
        assert draft["sheet_type"] == "conclusion"
        assert draft["field_id"] == "conclusion_narrative"

    @pytest.mark.asyncio
    async def test_draft_locator_field_id_from_target_cell(self, mock_db, project_id, wp_id):
        """field_id 从 target_cell 第 3 段解析"""
        mock_record = MagicMock()
        mock_record.id = uuid.uuid4()
        mock_record.wp_id = wp_id
        mock_record.target_cell = f"workpaper:{wp_id}:opinion_paragraph"
        mock_record.generated_content = "审计意见段落"
        mock_record.model = "qwen3.5-27b"
        mock_record.confidence = Decimal("0.9")
        mock_record.generated_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_record]
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AccountPackageConclusionContextService(mock_db)
        drafts = await service.get_pending_ai_drafts(
            project_id, "D1_notes_receivable", wp_id=wp_id
        )

        assert drafts[0]["field_id"] == "opinion_paragraph"

    @pytest.mark.asyncio
    async def test_draft_locator_field_id_none_when_no_field(self, mock_db, project_id, wp_id):
        """target_cell 无第 3 段时 field_id 为 None"""
        mock_record = MagicMock()
        mock_record.id = uuid.uuid4()
        mock_record.wp_id = wp_id
        mock_record.target_cell = f"workpaper:{wp_id}"
        mock_record.generated_content = "内容"
        mock_record.model = "qwen3.5-27b"
        mock_record.confidence = None
        mock_record.generated_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_record]
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AccountPackageConclusionContextService(mock_db)
        drafts = await service.get_pending_ai_drafts(
            project_id, "D1_notes_receivable", wp_id=wp_id
        )

        assert drafts[0]["field_id"] is None

    @pytest.mark.asyncio
    async def test_has_pending_ai_draft(self, mock_db, project_id, wp_id):
        """has_pending_ai_draft 在有 pending 记录时返回 True"""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3

        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AccountPackageConclusionContextService(mock_db)
        result = await service.has_pending_ai_draft(
            project_id, "D2_accounts_receivable", wp_id=wp_id
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_no_pending_ai_draft(self, mock_db, project_id, wp_id):
        """has_pending_ai_draft 在无 pending 记录时返回 False"""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0

        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AccountPackageConclusionContextService(mock_db)
        result = await service.has_pending_ai_draft(
            project_id, "D2_accounts_receivable", wp_id=wp_id
        )

        assert result is False

    def test_reads_from_existing_ai_content_log_not_new_table(self):
        """验证服务从 AiContentLog（ai_content_log 表）读取，不创建新表"""
        import inspect
        source = inspect.getsource(AccountPackageConclusionContextService)

        # 应使用 AiContentLog
        assert "AiContentLog" in source, "应从现有 AiContentLog 读取"

        # 不应有 CREATE TABLE 或新模型定义
        assert "CREATE TABLE" not in source, "不应创建新表"
        assert "Base)" not in source, "不应定义新 ORM 模型"
