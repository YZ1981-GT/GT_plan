"""P1-1: 复核意见证据链测试

验证：
- P1-1.1: 复核意见支持关联 EvidenceRef
- P1-1.3: 关闭重大复核意见必须填写关闭依据
- P1-1.4: 统计 Aging、重复问题、逾期未回复

Validates: Requirements 3.1, 3.2, 3.3
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.workpaper_models import ReviewCommentStatus, ReviewRecord
from app.services.wp_review_service import WpReviewService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_review_record(
    *,
    priority: str = "suggest",
    status: ReviewCommentStatus = ReviewCommentStatus.open,
    evidence_refs: list | None = None,
    close_evidence_refs: list | None = None,
    close_reason: str | None = None,
    created_at: datetime | None = None,
    cell_reference: str | None = None,
    working_paper_id: uuid.UUID | None = None,
) -> ReviewRecord:
    """创建测试用 ReviewRecord（mock 对象）"""
    record = MagicMock(spec=ReviewRecord)
    record.id = uuid.uuid4()
    record.working_paper_id = working_paper_id or uuid.uuid4()
    record.cell_reference = cell_reference
    record.comment_text = "测试复核意见"
    record.commenter_id = uuid.uuid4()
    record.status = status
    record.priority = priority
    record.reply_text = None
    record.replier_id = None
    record.replied_at = None
    record.resolved_by = None
    record.resolved_at = None
    record.evidence_refs = evidence_refs or []
    record.close_evidence_refs = close_evidence_refs or []
    record.close_reason = close_reason
    record.created_at = created_at or datetime.now(timezone.utc)
    record.updated_at = datetime.now(timezone.utc)
    record.is_deleted = False
    return record


# ---------------------------------------------------------------------------
# P1-1.1: 复核意见支持关联 EvidenceRef
# ---------------------------------------------------------------------------

class TestReviewEvidenceRef:
    """P1-1.1: 复核意见创建时可关联 EvidenceRef"""

    @pytest.mark.asyncio
    async def test_add_comment_with_evidence_refs(self):
        """创建复核意见时可附带 evidence_refs"""
        svc = WpReviewService()
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        evidence = [
            {
                "evidence_type": "attachment",
                "evidence_id": "att-001",
                "project_id": "proj-001",
                "label": "银行对账单",
            },
            {
                "evidence_type": "workpaper_cell",
                "evidence_id": "wp-001-R5C3",
                "project_id": "proj-001",
                "label": "现金审定表 R5C3",
            },
        ]

        result = await svc.add_comment(
            db,
            working_paper_id=uuid.uuid4(),
            commenter_id=uuid.uuid4(),
            comment_text="请核实银行余额差异",
            cell_reference="R5C3",
            evidence_refs=evidence,
        )

        # 验证 ReviewRecord 被添加到 session
        db.add.assert_called_once()
        added_record = db.add.call_args[0][0]
        assert isinstance(added_record, ReviewRecord)
        assert added_record.evidence_refs == evidence

    @pytest.mark.asyncio
    async def test_add_comment_without_evidence_refs(self):
        """不传 evidence_refs 时默认空列表"""
        svc = WpReviewService()
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        await svc.add_comment(
            db,
            working_paper_id=uuid.uuid4(),
            commenter_id=uuid.uuid4(),
            comment_text="格式建议",
        )

        added_record = db.add.call_args[0][0]
        assert added_record.evidence_refs == []


# ---------------------------------------------------------------------------
# P1-1.3: 关闭重大复核意见必须填写关闭依据
# ---------------------------------------------------------------------------

class TestMajorIssueClosureRequiresEvidence:
    """P1-1.3: priority=must_fix 的复核意见关闭必须提供关闭依据"""

    @pytest.mark.asyncio
    async def test_must_fix_cannot_close_without_evidence(self):
        """must_fix 优先级无关闭依据时拒绝关闭"""
        svc = WpReviewService()
        db = AsyncMock()

        record = _make_review_record(priority="must_fix", status=ReviewCommentStatus.open)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="重大复核意见.*必须填写关闭依据"):
            await svc.resolve(
                db,
                review_id=record.id,
                resolved_by=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_must_fix_can_close_with_reason(self):
        """must_fix 有关闭说明时允许关闭"""
        svc = WpReviewService()
        db = AsyncMock()

        record = _make_review_record(priority="must_fix", status=ReviewCommentStatus.open)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()

        result = await svc.resolve(
            db,
            review_id=record.id,
            resolved_by=uuid.uuid4(),
            close_reason="已补充审定调整分录并核对一致",
        )

        assert result["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_must_fix_can_close_with_evidence_refs(self):
        """must_fix 有整改证据引用时允许关闭"""
        svc = WpReviewService()
        db = AsyncMock()

        record = _make_review_record(priority="must_fix", status=ReviewCommentStatus.open)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()

        close_evidence = [
            {
                "evidence_type": "attachment",
                "evidence_id": "att-fix-001",
                "project_id": "proj-001",
                "label": "修正后的对账单",
            }
        ]

        result = await svc.resolve(
            db,
            review_id=record.id,
            resolved_by=uuid.uuid4(),
            close_evidence_refs=close_evidence,
        )

        assert result["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_suggest_can_close_without_evidence(self):
        """suggest 优先级无需关闭依据"""
        svc = WpReviewService()
        db = AsyncMock()

        record = _make_review_record(priority="suggest", status=ReviewCommentStatus.open)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()

        result = await svc.resolve(
            db,
            review_id=record.id,
            resolved_by=uuid.uuid4(),
        )

        assert result["status"] == "resolved"


# ---------------------------------------------------------------------------
# P1-1.4: 统计 Aging、重复问题、逾期未回复
# ---------------------------------------------------------------------------

class TestReviewStats:
    """P1-1.4: get_review_stats 返回正确的统计数据"""

    @pytest.mark.asyncio
    async def test_stats_returns_expected_structure(self):
        """验证返回结构包含所有必需字段"""
        svc = WpReviewService()
        db = AsyncMock()

        # Mock 所有 count 查询返回 0
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        db.execute = AsyncMock(return_value=mock_result)

        result = await svc.get_review_stats(db, project_id=uuid.uuid4())

        assert "total_open" in result
        assert "overdue_count" in result
        assert "aging_buckets" in result
        assert "duplicate_count" in result
        assert "0_24h" in result["aging_buckets"]
        assert "24_72h" in result["aging_buckets"]
        assert "gt_72h" in result["aging_buckets"]

    @pytest.mark.asyncio
    async def test_stats_all_zero_on_empty_project(self):
        """无复核意见的项目，所有计数为 0"""
        svc = WpReviewService()
        db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        db.execute = AsyncMock(return_value=mock_result)

        result = await svc.get_review_stats(db, project_id=uuid.uuid4())

        assert result["total_open"] == 0
        assert result["overdue_count"] == 0
        assert result["aging_buckets"]["0_24h"] == 0
        assert result["aging_buckets"]["24_72h"] == 0
        assert result["aging_buckets"]["gt_72h"] == 0
        assert result["duplicate_count"] == 0
