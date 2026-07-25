"""调整分录协作接力 AdjustmentCollaborationService 属性/单元测试

spec: adjustment-collaboration-and-propagation — Property 1-7, 12

覆盖：状态机合法/非法转换(P1)/事件 append-only(P2)/单组活跃唯一+多轮(P3)/
协作锁(P4)/补充借贷平衡守卫(P5)/approved 拒绝(P6)/通知触发(P7)/权限守卫(P12)。
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountSource,
    AdjustmentCollaboration,
    AdjustmentCollaborationEvent,
    AdjustmentType,
    ReviewStatus,
    TrialBalance,
)
from app.models.audit_platform_schemas import (
    AdjustmentCreate,
    AdjustmentLineItem,
    AdjustmentSyncLineItem,
    AdjustmentSyncRequest,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.adjustment_service import AdjustmentService
from app.services.adjustment_sync_service import AdjustmentSyncService, AdjustmentSyncError
from app.services import adjustment_collaboration_service as collab_mod
from app.services.adjustment_collaboration_service import (
    AdjustmentCollaborationService,
    CollaborationError,
    has_active_collaboration,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

_INITIATOR = uuid.uuid4()
_ASSIGNEE_UID = uuid.uuid4()
_STAFF_ID = uuid.uuid4()
_NON_MEMBER = uuid.uuid4()
_WP_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def pid(db_session: AsyncSession):
    project = Project(
        id=uuid.uuid4(), name="协作测试_2025", client_name="协作测试",
        project_type=ProjectType.annual, status=ProjectStatus.planning,
        created_by=_INITIATOR,
    )
    db_session.add(project)
    await db_session.flush()
    p = project.id
    db_session.add_all([
        AccountChart(project_id=p, account_code="1001", account_name="库存现金",
                     direction=AccountDirection.debit, level=1,
                     category=AccountCategory.asset, source=AccountSource.standard),
        AccountChart(project_id=p, account_code="6001", account_name="主营业务收入",
                     direction=AccountDirection.credit, level=1,
                     category=AccountCategory.revenue, source=AccountSource.standard),
    ])
    # 被指派人：StaffMember + ProjectAssignment（项目成员）
    db_session.add(StaffMember(id=_STAFF_ID, user_id=_ASSIGNEE_UID, name="张三"))
    db_session.add(ProjectAssignment(project_id=p, staff_id=_STAFF_ID, role="auditor"))
    await db_session.commit()
    return p


def _line_items(debit="5000", credit="5000"):
    return [
        AdjustmentSyncLineItem(standard_account_code="1001", account_name="库存现金",
                               debit_amount=Decimal(debit), credit_amount=Decimal("0")),
        AdjustmentSyncLineItem(standard_account_code="6001", account_name="主营业务收入",
                               debit_amount=Decimal("0"), credit_amount=Decimal(credit)),
    ]


async def _create_manual_group(db, project_id) -> uuid.UUID:
    """创建一个手工调整组，返回 entry_group_id。"""
    svc = AdjustmentService(db)
    res = await svc.create_entry(project_id, AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025, company_code="001",
        description="待协作补充",
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", account_name="库存现金",
                               debit_amount=Decimal("5000"), credit_amount=Decimal("0")),
            AdjustmentLineItem(standard_account_code="6001", account_name="主营业务收入",
                               debit_amount=Decimal("0"), credit_amount=Decimal("5000")),
        ],
    ), _INITIATOR, batch_mode=True)
    await db.flush()
    return res.entry_group_id


async def _events(db, collab_id) -> list[str]:
    r = await db.execute(
        sa.select(AdjustmentCollaborationEvent.event_type)
        .where(AdjustmentCollaborationEvent.collaboration_id == collab_id)
        .order_by(AdjustmentCollaborationEvent.created_at)
    )
    return [row[0] for row in r.all()]


# ─── P1 状态机合法/非法转换 ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p1_state_machine_legal_and_illegal(db_session, pid):
    gid = await _create_manual_group(db_session, pid)
    svc = AdjustmentCollaborationService(db_session)
    c = await svc.assign(pid, entry_group_id=gid, assignee_id=_ASSIGNEE_UID,
                         initiator_id=_INITIATOR, year=2025, note="请补充")
    assert c.status == "pending"
    # 合法：pending → acknowledged
    c = await svc.acknowledge(pid, c.id, _ASSIGNEE_UID)
    assert c.status == "acknowledged"
    # 非法：acknowledged → confirmed（跳过 contributed）
    with pytest.raises(CollaborationError) as ei:
        await svc.confirm(pid, c.id, _ASSIGNEE_UID)
    assert ei.value.code == "INVALID_TRANSITION"


# ─── P2 事件 append-only ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p2_events_append_only(db_session, pid):
    gid = await _create_manual_group(db_session, pid)
    svc = AdjustmentCollaborationService(db_session)
    c = await svc.assign(pid, entry_group_id=gid, assignee_id=_ASSIGNEE_UID,
                         initiator_id=_INITIATOR, year=2025)
    await svc.acknowledge(pid, c.id, _ASSIGNEE_UID)
    await svc.contribute(pid, c.id, _ASSIGNEE_UID, _line_items(), note="已补充")
    await svc.confirm(pid, c.id, _ASSIGNEE_UID)
    evts = await _events(db_session, c.id)
    assert evts == ["assigned", "acknowledged", "contributed", "confirmed"]


# ─── P3 单组活跃唯一 + 多轮 ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p3_single_active_and_multi_round(db_session, pid):
    gid = await _create_manual_group(db_session, pid)
    svc = AdjustmentCollaborationService(db_session)
    await svc.assign(pid, entry_group_id=gid, assignee_id=_ASSIGNEE_UID,
                     initiator_id=_INITIATOR, year=2025)
    # 再次转派 → 重派（仍单条活跃）
    c = await svc.assign(pid, entry_group_id=gid, assignee_id=_ASSIGNEE_UID,
                         initiator_id=_INITIATOR, year=2025)
    active = await db_session.execute(
        sa.select(sa.func.count(AdjustmentCollaboration.id)).where(
            AdjustmentCollaboration.entry_group_id == gid,
            AdjustmentCollaboration.status.in_(["pending", "acknowledged", "contributed"]),
            AdjustmentCollaboration.is_deleted == sa.false(),
        )
    )
    assert (active.scalar() or 0) == 1
    assert c.round == 1
    # 退回后再派 → 新轮 round=2
    await svc.reject(pid, c.id, _INITIATOR, "信息不足")
    c2 = await svc.assign(pid, entry_group_id=gid, assignee_id=_ASSIGNEE_UID,
                          initiator_id=_INITIATOR, year=2025)
    assert c2.round == 2
    # 历史 round1 的事件保留
    assert "rejected" in await _events(db_session, c.id)


# ─── P4 协作锁 ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p4_collaboration_lock(db_session, pid):
    # workpaper-origin 组（经 sync 创建）
    sync = AdjustmentSyncService(db_session)
    req = AdjustmentSyncRequest(
        year=2025, wp_id=_WP_ID, item_id="D4-4-rows", source_wp_code="D4",
        description="收入调整", adjustment_type=AdjustmentType.aje,
        line_items=_line_items(),
    )
    grp = await sync.sync_from_workpaper(pid, req, _INITIATOR)
    await db_session.flush()
    svc = AdjustmentCollaborationService(db_session)
    await svc.assign(pid, entry_group_id=grp.entry_group_id, assignee_id=_ASSIGNEE_UID,
                     initiator_id=_INITIATOR, year=2025)
    # 活跃协作 → 锁
    assert await has_active_collaboration(db_session, pid, grp.entry_group_id) is True
    with pytest.raises(AdjustmentSyncError) as ei:
        await sync.sync_from_workpaper(pid, req, _INITIATOR)
    assert ei.value.code == "COLLABORATION_LOCKED"
    # 确认后释放锁 → sync 恢复
    active = await svc.get_active_by_group(pid, grp.entry_group_id)
    await svc.acknowledge(pid, active.id, _ASSIGNEE_UID)
    await svc.contribute(pid, active.id, _ASSIGNEE_UID, _line_items())
    await svc.confirm(pid, active.id, _ASSIGNEE_UID)
    assert await has_active_collaboration(db_session, pid, grp.entry_group_id) is False
    await sync.sync_from_workpaper(pid, req, _INITIATOR)  # 不再抛


# ─── P5 补充借贷平衡守卫 ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p5_contribute_balance_guard(db_session, pid):
    gid = await _create_manual_group(db_session, pid)
    svc = AdjustmentCollaborationService(db_session)
    c = await svc.assign(pid, entry_group_id=gid, assignee_id=_ASSIGNEE_UID,
                         initiator_id=_INITIATOR, year=2025)
    with pytest.raises(CollaborationError) as ei:
        await svc.contribute(pid, c.id, _ASSIGNEE_UID, _line_items(debit="5000", credit="3000"))
    assert ei.value.code == "UNBALANCED"


# ─── P6 approved 不可协作 ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p6_approved_cannot_collaborate(db_session, pid):
    from app.models.audit_platform_models import Adjustment
    gid = await _create_manual_group(db_session, pid)
    rows = (await db_session.execute(
        sa.select(Adjustment).where(Adjustment.entry_group_id == gid,
                                    Adjustment.is_deleted == sa.false())
    )).scalars().all()
    for r in rows:
        r.review_status = ReviewStatus.approved
    await db_session.flush()
    svc = AdjustmentCollaborationService(db_session)
    with pytest.raises(CollaborationError) as ei:
        await svc.assign(pid, entry_group_id=gid, assignee_id=_ASSIGNEE_UID,
                         initiator_id=_INITIATOR, year=2025)
    assert ei.value.code == "APPROVED_LOCKED"


# ─── P7 通知触发到正确对象 ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p7_notifications(db_session, pid, monkeypatch):
    spy = AsyncMock(return_value={"id": "n"})
    monkeypatch.setattr(collab_mod.NotificationService, "send_notification", spy)
    gid = await _create_manual_group(db_session, pid)
    svc = AdjustmentCollaborationService(db_session)
    c = await svc.assign(pid, entry_group_id=gid, assignee_id=_ASSIGNEE_UID,
                         initiator_id=_INITIATOR, year=2025)
    # 转派 → 通知 assignee
    assert spy.await_count == 1
    assert spy.await_args.kwargs["user_id"] == _ASSIGNEE_UID
    await svc.acknowledge(pid, c.id, _ASSIGNEE_UID)
    await svc.contribute(pid, c.id, _ASSIGNEE_UID, _line_items())
    # 补充 → 通知 initiator
    assert spy.await_args.kwargs["user_id"] == _INITIATOR
    await svc.confirm(pid, c.id, _ASSIGNEE_UID)
    # 确认 → 通知 initiator
    assert spy.await_args.kwargs["user_id"] == _INITIATOR


# ─── P12 权限守卫 ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p12_not_project_member(db_session, pid):
    gid = await _create_manual_group(db_session, pid)
    svc = AdjustmentCollaborationService(db_session)
    with pytest.raises(CollaborationError) as ei:
        await svc.assign(pid, entry_group_id=gid, assignee_id=_NON_MEMBER,
                         initiator_id=_INITIATOR, year=2025)
    assert ei.value.code == "NOT_PROJECT_MEMBER"


@pytest.mark.asyncio
async def test_p12_not_assignee(db_session, pid):
    gid = await _create_manual_group(db_session, pid)
    svc = AdjustmentCollaborationService(db_session)
    c = await svc.assign(pid, entry_group_id=gid, assignee_id=_ASSIGNEE_UID,
                         initiator_id=_INITIATOR, year=2025)
    # 非被指派人 acknowledge → NOT_ASSIGNEE
    with pytest.raises(CollaborationError) as ei:
        await svc.acknowledge(pid, c.id, _INITIATOR)
    assert ei.value.code == "NOT_ASSIGNEE"


@pytest.mark.asyncio
async def test_p12_reject_not_participant(db_session, pid):
    gid = await _create_manual_group(db_session, pid)
    svc = AdjustmentCollaborationService(db_session)
    c = await svc.assign(pid, entry_group_id=gid, assignee_id=_ASSIGNEE_UID,
                         initiator_id=_INITIATOR, year=2025)
    with pytest.raises(CollaborationError) as ei:
        await svc.reject(pid, c.id, _NON_MEMBER, "无关人退回")
    assert ei.value.code == "NOT_PARTICIPANT"


# ─── 转派可传 staff_id（picker）→ 解析为 user_id ─────────────────────────────
@pytest.mark.asyncio
async def test_assign_accepts_staff_id(db_session, pid):
    gid = await _create_manual_group(db_session, pid)
    svc = AdjustmentCollaborationService(db_session)
    c = await svc.assign(pid, entry_group_id=gid, assignee_id=_STAFF_ID,
                         initiator_id=_INITIATOR, year=2025)
    # staff_id 解析为其 user_id
    assert c.assignee_id == _ASSIGNEE_UID
