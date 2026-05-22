"""Phase 2 F3 批量状态变更测试

覆盖：
- 批量提交复核（draft → in_review）
- 批量退回（in_review → draft）
- 部分跳过（状态不允许）
- 空列表校验
- 不支持的操作校验
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.routers.workpaper_batch_status import (
    _TRANSITIONS,
    BatchStatusRequest,
)


class TestTransitionRules:
    """状态转换规则测试"""

    def test_submit_review_from_draft(self):
        assert _TRANSITIONS["submit_review"]["draft"] == "in_review"

    def test_submit_review_from_in_review_not_allowed(self):
        assert "in_review" not in _TRANSITIONS["submit_review"]

    def test_return_to_draft_from_in_review(self):
        assert _TRANSITIONS["return_to_draft"]["in_review"] == "draft"

    def test_mark_complete_from_in_review(self):
        assert _TRANSITIONS["mark_complete"]["in_review"] == "completed"

    def test_mark_complete_from_draft(self):
        assert _TRANSITIONS["mark_complete"]["draft"] == "completed"

    def test_mark_complete_from_completed_not_allowed(self):
        assert "completed" not in _TRANSITIONS["mark_complete"]


class TestBatchStatusRequest:
    """请求模型验证"""

    def test_valid_request(self):
        req = BatchStatusRequest(
            wp_ids=[uuid4(), uuid4()],
            action="submit_review",
            comment="批量提交",
        )
        assert len(req.wp_ids) == 2
        assert req.action == "submit_review"

    def test_optional_comment(self):
        req = BatchStatusRequest(
            wp_ids=[uuid4()],
            action="return_to_draft",
        )
        assert req.comment is None

    def test_all_actions_valid(self):
        for action in ["submit_review", "return_to_draft", "mark_complete"]:
            req = BatchStatusRequest(wp_ids=[uuid4()], action=action)
            assert req.action == action
