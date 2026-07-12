"""WorkflowGate 单元测试

覆盖：
  - classify: review_passed/archived/locked → blocked；under_review → revert_needed；其余 → writable
  - revert_if_under_review: 有编制权 → 回退 + 审计日志；无权 → 不改
  - 边界：空列表、多底稿混合状态

Requirements: 4.3, 4.4, 9.1, 9.2, 9.3
"""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.bulk_tab.workflow_gate import (
    ClassifiedItem,
    WorkflowClassification,
    WorkflowGate,
    _BLOCKED_STATUSES,
    _REVERT_NEEDED_STATUSES,
)


# ---------------------------------------------------------------------------
# classify 测试
# ---------------------------------------------------------------------------


class TestClassify:
    """测试 WorkflowGate.classify()"""

    def setup_method(self) -> None:
        self.gate = WorkflowGate()

    def test_empty_list(self) -> None:
        """空列表返回空 dict"""
        result = self.gate.classify([])
        assert result == {}

    def test_review_passed_is_blocked(self) -> None:
        """review_passed → blocked"""
        wp_id = uuid.uuid4()
        result = self.gate.classify([{"wp_id": wp_id, "status": "review_passed"}])
        assert result[wp_id].classification == "blocked"
        assert result[wp_id].reason == "review_passed"

    def test_archived_is_blocked(self) -> None:
        """archived → blocked"""
        wp_id = uuid.uuid4()
        result = self.gate.classify([{"wp_id": wp_id, "status": "archived"}])
        assert result[wp_id].classification == "blocked"
        assert result[wp_id].reason == "archived"

    def test_review_level1_passed_is_blocked(self) -> None:
        """review_level1_passed（旧值）→ blocked"""
        wp_id = uuid.uuid4()
        result = self.gate.classify([{"wp_id": wp_id, "status": "review_level1_passed"}])
        assert result[wp_id].classification == "blocked"

    def test_review_level2_passed_is_blocked(self) -> None:
        """review_level2_passed（旧值）→ blocked"""
        wp_id = uuid.uuid4()
        result = self.gate.classify([{"wp_id": wp_id, "status": "review_level2_passed"}])
        assert result[wp_id].classification == "blocked"

    def test_under_review_is_revert_needed(self) -> None:
        """under_review → revert_needed"""
        wp_id = uuid.uuid4()
        result = self.gate.classify([{"wp_id": wp_id, "status": "under_review"}])
        assert result[wp_id].classification == "revert_needed"
        assert result[wp_id].reason is None

    def test_draft_is_writable(self) -> None:
        """draft → writable"""
        wp_id = uuid.uuid4()
        result = self.gate.classify([{"wp_id": wp_id, "status": "draft"}])
        assert result[wp_id].classification == "writable"

    def test_edit_complete_is_writable(self) -> None:
        """edit_complete → writable"""
        wp_id = uuid.uuid4()
        result = self.gate.classify([{"wp_id": wp_id, "status": "edit_complete"}])
        assert result[wp_id].classification == "writable"

    def test_revision_required_is_writable(self) -> None:
        """revision_required → writable"""
        wp_id = uuid.uuid4()
        result = self.gate.classify([{"wp_id": wp_id, "status": "revision_required"}])
        assert result[wp_id].classification == "writable"

    def test_unknown_status_is_writable(self) -> None:
        """未知状态 → writable（fail-soft）"""
        wp_id = uuid.uuid4()
        result = self.gate.classify([{"wp_id": wp_id, "status": "some_future_status"}])
        assert result[wp_id].classification == "writable"

    def test_missing_status_key_is_writable(self) -> None:
        """缺少 status 键 → writable（空字符串不在阻塞集合中）"""
        wp_id = uuid.uuid4()
        result = self.gate.classify([{"wp_id": wp_id}])
        assert result[wp_id].classification == "writable"

    def test_mixed_statuses(self) -> None:
        """多底稿混合状态正确分类"""
        wp1 = uuid.uuid4()
        wp2 = uuid.uuid4()
        wp3 = uuid.uuid4()
        wp4 = uuid.uuid4()

        items = [
            {"wp_id": wp1, "status": "review_passed"},
            {"wp_id": wp2, "status": "under_review"},
            {"wp_id": wp3, "status": "draft"},
            {"wp_id": wp4, "status": "archived"},
        ]

        result = self.gate.classify(items)

        assert result[wp1].classification == "blocked"
        assert result[wp2].classification == "revert_needed"
        assert result[wp3].classification == "writable"
        assert result[wp4].classification == "blocked"

    def test_all_blocked_statuses_covered(self) -> None:
        """确保所有 blocked 状态常量都被正确分类"""
        for status in _BLOCKED_STATUSES:
            wp_id = uuid.uuid4()
            result = self.gate.classify([{"wp_id": wp_id, "status": status}])
            assert result[wp_id].classification == "blocked", f"{status} should be blocked"

    def test_all_revert_needed_statuses_covered(self) -> None:
        """确保所有 revert_needed 状态常量都被正确分类"""
        for status in _REVERT_NEEDED_STATUSES:
            wp_id = uuid.uuid4()
            result = self.gate.classify([{"wp_id": wp_id, "status": status}])
            assert result[wp_id].classification == "revert_needed", (
                f"{status} should be revert_needed"
            )


