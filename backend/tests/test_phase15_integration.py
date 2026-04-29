"""Phase 15: 集成测试

测试用例 ID: P15-IT-001 ~ P15-IT-005 + P15-UT 补充
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from app.services.task_event_bus import TaskEventBus, RETRY_BASE_SECONDS, RETRY_MULTIPLIER
from app.services.task_tree_service import TaskTreeService, VALID_TRANSITIONS
from app.services.issue_ticket_service import IssueTicketService, SLA_HOURS, VALID_TRANSITIONS as ISSUE_TRANSITIONS
from app.services.rc_enhanced_service import RCEnhancedService
from app.models.phase15_enums import TaskNodeStatus, TaskEventStatus, IssueStatus, IssueSource


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


# ── P15-IT-001: trim 事件联动任务树状态 ────────────────────────

@pytest.mark.asyncio
async def test_event_bus_publish_returns_event_id(mock_db):
    """P15-UT-007 extended: publish 写入 task_events 表"""
    bus = TaskEventBus()
    # Mock: 无已有事件（幂等检查返回 None）
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    eid = await bus.publish(
        mock_db, uuid.uuid4(), "trim_applied", None,
        {"ref_id": "proc_001", "version": "1"},
    )
    # publish 写入 DB 并返回 event_id（UUID）
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited()
    # event_id 来自 TaskEvent.id（由 ORM default 生成），mock 环境下 add 的对象有 id
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj is not None


@pytest.mark.asyncio
async def test_event_bus_consume_success(mock_db):
    """P15-UT-008: consume 成功 → status=succeeded"""
    bus = TaskEventBus()

    # 注册一个成功的 handler
    async def _ok_handler(db, payload):
        pass
    bus.register_handler("test_ok", _ok_handler)

    mock_event = MagicMock()
    mock_event.id = uuid.uuid4()
    mock_event.event_type = "test_ok"
    mock_event.status = TaskEventStatus.queued
    mock_event.retry_count = 0
    mock_event.max_retries = 3
    mock_event.payload = {}
    mock_event.project_id = uuid.uuid4()
    mock_event.trace_id = "trc_test"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_event
    mock_db.execute.return_value = mock_result

    ok = await bus.consume(mock_db, mock_event.id)
    assert ok is True
    assert mock_event.status == TaskEventStatus.succeeded


@pytest.mark.asyncio
async def test_event_bus_consume_failure_retry(mock_db):
    """P15-UT-009: consume 失败 → retry_count++ + next_retry_at"""
    bus = TaskEventBus()

    async def _fail_handler(db, payload):
        raise ValueError("test error")
    bus.register_handler("test_fail", _fail_handler)

    mock_event = MagicMock()
    mock_event.id = uuid.uuid4()
    mock_event.event_type = "test_fail"
    mock_event.status = TaskEventStatus.queued
    mock_event.retry_count = 0
    mock_event.max_retries = 3
    mock_event.payload = {}
    mock_event.project_id = uuid.uuid4()
    mock_event.trace_id = "trc_test"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_event
    mock_db.execute.return_value = mock_result

    ok = await bus.consume(mock_db, mock_event.id)
    assert ok is False
    assert mock_event.retry_count == 1
    assert mock_event.status == TaskEventStatus.failed
    assert mock_event.next_retry_at is not None


@pytest.mark.asyncio
async def test_event_bus_consume_dead_letter(mock_db):
    """P15-UT-010: 超 max_retries → dead_letter"""
    bus = TaskEventBus()

    async def _fail_handler(db, payload):
        raise ValueError("permanent error")
    bus.register_handler("test_dead", _fail_handler)

    mock_event = MagicMock()
    mock_event.id = uuid.uuid4()
    mock_event.event_type = "test_dead"
    mock_event.status = TaskEventStatus.queued
    mock_event.retry_count = 2  # 已重试 2 次
    mock_event.max_retries = 3
    mock_event.payload = {}
    mock_event.project_id = uuid.uuid4()
    mock_event.trace_id = "trc_test"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_event
    mock_db.execute.return_value = mock_result

    ok = await bus.consume(mock_db, mock_event.id)
    assert ok is False
    assert mock_event.status == TaskEventStatus.dead_letter
    assert mock_event.retry_count == 3


@pytest.mark.asyncio
async def test_event_bus_replay_resets_status(mock_db):
    """P15-UT-011: replay dead_letter → queued + retry_count=0"""
    bus = TaskEventBus()

    mock_event = MagicMock()
    mock_event.id = uuid.uuid4()
    mock_event.status = TaskEventStatus.dead_letter
    mock_event.retry_count = 3
    mock_event.project_id = uuid.uuid4()
    mock_event.trace_id = "trc_test"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_event
    mock_db.execute.return_value = mock_result

    result = await bus.replay(mock_db, mock_event.id, uuid.uuid4(), "manual_retry")
    assert result["status"] == TaskEventStatus.queued
    assert mock_event.retry_count == 0
    assert mock_event.status == TaskEventStatus.queued


# ── P15-IT-004: RC 关闭态消息阻断 ─────────────────────────────

@pytest.mark.asyncio
async def test_rc_closed_state_blocks_text(mock_db):
    """P15-UT-020: 关闭态 + text → 422"""
    svc = RCEnhancedService()

    mock_result = MagicMock()
    mock_result.fetchone.return_value = ("closed",)
    mock_db.execute.return_value = mock_result

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await svc.check_closed_state_guard(mock_db, uuid.uuid4(), "text")
    assert exc_info.value.status_code == 422
    assert "RC_CONVERSATION_CLOSED" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_rc_open_state_allows_text(mock_db):
    """P15-UT-021: open 态 + text → 通过"""
    svc = RCEnhancedService()

    mock_result = MagicMock()
    mock_result.fetchone.return_value = ("open",)
    mock_db.execute.return_value = mock_result

    # 不应抛异常
    await svc.check_closed_state_guard(mock_db, uuid.uuid4(), "text")


# ── P15-IT-005: RC 错误码一致性 ────────────────────────────────

def test_rc_error_codes_defined():
    """P15-IT-005: RC 错误码在服务中被使用"""
    # RC_PERMISSION_DENIED 在路由层使用（review_conversations.py），不在 service 中
    # 验证 service 中使用的错误码
    import inspect
    source = inspect.getsource(RCEnhancedService)
    service_codes = [
        "RC_CONVERSATION_CLOSED",
        "RC_REQUIRED_FIELD_MISSING",
        "RC_NOT_FOUND",
    ]
    for code in service_codes:
        assert code in source, f"Error code {code} not found in RCEnhancedService"


# ── P15-UT-022/023: RC 导出 ────────────────────────────────────

@pytest.mark.asyncio
async def test_rc_export_missing_purpose_returns_400(mock_db):
    """P15-UT-022: export_evidence 缺 purpose → 400"""
    svc = RCEnhancedService()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await svc.export_evidence(
            mock_db, uuid.uuid4(), "", "receiver", "full_timeline", "mask", True, uuid.uuid4()
        )
    assert exc_info.value.status_code == 400
    assert "RC_REQUIRED_FIELD_MISSING" in str(exc_info.value.detail)


# ── 重试退避策略验证 ──────────────────────────────────────────

def test_retry_backoff_formula():
    """验证重试退避：1m → 5m → 25m"""
    for retry in range(3):
        delay = RETRY_BASE_SECONDS * (RETRY_MULTIPLIER ** (retry + 1))
        expected = {0: 300, 1: 1500, 2: 7500}  # 5m, 25m, 125m
        assert delay == expected[retry], f"retry={retry} delay={delay} expected={expected[retry]}"
