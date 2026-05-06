"""sla_worker Q 整改单专属 SLA 测试 — Round 3 需求 5

验证:
- source='Q' 工单 open 超过 48h → severity 升级 + 通知签字合伙人
- source='Q' 工单 in_fix 超过 7d → severity 升级 + 通知签字合伙人
- 未超时的 Q 工单不被升级
- 非 Q 工单不受 Q 分支影响
- Q 整改单强制字段校验（remediation_plan / evidence_attachment / qc_verifier_id）
- pending_recheck 时通知 qc_verifier_id

Validates: Requirements 5
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus, ProjectType
from app.models.core import Notification, Project
from app.models.phase15_enums import IssueSource, IssueStatus
from app.models.phase15_models import IssueTicket
from app.models.staff_models import ProjectAssignment, StaffMember

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)

PROJECT_ID = uuid.uuid4()
PARTNER_USER_ID = uuid.uuid4()
PARTNER_STAFF_ID = uuid.uuid4()
QC_VERIFIER_USER_ID = uuid.uuid4()
OPERATOR_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建项目 + 签字合伙人 + 质控验证人。"""
    proj = Project(
        id=PROJECT_ID, name="测试项目", client_name="客户A",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=OPERATOR_ID,
    )
    db_session.add(proj)
    await db_session.flush()

    partner = StaffMember(
        id=PARTNER_STAFF_ID, user_id=PARTNER_USER_ID,
        name="签字合伙人", title="合伙人",
    )
    db_session.add(partner)
    await db_session.flush()

    db_session.add(ProjectAssignment(
        id=uuid.uuid4(), project_id=PROJECT_ID,
        staff_id=PARTNER_STAFF_ID, role="signing_partner",
    ))
    await db_session.flush()
    await db_session.commit()
    return db_session


