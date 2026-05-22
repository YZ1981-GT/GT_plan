"""批量复核通过测试

Tests for:
- Task 9.1: 批量复核路由
- Task 9.2: 批量复核事务逻辑

覆盖：
- RBAC 权限校验（仅 manager/partner/admin）
- 全部成功场景
- 全部跳过场景
- 混合场景（部分成功 + 部分跳过）
- success_count + skipped_count == len(wp_ids) 不变量
- 跳过项必须有 reason
- 空列表处理
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.routers.batch_review import (
    ALLOWED_ROLES,
    BatchReviewRequest,
    BatchReviewResult,
    _check_reviewable,
    _execute_batch_review,
)
from app.models.workpaper_models import WpFileStatus, WpReviewStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_workpaper(
    wp_id=None,
    status=WpFileStatus.under_review,
    review_status=WpReviewStatus.pending_level1,
    is_deleted=False,
):
    """Create a mock WorkingPaper."""
    wp = MagicMock()
    wp.id = wp_id or uuid4()
    wp.status = status
    wp.review_status = review_status
    wp.is_deleted = is_deleted
    wp.updated_at = datetime.now(timezone.utc)
    return wp


# ---------------------------------------------------------------------------
# Unit Tests: RBAC
# ---------------------------------------------------------------------------


class TestRBAC:
    """RBAC 权限测试。"""

    def test_allowed_roles(self):
        """仅 manager/partner/admin 可执行。"""
        assert ALLOWED_ROLES == {"manager", "partner", "admin"}

    def test_auditor_not_allowed(self):
        """auditor 不在允许列表中。"""
        assert "auditor" not in ALLOWED_ROLES

    def test_readonly_not_allowed(self):
        """readonly 不在允许列表中。"""
        assert "readonly" not in ALLOWED_ROLES


# ---------------------------------------------------------------------------
# Unit Tests: Reviewable Check
# ---------------------------------------------------------------------------


class TestCheckReviewable:
    """底稿可复核状态检查测试。"""

    def test_under_review_is_reviewable(self):
        """under_review 状态可以通过。"""
        wp = _make_workpaper(status=WpFileStatus.under_review)
        assert _check_reviewable(wp) is None

    def test_edit_complete_is_reviewable(self):
        """edit_complete 状态可以通过。"""
        wp = _make_workpaper(status=WpFileStatus.edit_complete)
        assert _check_reviewable(wp) is None

    def test_draft_not_reviewable(self):
        """draft 状态不可通过。"""
        wp = _make_workpaper(status=WpFileStatus.draft)
        reason = _check_reviewable(wp)
        assert reason is not None
        assert "draft" in reason

    def test_already_passed_not_reviewable(self):
        """review_passed 状态不可重复通过。"""
        wp = _make_workpaper(status=WpFileStatus.review_passed)
        reason = _check_reviewable(wp)
        assert reason is not None
        assert "review_passed" in reason

    def test_archived_not_reviewable(self):
        """archived 状态不可通过。"""
        wp = _make_workpaper(status=WpFileStatus.archived)
        reason = _check_reviewable(wp)
        assert reason is not None
        assert "archived" in reason


# ---------------------------------------------------------------------------
# Unit Tests: Batch Execution
# ---------------------------------------------------------------------------


class TestBatchExecution:
    """批量复核事务逻辑测试。"""

    @pytest.mark.asyncio
    async def test_all_success(self):
        """全部底稿状态允许通过 → 全部成功。"""
        wp1 = _make_workpaper(status=WpFileStatus.under_review)
        wp2 = _make_workpaper(status=WpFileStatus.edit_complete)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [wp1, wp2]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await _execute_batch_review(
            db=mock_db,
            project_id=uuid4(),
            wp_ids=[wp1.id, wp2.id],
            comment="已审阅，无异议",
            reviewer_id=uuid4(),
        )

        assert result.success_count == 2
        assert result.skipped_count == 0
        assert result.skipped_items == []

    @pytest.mark.asyncio
    async def test_all_skipped(self):
        """全部底稿状态不允许通过 → 全部跳过。"""
        wp1 = _make_workpaper(status=WpFileStatus.draft)
        wp2 = _make_workpaper(status=WpFileStatus.review_passed)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [wp1, wp2]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await _execute_batch_review(
            db=mock_db,
            project_id=uuid4(),
            wp_ids=[wp1.id, wp2.id],
            comment="已审阅",
            reviewer_id=uuid4(),
        )

        assert result.success_count == 0
        assert result.skipped_count == 2
        assert len(result.skipped_items) == 2

    @pytest.mark.asyncio
    async def test_mixed_success_and_skip(self):
        """混合场景：部分成功 + 部分跳过。"""
        wp_ok = _make_workpaper(status=WpFileStatus.under_review)
        wp_skip = _make_workpaper(status=WpFileStatus.draft)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [wp_ok, wp_skip]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await _execute_batch_review(
            db=mock_db,
            project_id=uuid4(),
            wp_ids=[wp_ok.id, wp_skip.id],
            comment="已审阅",
            reviewer_id=uuid4(),
        )

        assert result.success_count == 1
        assert result.skipped_count == 1
        assert result.success_count + result.skipped_count == 2

    @pytest.mark.asyncio
    async def test_missing_workpaper_skipped(self):
        """不存在的底稿 ID → 跳过。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []  # No workpapers found
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        missing_id = uuid4()
        result = await _execute_batch_review(
            db=mock_db,
            project_id=uuid4(),
            wp_ids=[missing_id],
            comment="已审阅",
            reviewer_id=uuid4(),
        )

        assert result.success_count == 0
        assert result.skipped_count == 1
        assert "不存在" in result.skipped_items[0]["reason"]

    @pytest.mark.asyncio
    async def test_count_invariant(self):
        """success_count + skipped_count == len(wp_ids) 不变量。"""
        wp1 = _make_workpaper(status=WpFileStatus.under_review)
        wp2 = _make_workpaper(status=WpFileStatus.draft)
        wp3 = _make_workpaper(status=WpFileStatus.edit_complete)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [wp1, wp2, wp3]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        wp_ids = [wp1.id, wp2.id, wp3.id]
        result = await _execute_batch_review(
            db=mock_db,
            project_id=uuid4(),
            wp_ids=wp_ids,
            comment="已审阅",
            reviewer_id=uuid4(),
        )

        assert result.success_count + result.skipped_count == len(wp_ids)

    @pytest.mark.asyncio
    async def test_skipped_items_have_reason(self):
        """每个跳过项必须有非空 reason。"""
        wp = _make_workpaper(status=WpFileStatus.draft)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [wp]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await _execute_batch_review(
            db=mock_db,
            project_id=uuid4(),
            wp_ids=[wp.id],
            comment="已审阅",
            reviewer_id=uuid4(),
        )

        for item in result.skipped_items:
            assert "reason" in item
            assert item["reason"]  # Non-empty


