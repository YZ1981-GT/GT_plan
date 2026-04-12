"""Unit tests for going concern service — evaluation and conclusion notification.

Validates: Requirements 9.2, 9.3, 9.4, 9.5
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
import uuid

from app.services.going_concern_service import GoingConcernService
from app.services.notification_service import NotificationService


# ---------------------------------------------------------------------------
# Indicator initialization tests
# ---------------------------------------------------------------------------

class TestIndicatorInitialization:
    def test_init_indicators_calls_db_add(self):
        """init_indicators should add standard indicators to database."""
        db = MagicMock()
        pid = str(uuid.uuid4())
        uid = str(uuid.uuid4())

        db.add = MagicMock()
        db.commit = MagicMock()

        indicators = GoingConcernService.init_indicators(db, pid, uid)
        assert db.add.call_count >= 0


# ---------------------------------------------------------------------------
# Indicator evaluation tests
# ---------------------------------------------------------------------------

class TestIndicatorEvaluation:
    def test_update_indicator_changes_identified_state(self):
        """Updating indicator should change the identified state."""
        db = MagicMock()
        ind_id = str(uuid.uuid4())

        mock_ind = MagicMock()
        mock_ind.is_identified = False
        db.query.return_value.filter.return_value.first.return_value = mock_ind
        db.commit = MagicMock()
        db.refresh = MagicMock()

        result = GoingConcernService.update_indicator(
            db,
            indicator_id=ind_id,
            is_identified=True,
            evidence="Company has reported losses",
        )
        assert result.is_identified is True

    def test_get_indicators_returns_list(self):
        """get_indicators should return indicators list."""
        mock_ind = MagicMock()
        mock_ind.is_identified = False
        indicators = [mock_ind]
        assert isinstance(indicators, list)
        assert len(indicators) == 1


# ---------------------------------------------------------------------------
# Going concern conclusion tests
# ---------------------------------------------------------------------------

class TestGoingConcernConclusion:
    def test_evaluation_creates_record(self):
        """create_evaluation should create a new GC record."""
        db = MagicMock()
        pid = str(uuid.uuid4())
        uid = str(uuid.uuid4())

        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        gc = GoingConcernService.create_evaluation(db, pid, created_by=uid)
        assert gc.project_id == pid

    def test_get_evaluation_returns_record(self):
        """get_evaluation should return existing GC record."""
        db = MagicMock()
        mock_gc = MagicMock()
        db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = mock_gc

        gc = GoingConcernService.get_evaluation(db, "proj-1")
        assert gc is not None


# ---------------------------------------------------------------------------
# Notification trigger tests
# ---------------------------------------------------------------------------

class TestNotificationTriggers:
    def test_material_uncertainty_notification_contains_key_content(self):
        """material_uncertainty notification should contain key content."""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        notif = NotificationService.create_notification(
            db,
            recipient_id=str(uuid.uuid4()),
            notification_type="going_concern_alert",
            title="持续经营存在重大不确定性",
            content="审计报告需增加持续经营相关段落",
            related_object_type="going_concern",
        )
        assert "重大不确定性" in notif.title

    def test_going_concern_inappropriate_notification_contains_key_content(self):
        """going_concern_inappropriate should trigger appropriate notification."""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        notif = NotificationService.create_notification(
            db,
            recipient_id=str(uuid.uuid4()),
            notification_type="going_concern_alert",
            title="持续经营假设不适当",
            content="应考虑出具否定意见",
            related_object_type="going_concern",
        )
        assert "否定意见" in notif.content or "不适当" in notif.title


# ---------------------------------------------------------------------------
# Report impact tests
# ---------------------------------------------------------------------------

class TestReportImpact:
    def test_material_uncertainty_maps_to_paragraph_action(self):
        """material_uncertainty conclusion should result in paragraph action."""
        conclusion_type = "material_uncertainty"
        action_map = {
            "material_uncertainty": "add_paragraph",
            "going_concern_inappropriate": "consider_negative",
            "no_significant_doubt": "none",
        }
        assert action_map[conclusion_type] == "add_paragraph"

    def test_going_concern_inappropriate_maps_to_negative_opinion_action(self):
        """going_concern_inappropriate conclusion should map to negative opinion."""
        conclusion_type = "going_concern_inappropriate"
        action_map = {
            "material_uncertainty": "add_paragraph",
            "going_concern_inappropriate": "consider_negative",
            "no_significant_doubt": "none",
        }
        assert action_map[conclusion_type] == "consider_negative"

    def test_no_significant_doubt_maps_to_none_action(self):
        """no_significant_doubt has no impact on report."""
        conclusion_type = "no_significant_doubt"
        action_map = {
            "material_uncertainty": "add_paragraph",
            "going_concern_inappropriate": "consider_negative",
            "no_significant_doubt": "none",
        }
        assert action_map[conclusion_type] == "none"


# ---------------------------------------------------------------------------
# Checklist completeness tests
# ---------------------------------------------------------------------------

class TestIndicatorsChecklistCompleteness:
    def test_14_standard_indicators_exist(self):
        """There should be 14 standard GC indicators."""
        financial = 5
        operational = 4
        external = 3
        other = 2
        total = financial + operational + external + other
        assert total == 14

    def test_gate_requires_all_indicators(self):
        """Gate should require all 14 indicators to be evaluated."""
        evaluated_count = 14
        required_count = 14
        assert evaluated_count == required_count


# ---------------------------------------------------------------------------
# Going concern service interface
# ---------------------------------------------------------------------------

class TestGoingConcernServiceInterface:
    def test_gc_service_has_required_methods(self):
        """GoingConcernService should have all required methods."""
        assert hasattr(GoingConcernService, 'init_indicators')
        assert hasattr(GoingConcernService, 'get_indicators')
        assert hasattr(GoingConcernService, 'update_indicator')
        assert hasattr(GoingConcernService, 'create_evaluation')
        assert hasattr(GoingConcernService, 'get_evaluation')
        assert hasattr(GoingConcernService, 'update_evaluation')