def _make_q_ticket(
    *,
    status: str = IssueStatus.open.value,
    severity: str = "major",
    created_hours_ago: int = 0,
    created_days_ago: int = 0,
    evidence_refs=None,
) -> IssueTicket:
    """创建一个 source='Q' 的 IssueTicket。"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    created_at = now - timedelta(hours=created_hours_ago, days=created_days_ago)
    return IssueTicket(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        source=IssueSource.Q.value,
        severity=severity,
        category="data_mismatch",
        title="质控整改单测试",
        owner_id=OPERATOR_ID,
        status=status,
        trace_id=str(uuid.uuid4()),
        created_at=created_at,
        updated_at=created_at,
        evidence_refs=evidence_refs or [],
    )


class TestQTicketSlaEscalation:
    """Q 整改单 SLA 超时升级测试。"""

    @pytest.mark.asyncio
    async def test_response_overdue_escalates_severity(self, seeded_db):
        """open 状态超过 48h → severity 从 major 升级到 blocker。"""
        db = seeded_db
        ticket = _make_q_ticket(status=IssueStatus.open.value, severity="major", created_hours_ago=50)
        db.add(ticket)
        await db.commit()

        from app.workers.sla_worker import _check_q_ticket_sla
        count = await _check_q_ticket_sla(db)

        await db.refresh(ticket)
        assert count == 1
        assert ticket.severity == "blocker"

    @pytest.mark.asyncio
    async def test_completion_overdue_escalates_severity(self, seeded_db):
        """in_fix 状态超过 7d → severity 从 minor 升级到 major。"""
        db = seeded_db
        ticket = _make_q_ticket(status=IssueStatus.in_fix.value, severity="minor", created_days_ago=8)
        db.add(ticket)
        await db.commit()

        from app.workers.sla_worker import _check_q_ticket_sla
        count = await _check_q_ticket_sla(db)

        await db.refresh(ticket)
        assert count == 1
        assert ticket.severity == "major"

    @pytest.mark.asyncio
    async def test_not_overdue_no_escalation(self, seeded_db):
        """open 状态未超过 48h → 不升级。"""
        db = seeded_db
        ticket = _make_q_ticket(status=IssueStatus.open.value, severity="major", created_hours_ago=10)
        db.add(ticket)
        await db.commit()

        from app.workers.sla_worker import _check_q_ticket_sla
        count = await _check_q_ticket_sla(db)

        await db.refresh(ticket)
        assert count == 0
        assert ticket.severity == "major"

    @pytest.mark.asyncio
    async def test_non_q_ticket_not_affected(self, seeded_db):
        """source='L2' 的工单不受 Q 分支影响。"""
        db = seeded_db
        ticket = IssueTicket(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            source=IssueSource.L2.value,
            severity="major",
            category="data_mismatch",
            title="普通问题单",
            owner_id=OPERATOR_ID,
            status=IssueStatus.open.value,
            trace_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=100),
        )
        db.add(ticket)
        await db.commit()

        from app.workers.sla_worker import _check_q_ticket_sla
        count = await _check_q_ticket_sla(db)

        await db.refresh(ticket)
        assert count == 0
        assert ticket.severity == "major"

    @pytest.mark.asyncio
    async def test_already_blocker_no_double_escalation(self, seeded_db):
        """已经是 blocker 的 Q 工单不再重复升级。"""
        db = seeded_db
        ticket = _make_q_ticket(status=IssueStatus.open.value, severity="blocker", created_hours_ago=50)
        db.add(ticket)
        await db.commit()

        from app.workers.sla_worker import _check_q_ticket_sla
        count = await _check_q_ticket_sla(db)

        assert count == 0
        await db.refresh(ticket)
        assert ticket.severity == "blocker"

    @pytest.mark.asyncio
    async def test_escalation_sends_notification_to_partner(self, seeded_db):
        """升级时应发送通知给签字合伙人。"""
        db = seeded_db
        ticket = _make_q_ticket(status=IssueStatus.open.value, severity="minor", created_hours_ago=50)
        db.add(ticket)
        await db.commit()

        from app.workers.sla_worker import _check_q_ticket_sla
        count = await _check_q_ticket_sla(db)

        assert count == 1
        # 检查通知是否已创建
        from sqlalchemy import select
        stmt = select(Notification).where(
            Notification.recipient_id == PARTNER_USER_ID,
            Notification.message_type == "qc_remediation_overdue",
        )
        result = await db.execute(stmt)
        notifications = result.scalars().all()
        assert len(notifications) == 1
        assert "质控整改单逾期" in notifications[0].title


class TestQTicketMandatoryFields:
    """Q 整改单强制字段校验测试。"""

    @pytest.mark.asyncio
    async def test_missing_fields_raises_422(self, seeded_db):
        """Q 工单进入 pending_recheck 时缺少强制字段 → 422。"""
        from fastapi import HTTPException

        from app.services.issue_ticket_service import issue_ticket_service

        db = seeded_db
        ticket = _make_q_ticket(
            status=IssueStatus.in_fix.value,
            evidence_refs=[],  # 无结构化字段
        )
        db.add(ticket)
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await issue_ticket_service.update_status(
                db, ticket.id, IssueStatus.pending_recheck.value,
                OPERATOR_ID, "fix_done",
            )
        assert exc_info.value.status_code == 422
        assert "Q_TICKET_MANDATORY_FIELDS_MISSING" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_partial_fields_raises_422(self, seeded_db):
        """Q 工单只填了部分强制字段 → 422。"""
        from fastapi import HTTPException

        from app.services.issue_ticket_service import issue_ticket_service

        db = seeded_db
        ticket = _make_q_ticket(
            status=IssueStatus.in_fix.value,
            evidence_refs={
                "remediation_plan": "整改方案",
                # 缺少 evidence_attachment 和 qc_verifier_id
            },
        )
        db.add(ticket)
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await issue_ticket_service.update_status(
                db, ticket.id, IssueStatus.pending_recheck.value,
                OPERATOR_ID, "fix_done",
            )
        assert exc_info.value.status_code == 422
        detail = exc_info.value.detail
        assert "evidence_attachment" in detail["missing_fields"]
        assert "qc_verifier_id" in detail["missing_fields"]

    @pytest.mark.asyncio
    async def test_all_fields_present_passes(self, seeded_db):
        """Q 工单所有强制字段齐全 → 正常流转到 pending_recheck。"""
        from app.services.issue_ticket_service import issue_ticket_service

        db = seeded_db
        ticket = _make_q_ticket(
            status=IssueStatus.in_fix.value,
            evidence_refs={
                "remediation_plan": "已修正现金流量表补充资料平衡差异",
                "evidence_attachment": str(uuid.uuid4()),
                "qc_verifier_id": str(QC_VERIFIER_USER_ID),
            },
        )
        db.add(ticket)
        await db.commit()

        result = await issue_ticket_service.update_status(
            db, ticket.id, IssueStatus.pending_recheck.value,
            OPERATOR_ID, "fix_done",
        )
        await db.commit()

        assert result["status"] == IssueStatus.pending_recheck.value

    @pytest.mark.asyncio
    async def test_non_q_ticket_no_validation(self, seeded_db):
        """非 Q 工单进入 pending_recheck 不需要强制字段。"""
        from app.services.issue_ticket_service import issue_ticket_service

        db = seeded_db
        ticket = IssueTicket(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            source=IssueSource.L2.value,
            severity="major",
            category="data_mismatch",
            title="普通问题单",
            owner_id=OPERATOR_ID,
            status=IssueStatus.in_fix.value,
            trace_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            evidence_refs=[],
        )
        db.add(ticket)
        await db.commit()

        result = await issue_ticket_service.update_status(
            db, ticket.id, IssueStatus.pending_recheck.value,
            OPERATOR_ID, "fix_done",
        )
        await db.commit()

        assert result["status"] == IssueStatus.pending_recheck.value


class TestQTicketRecheckNotification:
    """Q 整改单 pending_recheck 通知 qc_verifier_id 测试。"""

    @pytest.mark.asyncio
    async def test_pending_recheck_notifies_verifier(self, seeded_db):
        """Q 工单进入 pending_recheck 时通知 qc_verifier_id。"""
        from app.services.issue_ticket_service import issue_ticket_service

        db = seeded_db
        ticket = _make_q_ticket(
            status=IssueStatus.in_fix.value,
            evidence_refs={
                "remediation_plan": "已修正",
                "evidence_attachment": str(uuid.uuid4()),
                "qc_verifier_id": str(QC_VERIFIER_USER_ID),
            },
        )
        db.add(ticket)
        await db.commit()

        await issue_ticket_service.update_status(
            db, ticket.id, IssueStatus.pending_recheck.value,
            OPERATOR_ID, "fix_done",
        )
        await db.commit()

        # 检查通知
        from sqlalchemy import select
        stmt = select(Notification).where(
            Notification.recipient_id == QC_VERIFIER_USER_ID,
            Notification.message_type == "qc_recheck_requested",
        )
        result = await db.execute(stmt)
        notifications = result.scalars().all()
        assert len(notifications) == 1
        assert "二次确认" in notifications[0].title