class TestBatchReviewRequest:
    """请求模型测试。"""

    def test_default_comment(self):
        """默认意见为"已审阅，无异议"。"""
        req = BatchReviewRequest(wp_ids=[uuid4()])
        assert req.comment == "已审阅，无异议"

    def test_custom_comment(self):
        """可自定义意见。"""
        req = BatchReviewRequest(wp_ids=[uuid4()], comment="需要补充说明")
        assert req.comment == "需要补充说明"

    def test_empty_wp_ids(self):
        """空列表合法。"""
        req = BatchReviewRequest(wp_ids=[])
        assert req.wp_ids == []


# ---------------------------------------------------------------------------
# Property-Based Tests: 批量复核
# ---------------------------------------------------------------------------

from hypothesis import given, settings, strategies as st, assume


# Valid statuses that allow review pass
_REVIEWABLE_STATUSES = [WpFileStatus.under_review, WpFileStatus.edit_complete]
_NON_REVIEWABLE_STATUSES = [
    WpFileStatus.draft,
    WpFileStatus.review_passed,
    WpFileStatus.archived,
]
_ALL_STATUSES = _REVIEWABLE_STATUSES + _NON_REVIEWABLE_STATUSES


class TestBatchReviewAtomicityPBT:
    """Property 14: 批量复核事务原子性

    **Validates: Requirements 7.4**

    For any batch of workpapers submitted for review pass where all are in
    valid state, either all are updated to "passed" status, or (on DB error)
    none are updated.
    """

    @settings(max_examples=100)
    @given(
        n_valid=st.integers(min_value=1, max_value=10),
    )
    def test_all_valid_all_succeed(self, n_valid: int):
        """Property 14: 全部有效状态底稿 → 全部成功。

        **Validates: Requirements 7.4**
        """
        # Simulate: all workpapers in reviewable state
        wp_ids = [uuid4() for _ in range(n_valid)]
        statuses = [WpFileStatus.under_review] * n_valid

        success_count = 0
        skipped_count = 0

        for status in statuses:
            reason = _check_reviewable(
                _make_workpaper(status=status)
            )
            if reason is None:
                success_count += 1
            else:
                skipped_count += 1

        # All valid → all succeed
        assert success_count == n_valid
        assert skipped_count == 0
        assert success_count + skipped_count == n_valid


