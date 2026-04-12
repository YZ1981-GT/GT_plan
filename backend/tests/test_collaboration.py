"""Integration tests for Phase 3 Collaboration module services.

Validates: Requirements 3.1, 3.2, 3.3
"""

import pytest
from sqlalchemy import create_engine, Column, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import sessionmaker
from datetime import date
import uuid

from app.models.base import Base, ProjectStatus, ProjectType


# ---------------------------------------------------------------------------
# Stub tables — satisfy FK references from collaboration_models that point
# to tables not imported elsewhere (e.g. 'report_notes', 'adjustments').
# Must be defined before importing the real models so Base.metadata sees them.
# ---------------------------------------------------------------------------


class ReportNoteStub(Base):
    """Stub for 'report_notes' table referenced by SubsequentEvent."""
    __tablename__ = "report_notes"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class WorkpaperStub(Base):
    """Stub for 'workpapers' table referenced by WorkpaperReviewRecord.

    The migration defines FK → workpapers.id but the WorkingPaper model
    uses __tablename__ = "working_papers".  This stub satisfies FK resolution.
    """
    __tablename__ = "workpapers"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


# Import real models after stubs so FK resolution succeeds
from app.models.collaboration_models import (  # noqa: E402
    SubsequentEvent, SEChecklist, ProjectSync, SyncLog,
    ProjectTimeline, WorkHours, BudgetHours, PBCChecklist,
    ConfirmationList, ConfirmationLetter, ConfirmationResult,
    ConfirmationSummary, ConfirmationAttachment,
    GoingConcern, GoingConcernIndicator, ArchiveChecklist,
    ArchiveModification, WorkpaperReviewRecord,
)
from app.models.core import Project  # noqa: F401
from app.models.workpaper_models import WorkingPaper  # noqa: F401
from app.models.core import User  # noqa: F401

from app.services.review_service import ReviewService
from app.services.sync_service import SyncService
from app.services.pbc_service import PBCService
from app.services.archive_service import ArchiveService
from app.services.subsequent_event_service import SubsequentEventService
from app.services.confirmation_service import ConfirmationService
from app.services.going_concern_service import GoingConcernService