# ---------------------------------------------------------------------------
# revert_if_under_review 测试
# ---------------------------------------------------------------------------


def _make_user(role: str = "auditor", user_id: uuid.UUID | None = None) -> MagicMock:
    """构造 mock User 对象"""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.role = MagicMock()
    user.role.value = role
    return user


class TestRevertIfUnderReview:
    """测试 WorkflowGate.revert_if_under_review()"""

    def setup_method(self) -> None:
        self.gate = WorkflowGate()

    @pytest.mark.asyncio
    async def test_revert_with_edit_permission(self) -> None:
        """有编制权限的用户 → 回退成功"""
        user = _make_user("auditor")  # auditor 有 WORKPAPER_WRITE
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # Mock db session
        db = AsyncMock()
        # execute for UPDATE returns result with rowcount > 0
        mock_update_result = MagicMock()
        mock_update_result.rowcount = 1

        # execute for SELECT project_id
        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = project_id

        db.execute = AsyncMock(side_effect=[mock_update_result, mock_select_result])
        db.flush = AsyncMock()

        with patch(
            "app.services.audit_log_helper.append_audit_log",
            new_callable=AsyncMock,
        ) as mock_audit:
            result = await self.gate.revert_if_under_review(db, wp_id, user)

        assert result is True
        # 验证 UPDATE 被调用
        assert db.execute.call_count == 2  # UPDATE + SELECT project_id
        assert db.flush.called
        # 验证审计日志被写入
        assert mock_audit.called
        audit_payload = mock_audit.call_args[0][1]
        assert audit_payload["action"] == "bulk_import_revert_status"
        assert audit_payload["resource_type"] == "working_paper"
        assert audit_payload["resource_id"] == str(wp_id)
        assert audit_payload["details"]["from_status"] == "under_review"
        assert audit_payload["details"]["to_status"] == "draft"

    @pytest.mark.asyncio
    async def test_no_edit_permission_qc_role(self) -> None:
        """qc 角色无编制权限 → 不回退（Req 9.3）"""
        user = _make_user("qc")
        wp_id = uuid.uuid4()
        db = AsyncMock()

        result = await self.gate.revert_if_under_review(db, wp_id, user)

        assert result is False
        # 不应有任何 DB 操作
        db.execute.assert_not_called()
        db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_edit_permission_readonly_role(self) -> None:
        """readonly 角色无编制权限 → 不回退（Req 9.3）"""
        user = _make_user("readonly")
        wp_id = uuid.uuid4()
        db = AsyncMock()

        result = await self.gate.revert_if_under_review(db, wp_id, user)

        assert result is False
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_can_revert(self) -> None:
        """admin 有编制权限 → 可回退"""
        user = _make_user("admin")
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()

        db = AsyncMock()
        mock_update_result = MagicMock()
        mock_update_result.rowcount = 1

        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = project_id

        db.execute = AsyncMock(side_effect=[mock_update_result, mock_select_result])
        db.flush = AsyncMock()

        with patch(
            "app.services.audit_log_helper.append_audit_log",
            new_callable=AsyncMock,
        ):
            result = await self.gate.revert_if_under_review(db, wp_id, user)

        assert result is True

    @pytest.mark.asyncio
    async def test_already_not_under_review(self) -> None:
        """底稿已不是 under_review（可能并发回退）→ 返回 True"""
        user = _make_user("auditor")
        wp_id = uuid.uuid4()

        db = AsyncMock()
        # UPDATE rowcount = 0（WHERE 条件不匹配）
        mock_update_result = MagicMock()
        mock_update_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_update_result)
        db.flush = AsyncMock()

        result = await self.gate.revert_if_under_review(db, wp_id, user)

        # 仍返回 True（视为已回退）
        assert result is True

    @pytest.mark.asyncio
    async def test_audit_log_failure_does_not_block(self) -> None:
        """审计日志写入失败不阻断主流程（fail-soft）"""
        user = _make_user("manager")
        wp_id = uuid.uuid4()

        db = AsyncMock()
        mock_update_result = MagicMock()
        mock_update_result.rowcount = 1

        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = uuid.uuid4()

        db.execute = AsyncMock(side_effect=[mock_update_result, mock_select_result])
        db.flush = AsyncMock()

        with patch(
            "app.services.audit_log_helper.append_audit_log",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            # 不应抛异常
            result = await self.gate.revert_if_under_review(db, wp_id, user)

        assert result is True

    @pytest.mark.asyncio
    async def test_partner_can_revert(self) -> None:
        """partner 角色有编制权限 → 可回退"""
        user = _make_user("partner")
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()

        db = AsyncMock()
        mock_update_result = MagicMock()
        mock_update_result.rowcount = 1
        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = project_id
        db.execute = AsyncMock(side_effect=[mock_update_result, mock_select_result])
        db.flush = AsyncMock()

        with patch(
            "app.services.audit_log_helper.append_audit_log",
            new_callable=AsyncMock,
        ):
            result = await self.gate.revert_if_under_review(db, wp_id, user)

        assert result is True
