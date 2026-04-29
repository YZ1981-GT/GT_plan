"""Phase 14: 统一门禁引擎测试

测试用例 ID: P14-UT-001 ~ P14-UT-029
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.trace_event_service import TraceEventService, generate_trace_id
from app.services.gate_engine import GateEngine, GateRule, GateRuleHit, RuleRegistry
from app.services.sod_guard_service import SoDGuardService, CONFLICT_MATRIX
from app.models.phase14_enums import (
    GateType, GateDecisionResult, GateSeverity, ReasonCode, SoDRole
)


# ── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def trace_service():
    return TraceEventService()


@pytest.fixture
def sod_service():
    return SoDGuardService()


# ── P14-UT-025: trace_id 格式 ─────────────────────────────────

def test_generate_trace_id_format():
    """P14-UT-025: trace_id 格式校验"""
    tid = generate_trace_id()
    assert tid.startswith("trc_")
    parts = tid.split("_")
    assert len(parts) == 3
    assert len(parts[1]) == 14  # yyyyMMddHHmmss
    assert len(parts[2]) == 12  # uuid short


# ── P14-UT-021~024: TraceEventService ─────────────────────────

@pytest.mark.asyncio
async def test_trace_write_returns_trace_id(mock_db, trace_service):
    """P14-UT-021: write() 返回 trace_id"""
    tid = await trace_service.write(
        db=mock_db,
        project_id=uuid.uuid4(),
        event_type="submit_review",
        object_type="workpaper",
        object_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        action="submit",
    )
    assert tid.startswith("trc_")
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_trace_replay_l1(mock_db, trace_service):
    """P14-UT-022: replay L1 返回 who/what/when"""
    event_id = uuid.uuid4()
    mock_event = MagicMock()
    mock_event.id = event_id
    mock_event.event_type = "submit_review"
    mock_event.object_type = "workpaper"
    mock_event.object_id = uuid.uuid4()
    mock_event.actor_id = uuid.uuid4()
    mock_event.actor_role = "assistant"
    mock_event.action = "submit"
    mock_event.decision = "allow"
    mock_event.reason_code = None
    mock_event.created_at = datetime.utcnow()
    mock_event.from_status = None
    mock_event.to_status = None
    mock_event.before_snapshot = None
    mock_event.after_snapshot = None
    mock_event.content_hash = None
    mock_event.version_no = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_event]
    mock_db.execute.return_value = mock_result

    result = await trace_service.replay(mock_db, "trc_test_123456789012", "L1")
    assert result["replay_status"] == "complete"
    assert len(result["events"]) == 1
    assert "before_snapshot" not in result["events"][0]


@pytest.mark.asyncio
async def test_trace_replay_l2_includes_snapshot(mock_db, trace_service):
    """P14-UT-023: replay L2 含 snapshot"""
    mock_event = MagicMock()
    mock_event.id = uuid.uuid4()
    mock_event.event_type = "gate_evaluated"
    mock_event.object_type = "gate_decision"
    mock_event.object_id = uuid.uuid4()
    mock_event.actor_id = uuid.uuid4()
    mock_event.actor_role = "manager"
    mock_event.action = "evaluate"
    mock_event.decision = "block"
    mock_event.reason_code = "QC_PROCEDURE_MANDATORY_TRIMMED"
    mock_event.created_at = datetime.utcnow()
    mock_event.from_status = "draft"
    mock_event.to_status = "submitted"
    mock_event.before_snapshot = {"status": "draft"}
    mock_event.after_snapshot = {"status": "submitted"}
    mock_event.content_hash = None
    mock_event.version_no = 1

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_event]
    mock_db.execute.return_value = mock_result

    result = await trace_service.replay(mock_db, "trc_test_123456789012", "L2")
    assert "before_snapshot" in result["events"][0]
    assert result["events"][0]["before_snapshot"] == {"status": "draft"}


@pytest.mark.asyncio
async def test_trace_replay_l3_includes_hash(mock_db, trace_service):
    """P14-UT-024: replay L3 含 content_hash"""
    mock_event = MagicMock()
    mock_event.id = uuid.uuid4()
    mock_event.event_type = "export"
    mock_event.object_type = "export"
    mock_event.object_id = uuid.uuid4()
    mock_event.actor_id = uuid.uuid4()
    mock_event.actor_role = "manager"
    mock_event.action = "export_package"
    mock_event.decision = "allow"
    mock_event.reason_code = None
    mock_event.created_at = datetime.utcnow()
    mock_event.from_status = None
    mock_event.to_status = None
    mock_event.before_snapshot = None
    mock_event.after_snapshot = None
    mock_event.content_hash = "abc123def456"
    mock_event.version_no = 2

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_event]
    mock_db.execute.return_value = mock_result

    result = await trace_service.replay(mock_db, "trc_test_123456789012", "L3")
    assert result["events"][0]["content_hash"] == "abc123def456"


# ── P14-UT-026~029: GateEngine ────────────────────────────────

class MockBlockingRule(GateRule):
    rule_code = "MOCK-BLOCK"
    error_code = "MOCK_BLOCKING"
    severity = GateSeverity.blocking

    async def check(self, db, context):
        return GateRuleHit(
            rule_code=self.rule_code,
            error_code=self.error_code,
            severity=self.severity,
            message="Mock blocking",
            location={"section": "test"},
            suggested_action="Fix it",
        )


class MockWarningRule(GateRule):
    rule_code = "MOCK-WARN"
    error_code = "MOCK_WARNING"
    severity = GateSeverity.warning

    async def check(self, db, context):
        return GateRuleHit(
            rule_code=self.rule_code,
            error_code=self.error_code,
            severity=self.severity,
            message="Mock warning",
        )


class MockPassRule(GateRule):
    rule_code = "MOCK-PASS"
    error_code = "MOCK_PASS"
    severity = GateSeverity.info

    async def check(self, db, context):
        return None  # 未命中


@pytest.mark.asyncio
async def test_gate_engine_blocking_decision(mock_db):
    """P14-UT-026: 多条 blocking → decision=block"""
    registry = RuleRegistry()
    registry.register(GateType.submit_review, MockBlockingRule())
    registry.register(GateType.submit_review, MockWarningRule())
    engine = GateEngine(registry)

    result = await engine.evaluate(
        db=mock_db,
        gate_type=GateType.submit_review,
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        context={},
    )
    assert result.decision == GateDecisionResult.block
    assert len(result.hit_rules) == 2


@pytest.mark.asyncio
async def test_gate_engine_severity_sort(mock_db):
    """P14-UT-027: blocking 在 warning 前"""
    registry = RuleRegistry()
    registry.register(GateType.submit_review, MockWarningRule())
    registry.register(GateType.submit_review, MockBlockingRule())
    engine = GateEngine(registry)

    result = await engine.evaluate(
        db=mock_db,
        gate_type=GateType.submit_review,
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        context={},
    )
    assert result.hit_rules[0].severity == GateSeverity.blocking
    assert result.hit_rules[1].severity == GateSeverity.warning


@pytest.mark.asyncio
async def test_gate_engine_allow_when_no_hits(mock_db):
    """P14-UT-029 variant: 无命中 → decision=allow"""
    registry = RuleRegistry()
    registry.register(GateType.submit_review, MockPassRule())
    engine = GateEngine(registry)

    result = await engine.evaluate(
        db=mock_db,
        gate_type=GateType.submit_review,
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        context={},
    )
    assert result.decision == GateDecisionResult.allow
    assert len(result.hit_rules) == 0


# ── P14-UT-017~020: SoD ───────────────────────────────────────

def test_sod_conflict_matrix_completeness():
    """P14-UT-017 prereq: CONFLICT_MATRIX 包含 3 组互斥对"""
    assert len(CONFLICT_MATRIX) == 6  # 3 pairs × 2 directions


@pytest.mark.asyncio
async def test_sod_preparer_approver_conflict(mock_db, sod_service):
    """P14-UT-017: preparer == partner_approver → 403"""
    actor_id = uuid.uuid4()

    # Mock WorkingPaper with preparer_id = actor_id
    mock_wp = MagicMock()
    mock_wp.preparer_id = actor_id
    mock_wp.reviewer_id = None
    mock_wp.partner_reviewed_by = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_wp
    mock_db.execute.return_value = mock_result

    result = await sod_service.check(
        db=mock_db,
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        actor_id=actor_id,
        target_role=SoDRole.partner_approver,
    )
    assert not result.allowed
    assert "同人编制+终审" in result.conflict_type


@pytest.mark.asyncio
async def test_sod_no_conflict(mock_db, sod_service):
    """P14-UT-018: preparer != reviewer → allowed"""
    actor_id = uuid.uuid4()
    other_id = uuid.uuid4()

    mock_wp = MagicMock()
    mock_wp.preparer_id = other_id  # 不同人
    mock_wp.reviewer_id = None
    mock_wp.partner_reviewed_by = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_wp
    mock_db.execute.return_value = mock_result

    result = await sod_service.check(
        db=mock_db,
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        actor_id=actor_id,
        target_role=SoDRole.reviewer,
    )
    assert result.allowed


# ── Enum 完整性测试 ────────────────────────────────────────────

def test_reason_code_enum_count():
    """ReasonCode 枚举包含 21 个值"""
    assert len(ReasonCode) == 21


def test_gate_type_enum():
    """GateType 枚举包含 3 个值"""
    assert len(GateType) == 3


def test_sod_role_enum():
    """SoDRole 枚举包含 4 个值"""
    assert len(SoDRole) == 4