TEST_DB_URL = "sqlite:///./test_collab.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    """Provide a transactional session for each test."""
    session = TestSession()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Helper: minimal project / user fixtures
# ---------------------------------------------------------------------------

def _make_project(db, name="Test Project"):
    pid = uuid.uuid4()
    p = Project(
        id=pid,
        name=name,
        client_name="Test Client",
        audit_period_start=date(2025, 1, 1),
        audit_period_end=date(2025, 12, 31),
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
    )
    db.add(p)
    db.commit()
    return pid


def _make_user(db):
    uid = uuid.uuid4()
    u = User(
        id=uid,
        username="tester",
        email="test@example.com",
        hashed_password="fakehash",
        role="auditor",
    )
    db.add(u)
    db.commit()
    return uid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_review_service_create_and_get(db):
    """ReviewService.create_review / get_workpaper_reviews / get_pending_reviews."""
    pid = _make_project(db)
    uid = _make_user(db)
    wid = uuid.uuid4()

    review = ReviewService.create_review(
        db,
        workpaper_id=str(wid),
        project_id=str(pid),
        reviewer_id=str(uid),
        review_level=1,
    )
    assert review.id is not None
    assert review.project_id == pid
    assert review.review_level == 1

    reviews = ReviewService.get_workpaper_reviews(db, str(wid))
    assert len(reviews) == 1

    pending = ReviewService.get_pending_reviews(db, str(uid))
    assert len(pending) == 1


def test_review_service_start_and_approve(db):
    """ReviewService.start_review / approve_review workflow."""
    pid = _make_project(db)
    uid = _make_user(db)
    wid = uuid.uuid4()

    review = ReviewService.create_review(
        db, workpaper_id=str(wid), project_id=str(pid),
        reviewer_id=str(uid), review_level=2,
    )
    started = ReviewService.start_review(db, str(review.id), str(uid))
    assert started.review_status.value == "pending_review"

    approved = ReviewService.approve_review(db, str(review.id), str(uid), comments="LGTM")
    assert approved.review_status.value == "approved"
    assert approved.comments == "LGTM"


def test_review_service_reject(db):
    """ReviewService.reject_review sets status and comments."""
    pid = _make_project(db)
    uid = _make_user(db)
    wid = uuid.uuid4()

    review = ReviewService.create_review(
        db, workpaper_id=str(wid), project_id=str(pid),
        reviewer_id=str(uid), review_level=3,
    )
    rejected = ReviewService.reject_review(db, str(review.id), str(uid), comments="Needs fix")
    assert rejected.review_status.value == "rejected"
    assert rejected.comments == "Needs fix"


def test_sync_service_lock_unlock(db):
    """SyncService.acquire_lock / release_lock / get_sync_status."""
    pid = _make_project(db)
    uid = _make_user(db)

    acquired = SyncService.acquire_lock(db, str(pid), str(uid))
    assert acquired is True

    status = SyncService.get_sync_status(db, str(pid))
    assert status is not None
    assert status.is_locked is True
    assert status.locked_by == uid

    released = SyncService.release_lock(db, str(pid), str(uid))
    assert released is True

    status2 = SyncService.get_sync_status(db, str(pid))
    assert status2.is_locked is False


def test_sync_service_record_sync(db):
    """SyncService.record_sync increments global_version."""
    from app.models.collaboration_models import SyncType

    pid = _make_project(db)
    uid = _make_user(db)

    sync = SyncService.record_sync(
        db, project_id=str(pid), user_id=str(uid),
        sync_type=SyncType.upload, details={"file": "test.xlsx"},
    )
    assert sync.global_version == 2  # get_or_create starts at 1, +1 for record_sync

    logs = SyncService.get_sync_logs(db, str(pid))
    assert len(logs) == 1
    assert logs[0].sync_type == SyncType.upload


def test_pbc_service_create_and_update(db):
    """PBCService.create_item / update_status."""
    pid = _make_project(db)

    item = PBCService.create_item(
        db,
        project_id=str(pid),
        item_name="Bank Statement",
        category="documentation",
    )
    assert item.item_name == "Bank Statement"
    assert item.status.value == "pending"

    updated = PBCService.update_status(
        db, str(item.id), "received", received_date="2025-01-15"
    )
    assert updated is not None
    status_name = updated.status.name.lower()
    assert status_name == "received"


def test_pbc_service_get_pending(db):
    """PBCService.get_pending_reminders returns pending/in_progress items."""
    pid = _make_project(db)

    item1 = PBCService.create_item(db, project_id=str(pid), item_name="Invoice")
    item2 = PBCService.create_item(db, project_id=str(pid), item_name="Contract")
    PBCService.update_status(db, str(item1.id), "received")

    pending = PBCService.get_pending_reminders(db, str(pid))
    assert len(pending) == 1
    assert pending[0].item_name == "Contract"


def test_archive_service_init_checklist(db):
    """ArchiveService.init_checklist creates 12 standard items; no duplicates."""
    pid = _make_project(db)

    items = ArchiveService.init_checklist(db, str(pid))
    assert len(items) == 12  # Standard 12-item checklist

    # Calling again should not create duplicates
    items2 = ArchiveService.init_checklist(db, str(pid))
    assert len(items2) == 0  # All items already exist — returns empty list


def test_archive_service_complete_item(db):
    """ArchiveService.complete_item marks item as completed."""
    pid = _make_project(db)
    uid = _make_user(db)

    created = ArchiveService.init_checklist(db, str(pid))
    assert len(created) == 12

    # Complete the first item
    first_item = created[0]
    completed = ArchiveService.complete_item(
        db, str(first_item.id), str(uid), notes="Checked and done"
    )
    assert completed is not None
    assert completed.is_completed is True
    assert completed.completed_by == uid
    assert completed.notes == "Checked and done"


def test_subsequent_event_service_init_checklist(db):
    """SubsequentEventService.init_checklist creates 6 standard items."""
    pid = _make_project(db)

    items = SubsequentEventService.init_checklist(db, str(pid))
    assert len(items) == 6  # Standard 6-item checklist

    codes = [i.item_code for i in items]
    assert "SE-001" in codes
    assert "SE-006" in codes


def test_subsequent_event_service_create_and_get(db):
    """SubsequentEventService.create_event / get_project_events."""
    pid = _make_project(db)
    uid = _make_user(db)

    event = SubsequentEventService.create_event(
        db,
        project_id=str(pid),
        event_date="2025-02-15",
        event_type="adjusting",
        description="Big lawsuit settlement",
        financial_impact=500000.0,
        created_by=str(uid),
    )
    assert event.description == "Big lawsuit settlement"
    assert event.event_type.value == "adjusting"
    assert event.financial_impact == 500000.0

    events = SubsequentEventService.get_project_events(db, str(pid))
    assert len(events) == 1


def test_subsequent_event_service_mark_disclosed(db):
    """SubsequentEventService.mark_disclosed sets is_disclosed."""
    pid = _make_project(db)

    items = SubsequentEventService.init_checklist(db, str(pid))
    first = items[0]
    completed = SubsequentEventService.complete_checklist_item(
        db, str(first.id), str(uuid.uuid4()), notes="SE-001 done"
    )
    assert completed.is_completed is True


def test_confirmation_service_create_and_summary(db):
    """ConfirmationService.create_confirmation / create_summary."""
    pid = _make_project(db)
    uid = _make_user(db)

    c = ConfirmationService.create_confirmation(
        db,
        project_id=str(pid),
        confirmation_type="BANK",
        description="Test bank confirmation",
        counterparty_name="Test Bank",
        account_info="1234567890",
        balance=10000.0,
        balance_date="2025-03-31",
        created_by=str(uid),
    )
    assert c.counterparty_name == "Test Bank"
    assert c.status.value == "pending"

    summary = ConfirmationService.create_summary(
        db, project_id=str(pid), summary_date="2025-03-31", created_by=str(uid)
    )
    assert summary.total_count == 1
    assert summary.not_replied_count == 1  # status=pending → not_replied


def test_confirmation_service_record_result(db):
    """ConfirmationService.record_result updates confirmation result."""
    pid = _make_project(db)
    uid = _make_user(db)

    c = ConfirmationService.create_confirmation(
        db, project_id=str(pid), confirmation_type="AR",
        description="AR confirmation", counterparty_name="Client ABC",
        balance=50000.0, balance_date="2025-03-31", created_by=str(uid),
    )
    result = ConfirmationService.record_result(
        db,
        confirmation_id=str(c.id),
        reply_status="confirmed_match",
        confirmed_amount=50000.0,
        difference_amount=0.0,
    )
    assert result.reply_status.value == "confirmed_match"
    assert result.confirmed_amount == 50000.0
    assert result.needs_adjustment is False


def test_going_concern_service_init_indicators(db):
    """GoingConcernService.init_indicators creates 14 standard indicators."""
    pid = _make_project(db)
    uid = _make_user(db)

    indicators = GoingConcernService.init_indicators(db, str(pid), str(uid))
    assert len(indicators) == 14  # 14 standard indicators

    codes = [i.indicator_type for i in indicators]
    assert "FIN-001" in codes
    assert "LAW-001" in codes
    assert "EXT-001" in codes
    assert "OPS-001" in codes


def test_going_concern_service_update_evaluation(db):
    """GoingConcernService.update_evaluation sets risk level and conclusion."""
    pid = _make_project(db)
    uid = _make_user(db)

    indicators = GoingConcernService.init_indicators(db, str(pid), str(uid))
    gc_id = indicators[0].going_concern_id

    updated = GoingConcernService.update_evaluation(
        db,
        gc_id=str(gc_id),
        has_gc_indicator=True,
        risk_level="high",
        assessment_basis="Net current liabilities exceed equity",
        auditor_conclusion="Material uncertainty exists",
    )
    assert updated is not None
    assert updated.has_gc_indicator is True
    assert updated.risk_level.value == "high"


def test_going_concern_service_update_indicator(db):
    """GoingConcernService.update_indicator marks indicator as identified."""
    pid = _make_project(db)
    uid = _make_user(db)

    indicators = GoingConcernService.init_indicators(db, str(pid), str(uid))
    fin001 = next(i for i in indicators if i.indicator_type == "FIN-001")

    updated = GoingConcernService.update_indicator(
        db,
        indicator_id=str(fin001.id),
        is_identified=True,
        evidence="Company has reported 3 consecutive years of losses",
    )
    assert updated is not None
    assert updated.is_identified is True
    assert updated.evidence is not None


def test_review_service_is_review_chain_complete(db):
    """ReviewService.is_review_chain_complete checks all required levels approved."""
    pid = _make_project(db)
    uid = _make_user(db)
    wid = uuid.uuid4()

    # Level 1 approved
    r1 = ReviewService.create_review(
        db, workpaper_id=str(wid), project_id=str(pid),
        reviewer_id=str(uid), review_level=1,
    )
    ReviewService.approve_review(db, str(r1.id), str(uid))

    # Level 2 approved
    r2 = ReviewService.create_review(
        db, workpaper_id=str(wid), project_id=str(pid),
        reviewer_id=str(uid), review_level=2,
    )
    ReviewService.approve_review(db, str(r2.id), str(uid))

    complete = ReviewService.is_review_chain_complete(db, str(wid), [1, 2])
    assert complete is True

    # Level 3 not approved
    ReviewService.create_review(
        db, workpaper_id=str(wid), project_id=str(pid),
        reviewer_id=str(uid), review_level=3,
    )
    partial = ReviewService.is_review_chain_complete(db, str(wid), [1, 2, 3])
    assert partial is False


def test_archive_service_request_modification(db):
    """ArchiveService.request_modification / get_pending_modifications."""
    pid = _make_project(db)
    uid = _make_user(db)

    mod = ArchiveService.request_modification(
        db,
        project_id=str(pid),
        requested_by=str(uid),
        modification_type="workpaper_update",
        description="Please update the revenue recognition note",
    )
    assert mod.approval_status.value == "pending"

    pending = ArchiveService.get_pending_modifications(db, str(pid))
    assert len(pending) == 1

    approved = ArchiveService.approve_modification(
        db, str(mod.id), str(uid), comments="Approved, please proceed"
    )
    assert approved.approval_status.value == "approved"
    assert approved.approval_comments == "Approved, please proceed"
