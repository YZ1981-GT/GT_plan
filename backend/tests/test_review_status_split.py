"""复核状态拆分测试 — 验证编制状态机 + 复核状态机 + 联动逻辑"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.models.workpaper_models import WpFileStatus, WpReviewStatus, WpStatus


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def mock_wp():
    """创建模拟底稿（含 review_status）"""
    wp = MagicMock()
    wp.id = uuid4()
    wp.project_id = uuid4()
    wp.wp_index_id = uuid4()
    wp.status = WpFileStatus.draft
    wp.review_status = WpReviewStatus.not_submitted
    wp.reviewer = uuid4()
    wp.parsed_data = {}
    wp.file_version = 1
    wp.updated_at = datetime.utcnow()
    return wp


@pytest.fixture
def mock_idx():
    idx = MagicMock()
    idx.id = uuid4()
    idx.status = WpStatus.in_progress
    return idx


class TestWpFileStatusEnum:
    """编制状态枚举完整性"""

    def test_lifecycle_values(self):
        assert WpFileStatus.draft.value == "draft"
        assert WpFileStatus.edit_complete.value == "edit_complete"
        assert WpFileStatus.under_review.value == "under_review"
        assert WpFileStatus.revision_required.value == "revision_required"
        assert WpFileStatus.review_passed.value == "review_passed"
        assert WpFileStatus.archived.value == "archived"

    def test_backward_compat(self):
        """旧值兼容"""
        assert WpFileStatus.review_level1_passed.value == "review_level1_passed"
        assert WpFileStatus.review_level2_passed.value == "review_level2_passed"


class TestWpReviewStatusEnum:
    """复核状态枚举完整性"""

    def test_all_values(self):
        assert WpReviewStatus.not_submitted.value == "not_submitted"
        assert WpReviewStatus.pending_level1.value == "pending_level1"
        assert WpReviewStatus.level1_in_progress.value == "level1_in_progress"
        assert WpReviewStatus.level1_passed.value == "level1_passed"
        assert WpReviewStatus.level1_rejected.value == "level1_rejected"
        assert WpReviewStatus.pending_level2.value == "pending_level2"
        assert WpReviewStatus.level2_in_progress.value == "level2_in_progress"
        assert WpReviewStatus.level2_passed.value == "level2_passed"
        assert WpReviewStatus.level2_rejected.value == "level2_rejected"


class TestUpdateStatus:
    """编制状态机测试"""

    @pytest.mark.asyncio
    async def test_draft_to_edit_complete(self, mock_db, mock_wp, mock_idx):
        from app.services.working_paper_service import WorkingPaperService
        mock_wp.status = WpFileStatus.draft

        # Mock DB queries
        wp_result = MagicMock()
        wp_result.scalar_one_or_none.return_value = mock_wp
        idx_result = MagicMock()
        idx_result.scalar_one_or_none.return_value = mock_idx
        mock_db.execute = AsyncMock(side_effect=[wp_result, idx_result])

        svc = WorkingPaperService()
        result = await svc.update_status(mock_db, mock_wp.id, "edit_complete")
        assert result["status"] == "edit_complete"
        assert mock_wp.status == WpFileStatus.edit_complete

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self, mock_db, mock_wp):
        from app.services.working_paper_service import WorkingPaperService
        mock_wp.status = WpFileStatus.draft

        wp_result = MagicMock()
        wp_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute = AsyncMock(return_value=wp_result)

        svc = WorkingPaperService()
        with pytest.raises(ValueError, match="状态转换不允许"):
            await svc.update_status(mock_db, mock_wp.id, "archived")

    @pytest.mark.asyncio
    async def test_archived_no_transitions(self, mock_db, mock_wp):
        from app.services.working_paper_service import WorkingPaperService
        mock_wp.status = WpFileStatus.archived

        wp_result = MagicMock()
        wp_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute = AsyncMock(return_value=wp_result)

        svc = WorkingPaperService()
        with pytest.raises(ValueError, match="状态转换不允许"):
            await svc.update_status(mock_db, mock_wp.id, "draft")


class TestUpdateReviewStatus:
    """复核状态机测试"""

    @pytest.mark.asyncio
    async def test_submit_to_pending_level1(self, mock_db, mock_wp):
        from app.services.working_paper_service import WorkingPaperService
        mock_wp.review_status = WpReviewStatus.not_submitted
        mock_wp.status = WpFileStatus.edit_complete

        wp_result = MagicMock()
        wp_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute = AsyncMock(return_value=wp_result)

        svc = WorkingPaperService()
        result = await svc.update_review_status(mock_db, mock_wp.id, "pending_level1")
        assert result["review_status"] == "pending_level1"
        # 联动：编制状态应变为 under_review
        assert mock_wp.status == WpFileStatus.under_review

    @pytest.mark.asyncio
    async def test_level1_rejected_reverts_to_revision(self, mock_db, mock_wp):
        from app.services.working_paper_service import WorkingPaperService
        mock_wp.review_status = WpReviewStatus.level1_in_progress
        mock_wp.status = WpFileStatus.under_review

        wp_result = MagicMock()
        wp_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute = AsyncMock(return_value=wp_result)

        svc = WorkingPaperService()
        result = await svc.update_review_status(mock_db, mock_wp.id, "level1_rejected")
        assert result["review_status"] == "level1_rejected"
        # 联动：编制状态应变为 revision_required
        assert mock_wp.status == WpFileStatus.revision_required

    @pytest.mark.asyncio
    async def test_level2_passed_marks_review_passed(self, mock_db, mock_wp):
        from app.services.working_paper_service import WorkingPaperService
        mock_wp.review_status = WpReviewStatus.level2_in_progress
        mock_wp.status = WpFileStatus.under_review

        wp_result = MagicMock()
        wp_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute = AsyncMock(return_value=wp_result)

        svc = WorkingPaperService()
        result = await svc.update_review_status(mock_db, mock_wp.id, "level2_passed")
        assert result["review_status"] == "level2_passed"
        # 联动：编制状态应变为 review_passed
        assert mock_wp.status == WpFileStatus.review_passed

    @pytest.mark.asyncio
    async def test_invalid_review_transition(self, mock_db, mock_wp):
        from app.services.working_paper_service import WorkingPaperService
        mock_wp.review_status = WpReviewStatus.not_submitted

        wp_result = MagicMock()
        wp_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute = AsyncMock(return_value=wp_result)

        svc = WorkingPaperService()
        with pytest.raises(ValueError, match="复核状态转换不允许"):
            await svc.update_review_status(mock_db, mock_wp.id, "level2_passed")

    @pytest.mark.asyncio
    async def test_rejected_can_resubmit(self, mock_db, mock_wp):
        """退回后可重新提交"""
        from app.services.working_paper_service import WorkingPaperService
        mock_wp.review_status = WpReviewStatus.level1_rejected

        wp_result = MagicMock()
        wp_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute = AsyncMock(return_value=wp_result)

        svc = WorkingPaperService()
        result = await svc.update_review_status(mock_db, mock_wp.id, "not_submitted")
        assert result["review_status"] == "not_submitted"


class TestFeatureMaturity:
    """功能成熟度分级测试"""

    def test_maturity_levels(self):
        from app.services.feature_flags import get_feature_maturity
        m = get_feature_maturity()
        assert m["online_editing"] == "pilot"
        assert m["project_management"] == "production"
        assert m["regulatory_filing"] == "experimental"
        assert m["offline_workpaper"] == "production"

    def test_all_features_have_maturity(self):
        from app.services.feature_flags import get_feature_maturity
        m = get_feature_maturity()
        for k, v in m.items():
            assert v in ("production", "pilot", "experimental"), f"{k} has invalid maturity: {v}"
