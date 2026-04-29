"""Phase 15: 任务树与问题单测试

测试用例 ID: P15-UT-001 ~ P15-UT-024
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta

from app.services.task_tree_service import TaskTreeService, VALID_TRANSITIONS
from app.services.issue_ticket_service import IssueTicketService, SLA_HOURS, VALID_TRANSITIONS as ISSUE_TRANSITIONS
from app.models.phase15_enums import (
    NodeLevel, TaskNodeStatus, IssueStatus, IssueSource, TaskEventStatus
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def tree_service():
    return TaskTreeService()


@pytest.fixture
def issue_service():
    return IssueTicketService()


# ── P15-UT-002: transit_status 合法迁移 ────────────────────────

def test_valid_transitions_completeness():
    """P15-UT-002 prereq: VALID_TRANSITIONS 包含 4 组合法迁移"""
    assert len(VALID_TRANSITIONS) == 4
    assert (TaskNodeStatus.pending, TaskNodeStatus.in_progress) in VALID_TRANSITIONS
    assert (TaskNodeStatus.in_progress, TaskNodeStatus.blocked) in VALID_TRANSITIONS
    assert (TaskNodeStatus.blocked, TaskNodeStatus.in_progress) in VALID_TRANSITIONS
    assert (TaskNodeStatus.in_progress, TaskNodeStatus.done) in VALID_TRANSITIONS


# ── P15-UT-003: transit_status 非法迁移 ────────────────────────

def test_invalid_transition_not_in_set():
    """P15-UT-003: pending→done 不在合法迁移集中"""
    assert (TaskNodeStatus.pending, TaskNodeStatus.done) not in VALID_TRANSITIONS


# ── P15-UT-006: get_stats 聚合 ─────────────────────────────────

@pytest.mark.asyncio
async def test_get_stats(mock_db, tree_service):
    """P15-UT-006: get_stats 按 node_level × status 聚合"""
    mock_result = MagicMock()
    mock_result.all.return_value = [
        ("workpaper", "pending", 5),
        ("workpaper", "done", 3),
        ("evidence", "pending", 10),
    ]
    mock_db.execute.return_value = mock_result

    stats = await tree_service.get_stats(mock_db, uuid.uuid4())
    assert "workpaper" in stats
    assert stats["workpaper"]["pending"] == 5
    assert stats["workpaper"]["done"] == 3
    assert stats["evidence"]["pending"] == 10


# ── P15-UT-014: create_from_conversation ───────────────────────

def test_sla_hours_config():
    """P15-UT-014 prereq: SLA_HOURS 配置正确"""
    assert SLA_HOURS["P0"] == 4
    assert SLA_HOURS["P1"] == 24
    assert SLA_HOURS["P2"] == 72


# ── P15-UT-015~016: issue status transitions ──────────────────

def test_issue_valid_transitions():
    """P15-UT-015: open→in_fix 合法"""
    assert (IssueStatus.open, IssueStatus.in_fix) in ISSUE_TRANSITIONS


def test_issue_invalid_transition():
    """P15-UT-016: open→closed 非法（跳过 in_fix）"""
    assert (IssueStatus.open, IssueStatus.closed) not in ISSUE_TRANSITIONS


# ── P15-UT-018: escalate 降级阻断 ─────────────────────────────

def test_escalation_order():
    """P15-UT-018 prereq: 升级顺序 L2 < L3 < Q"""
    from app.services.issue_ticket_service import ESCALATION_ORDER
    assert ESCALATION_ORDER == [IssueSource.L2, IssueSource.L3, IssueSource.Q]


# ── 枚举完整性 ─────────────────────────────────────────────────

def test_node_level_enum():
    assert len(NodeLevel) == 4


def test_task_node_status_enum():
    assert len(TaskNodeStatus) == 4


def test_task_event_status_enum():
    assert len(TaskEventStatus) == 5


def test_issue_status_enum():
    assert len(IssueStatus) == 5


def test_issue_source_enum():
    assert len(IssueSource) == 3
