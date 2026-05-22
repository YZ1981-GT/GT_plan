"""Phase 7 Sprint 3 + Sprint 4 基础测试

覆盖：
- F7 工时填报 CRUD + 日合计校验
- F8 预算对比
- F9 推荐算法
- F10 审批关联
- F11 SSE 通知服务
- F12 紧急度评分
- F13 stale 过滤器（composable 逻辑）
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# F7: WorkHourEntry Model + Status Enum
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkHourEntryModel:
    """Task 10.1: ORM model + enum"""

    def test_status_enum_values(self):
        from app.models.workhour_entry_models import WorkHourEntryStatus

        assert WorkHourEntryStatus.draft == "draft"
        assert WorkHourEntryStatus.submitted == "submitted"
        assert WorkHourEntryStatus.approved == "approved"
        assert WorkHourEntryStatus.rejected == "rejected"

    def test_model_tablename(self):
        from app.models.workhour_entry_models import WorkHourEntry

        assert WorkHourEntry.__tablename__ == "work_hour_entries"

    def test_model_has_required_columns(self):
        from app.models.workhour_entry_models import WorkHourEntry

        columns = {c.name for c in WorkHourEntry.__table__.columns}
        expected = {
            "id", "user_id", "project_id", "date", "hours",
            "cycle", "wp_code", "procedure", "description", "status",
            "submitted_at", "approved_by", "approved_at", "rejected_reason",
            "created_at", "updated_at",
        }
        assert expected.issubset(columns)

    def test_model_indexes(self):
        from app.models.workhour_entry_models import WorkHourEntry

        index_names = {idx.name for idx in WorkHourEntry.__table__.indexes}
        assert "idx_whe_user_date" in index_names
        assert "idx_whe_project_status" in index_names
        assert "idx_whe_project_cycle" in index_names


# ═══════════════════════════════════════════════════════════════════════════════
# F7: Router helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkHourEntryRouter:
    """Task 10.2: Router helper functions"""

    def test_infer_cycle_from_wp_code(self):
        from app.routers.workhour_entries import _infer_cycle

        assert _infer_cycle("D2-1", None) == "D"
        assert _infer_cycle("E1-3", None) == "E"
        assert _infer_cycle("F2-2", None) == "F"
        assert _infer_cycle(None, "H") == "H"
        assert _infer_cycle(None, None) == "OTHER"

    def test_infer_cycle_explicit_takes_precedence(self):
        from app.routers.workhour_entries import _infer_cycle

        assert _infer_cycle("D2-1", "X") == "X"

    def test_entry_to_dict(self):
        from app.routers.workhour_entries import _entry_to_dict
        from app.models.workhour_entry_models import WorkHourEntry

        entry = WorkHourEntry(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            date=date(2026, 5, 22),
            hours=Decimal("8.5"),
            cycle="D",
            wp_code="D2-1",
            procedure=None,
            description="测试",
            status="draft",
            submitted_at=None,
            approved_by=None,
            approved_at=None,
            rejected_reason=None,
            created_at=datetime(2026, 5, 22, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 22, tzinfo=timezone.utc),
        )
        result = _entry_to_dict(entry)
        assert result["hours"] == 8.5
        assert result["cycle"] == "D"
        assert result["status"] == "draft"
        assert result["date"] == "2026-05-22"


# ═══════════════════════════════════════════════════════════════════════════════
# F8: Budget Compare
# ═══════════════════════════════════════════════════════════════════════════════


class TestBudgetCompare:
    """Task 11.2: Budget router logic"""

    def test_router_exists(self):
        from app.routers.workhour_budget import router

        assert router.prefix == "/api/projects/{project_id}/workhours/budget-vs-actual"


# ═══════════════════════════════════════════════════════════════════════════════
# F9: Review Recommend
# ═══════════════════════════════════════════════════════════════════════════════


class TestReviewRecommend:
    """Task 12.1: Recommendation algorithm"""

    def test_calc_recommendation_score_all_max(self):
        from app.routers.review_recommend import _calc_recommendation_score

        result = _calc_recommendation_score(
            review_count_in_cycle=10,
            current_week_hours=0,
            matched_cycles=1,
            total_cycles=1,
        )
        # history=1.0, capacity=1.0, expertise=1.0 → score=1.0
        assert result["score"] == 1.0

    def test_calc_recommendation_score_all_zero(self):
        from app.routers.review_recommend import _calc_recommendation_score

        result = _calc_recommendation_score(
            review_count_in_cycle=0,
            current_week_hours=40,
            matched_cycles=0,
            total_cycles=5,
        )
        # history=0, capacity=0, expertise=0 → score=0
        assert result["score"] == 0.0

    def test_calc_recommendation_score_partial(self):
        from app.routers.review_recommend import _calc_recommendation_score

        result = _calc_recommendation_score(
            review_count_in_cycle=5,
            current_week_hours=20,
            matched_cycles=1,
            total_cycles=2,
        )
        # history=0.5, capacity=0.5, expertise=0.5
        # score = 0.4*0.5 + 0.3*0.5 + 0.3*0.5 = 0.5
        assert result["score"] == 0.5

    def test_capacity_monotonicity(self):
        """More capacity (less hours worked) → higher score"""
        from app.routers.review_recommend import _calc_recommendation_score

        score_low_hours = _calc_recommendation_score(
            review_count_in_cycle=5, current_week_hours=10,
            matched_cycles=1, total_cycles=2,
        )
        score_high_hours = _calc_recommendation_score(
            review_count_in_cycle=5, current_week_hours=30,
            matched_cycles=1, total_cycles=2,
        )
        assert score_low_hours["score"] > score_high_hours["score"]

    def test_history_monotonicity(self):
        """More history → higher score"""
        from app.routers.review_recommend import _calc_recommendation_score

        score_more_history = _calc_recommendation_score(
            review_count_in_cycle=8, current_week_hours=20,
            matched_cycles=1, total_cycles=2,
        )
        score_less_history = _calc_recommendation_score(
            review_count_in_cycle=2, current_week_hours=20,
            matched_cycles=1, total_cycles=2,
        )
        assert score_more_history["score"] > score_less_history["score"]


# ═══════════════════════════════════════════════════════════════════════════════
# F10: Workhour Approval
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkHourApproval:
    """Task 13.1: Approval router"""

    def test_router_exists(self):
        from app.routers.workhour_approval import router

        assert router.prefix == "/api/projects/{project_id}/workhours/approval"

    def test_calc_wp_progress_stub(self):
        from app.routers.workhour_approval import _calc_wp_progress

        # Stub returns 0% for now
        assert _calc_wp_progress("D2-1") == 0.0
        assert _calc_wp_progress(None) == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# F11: SSE Review Notification
# ═══════════════════════════════════════════════════════════════════════════════


class TestReviewNotificationService:
    """Task 15.1: SSE notification service"""

    def test_event_type_enum_extended(self):
        from app.models.audit_platform_schemas import EventType

        assert EventType.REVIEW_ACCEPTED == "review.accepted"
        assert EventType.REVIEW_COMPLETED == "review.completed"

    def test_service_class_exists(self):
        from app.services.review_notification_service import ReviewNotificationService

        assert hasattr(ReviewNotificationService, "notify_review_accepted")
        assert hasattr(ReviewNotificationService, "notify_review_completed")

    @pytest.mark.asyncio
    async def test_notify_review_accepted_dedup(self):
        """Redis idempotent key prevents duplicate notifications"""
        from app.services.review_notification_service import ReviewNotificationService

        review_id = uuid.uuid4()
        # Mock Redis to simulate existing key
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="1")  # Already sent

        with patch("app.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)):
            result = await ReviewNotificationService.notify_review_accepted(
                review_id=review_id,
                wp_code="D2-1",
                reviewer_name="张三",
                submitter_id=uuid.uuid4(),
            )
            assert result is False  # Deduplicated

    @pytest.mark.asyncio
    async def test_notify_review_accepted_first_time(self):
        """First notification goes through"""
        from app.services.review_notification_service import ReviewNotificationService

        review_id = uuid.uuid4()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # Not sent yet
        mock_redis.set = AsyncMock()

        with patch("app.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)):
            result = await ReviewNotificationService.notify_review_accepted(
                review_id=review_id,
                wp_code="D2-1",
                reviewer_name="张三",
                submitter_id=uuid.uuid4(),
            )
            assert result is True


# ═══════════════════════════════════════════════════════════════════════════════
# F12: Partner Urgency Score
# ═══════════════════════════════════════════════════════════════════════════════


class TestPartnerUrgency:
    """Task 16.1: Urgency scoring"""

    def test_calc_urgency_score_max(self):
        from app.routers.partner_urgency import _calc_urgency_score

        # All factors at max → score = 100
        score = _calc_urgency_score(
            days_remaining=0, max_days=90,
            blocking_vr_count=10,
            completed_wp=0, total_wp=10,
        )
        assert score == 100

    def test_calc_urgency_score_min(self):
        from app.routers.partner_urgency import _calc_urgency_score

        # All factors at min → score = 0
        score = _calc_urgency_score(
            days_remaining=90, max_days=90,
            blocking_vr_count=0,
            completed_wp=10, total_wp=10,
        )
        assert score == 0

    def test_calc_urgency_score_mid(self):
        from app.routers.partner_urgency import _calc_urgency_score

        score = _calc_urgency_score(
            days_remaining=45, max_days=90,
            blocking_vr_count=5,
            completed_wp=5, total_wp=10,
        )
        # sla=0.5, vr=0.5, wp=0.5 → (0.4*0.5 + 0.3*0.5 + 0.3*0.5)*100 = 50
        assert score == 50

    def test_urgency_label_mapping(self):
        from app.routers.partner_urgency import _get_urgency_label

        assert _get_urgency_label(80) == "urgent"
        assert _get_urgency_label(90) == "urgent"
        assert _get_urgency_label(60) == "attention"
        assert _get_urgency_label(79) == "attention"
        assert _get_urgency_label(40) == "normal"
        assert _get_urgency_label(59) == "normal"
        assert _get_urgency_label(39) == "safe"
        assert _get_urgency_label(0) == "safe"

    def test_urgency_score_range(self):
        """Score always in [0, 100]"""
        from app.routers.partner_urgency import _calc_urgency_score

        # Edge case: negative days remaining
        score = _calc_urgency_score(
            days_remaining=-10, max_days=90,
            blocking_vr_count=20,
            completed_wp=0, total_wp=10,
        )
        assert 0 <= score <= 100

    def test_urgency_sla_monotonicity(self):
        """Less days remaining → higher score"""
        from app.routers.partner_urgency import _calc_urgency_score

        score_urgent = _calc_urgency_score(
            days_remaining=5, max_days=90,
            blocking_vr_count=5, completed_wp=5, total_wp=10,
        )
        score_safe = _calc_urgency_score(
            days_remaining=80, max_days=90,
            blocking_vr_count=5, completed_wp=5, total_wp=10,
        )
        assert score_urgent > score_safe

    def test_router_exists(self):
        from app.routers.partner_urgency import router

        assert router.prefix == "/api/partner/projects"


# ═══════════════════════════════════════════════════════════════════════════════
# F13: Stale Filter (composable logic tested via Python equivalent)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStaleFilterLogic:
    """Task 17.1: Stale filter logic (Python equivalent of composable)"""

    def _filter_stale(self, nodes, links):
        """Python equivalent of useStaleFilter logic"""
        stale_ids = {n["id"] for n in nodes if n.get("is_stale")}
        if not stale_ids:
            return [], []

        neighbor_ids = set()
        for link in links:
            sid = link["source"] if isinstance(link["source"], str) else link["source"]["id"]
            tid = link["target"] if isinstance(link["target"], str) else link["target"]["id"]
            if sid in stale_ids:
                neighbor_ids.add(tid)
            if tid in stale_ids:
                neighbor_ids.add(sid)

        visible_ids = stale_ids | neighbor_ids
        filtered_nodes = [n for n in nodes if n["id"] in visible_ids]
        filtered_links = [
            l for l in links
            if (l["source"] if isinstance(l["source"], str) else l["source"]["id"]) in visible_ids
            and (l["target"] if isinstance(l["target"], str) else l["target"]["id"]) in visible_ids
        ]
        return filtered_nodes, filtered_links

    def test_no_stale_returns_empty(self):
        nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        links = [{"source": "A", "target": "B"}]
        fn, fl = self._filter_stale(nodes, links)
        assert fn == []
        assert fl == []

    def test_stale_with_neighbor(self):
        nodes = [
            {"id": "A", "is_stale": True},
            {"id": "B"},
            {"id": "C"},
        ]
        links = [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
        ]
        fn, fl = self._filter_stale(nodes, links)
        # A is stale, B is 1-hop neighbor
        assert {n["id"] for n in fn} == {"A", "B"}
        # Only A→B link is visible (both endpoints visible)
        assert len(fl) == 1
        assert fl[0]["source"] == "A"

    def test_idempotent(self):
        """filter(filter(g)) == filter(g)"""
        nodes = [
            {"id": "A", "is_stale": True},
            {"id": "B"},
            {"id": "C"},
            {"id": "D", "is_stale": True},
        ]
        links = [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
            {"source": "D", "target": "C"},
        ]
        fn1, fl1 = self._filter_stale(nodes, links)
        fn2, fl2 = self._filter_stale(fn1, fl1)
        assert {n["id"] for n in fn1} == {n["id"] for n in fn2}
        assert len(fl1) == len(fl2)