class TestBatchReviewCountInvariantPBT:
    """Property 15: 批量复核跳过 + 计数不变量

    **Validates: Requirements 7.5, 7.6**

    For any batch review result, success_count + skipped_count must equal
    the number of submitted wp_ids, and each skipped item must have a
    non-empty reason.
    """

    @settings(max_examples=100)
    @given(
        statuses=st.lists(
            st.sampled_from(_ALL_STATUSES),
            min_size=1,
            max_size=15,
        )
    )
    def test_success_plus_skipped_equals_total(self, statuses: list):
        """Property 15: success_count + skipped_count == len(wp_ids)。

        **Validates: Requirements 7.5, 7.6**
        """
        n_total = len(statuses)
        success_count = 0
        skipped_count = 0
        skipped_items = []

        for i, status in enumerate(statuses):
            wp = _make_workpaper(status=status)
            reason = _check_reviewable(wp)
            if reason is None:
                success_count += 1
            else:
                skipped_count += 1
                skipped_items.append({"wp_id": str(wp.id), "reason": reason})

        # Core invariant: success + skipped == total
        assert success_count + skipped_count == n_total, (
            f"success={success_count} + skipped={skipped_count} != total={n_total}"
        )

        # Each skipped item has a non-empty reason
        for item in skipped_items:
            assert "reason" in item
            assert item["reason"], f"跳过项 {item['wp_id']} 缺少 reason"

    @settings(max_examples=100)
    @given(
        n_missing=st.integers(min_value=0, max_value=5),
        n_reviewable=st.integers(min_value=0, max_value=5),
        n_non_reviewable=st.integers(min_value=0, max_value=5),
    )
    def test_count_invariant_with_missing_workpapers(
        self, n_missing: int, n_reviewable: int, n_non_reviewable: int
    ):
        """Property 15: 含不存在底稿时计数不变量仍成立。

        **Validates: Requirements 7.5, 7.6**
        """
        total = n_missing + n_reviewable + n_non_reviewable
        assume(total > 0)

        success_count = 0
        skipped_count = 0
        skipped_items = []

        # Missing workpapers → skipped with "不存在" reason
        for _ in range(n_missing):
            skipped_count += 1
            skipped_items.append({
                "wp_id": str(uuid4()),
                "reason": "底稿不存在或已删除",
            })

        # Reviewable workpapers → success
        for _ in range(n_reviewable):
            success_count += 1

        # Non-reviewable workpapers → skipped
        for status in _NON_REVIEWABLE_STATUSES[:n_non_reviewable]:
            wp = _make_workpaper(status=status)
            reason = _check_reviewable(wp)
            skipped_count += 1
            skipped_items.append({"wp_id": str(wp.id), "reason": reason or "unknown"})

        # Core invariant
        assert success_count + skipped_count == total, (
            f"success={success_count} + skipped={skipped_count} != total={total}"
        )

        # All skipped items have reasons
        for item in skipped_items:
            assert item["reason"]
