"""工时批量审批单元测试 — Round 2 需求 7

测试覆盖：
1. 正常批准流转 confirmed → approved
2. 正常退回流转 confirmed → draft
3. SOD 守卫：审批人不能审批自己的工时
4. 幂等性：相同 idempotency_key 返回相同结果
5. 状态校验：非 confirmed 状态不可审批
6. 记录不存在时返回 failed
"""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio

from app.services.workhour_approve_service import WorkHourApproveService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeWorkHour:
    """模拟 WorkHour ORM 对象"""

    def __init__(self, id, staff_id, status="confirmed", work_date=None, hours=8.0):
        self.id = id
        self.staff_id = staff_id
        self.status = status
        self.work_date = work_date or date(2026, 5, 1)
        self.hours = Decimal(str(hours))
        self.is_deleted = False


class FakeResult:
    """模拟 SQLAlchemy 查询结果"""

    def __init__(self, records):
        self._records = records

    def scalars(self):
        return self

    def all(self):
        return self._records


class FakeScalarResult:
    """模拟 scalar_one_or_none 结果"""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value


@pytest.fixture
def service():
    return WorkHourApproveService()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_approve_success(service):
    """正常批准：confirmed → approved，发通知"""
    staff_id = uuid.uuid4()
    approver_user_id = uuid.uuid4()
    approver_staff_id = uuid.uuid4()  # 不同于 staff_id
    staff_user_id = uuid.uuid4()

    wh1 = FakeWorkHour(id=uuid.uuid4(), staff_id=staff_id)
    wh2 = FakeWorkHour(id=uuid.uuid4(), staff_id=staff_id)

    db = AsyncMock()

    # 模拟查询：
    # 1. _get_staff_id → scalar_one_or_none
    # 2. WorkHour 列表 → scalars().all()
    # 3+ _get_user_id_by_staff → scalar_one_or_none
    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            # 查询审批人 staff_id
            return FakeScalarResult(approver_staff_id)
        elif call_count[0] == 2:
            # 查询 WorkHour 列表
            return FakeResult([wh1, wh2])
        else:
            # 查询员工 user_id（发通知用）
            return FakeScalarResult(staff_user_id)

    db.execute = mock_execute
    db.commit = AsyncMock()

    with patch(
        "app.services.workhour_approve_service.NotificationService"
    ) as MockNotifService:
        mock_notif = AsyncMock()
        mock_notif.send_notification = AsyncMock(return_value={"id": "notif-1"})
        MockNotifService.return_value = mock_notif

        result = await service.batch_approve(
            db=db,
            hour_ids=[wh1.id, wh2.id],
            action="approve",
            approver_user_id=approver_user_id,
        )

    assert result["approved_count"] == 2
    assert result["rejected_count"] == 0
    assert result["failed"] == []
    assert wh1.status == "approved"
    assert wh2.status == "approved"


@pytest.mark.asyncio
async def test_batch_reject_success(service):
    """正常退回：confirmed → draft，附原因"""
    staff_id = uuid.uuid4()
    approver_user_id = uuid.uuid4()
    approver_staff_id = uuid.uuid4()
    staff_user_id = uuid.uuid4()

    wh1 = FakeWorkHour(id=uuid.uuid4(), staff_id=staff_id)

    db = AsyncMock()
    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            # 审批人 staff_id
            return FakeScalarResult(approver_staff_id)
        elif call_count[0] == 2:
            # WorkHour 列表
            return FakeResult([wh1])
        else:
            # 员工 user_id
            return FakeScalarResult(staff_user_id)

    db.execute = mock_execute
    db.commit = AsyncMock()

    with patch(
        "app.services.workhour_approve_service.NotificationService"
    ) as MockNotifService:
        mock_notif = AsyncMock()
        mock_notif.send_notification = AsyncMock(return_value={"id": "notif-1"})
        MockNotifService.return_value = mock_notif

        result = await service.batch_approve(
            db=db,
            hour_ids=[wh1.id],
            action="reject",
            approver_user_id=approver_user_id,
            reason="工时描述不清晰",
        )

    assert result["approved_count"] == 0
    assert result["rejected_count"] == 1
    assert result["failed"] == []
    assert wh1.status == "draft"


@pytest.mark.asyncio
async def test_sod_guard_self_approve_blocked(service):
    """SOD 守卫：审批人不能审批自己的工时"""
    same_staff_id = uuid.uuid4()
    approver_user_id = uuid.uuid4()

    wh1 = FakeWorkHour(id=uuid.uuid4(), staff_id=same_staff_id)

    db = AsyncMock()
    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            # 审批人的 staff_id 与工时记录的 staff_id 相同
            return FakeScalarResult(same_staff_id)
        elif call_count[0] == 2:
            # WorkHour 列表
            return FakeResult([wh1])
        else:
            return FakeScalarResult(None)

    db.execute = mock_execute
    db.commit = AsyncMock()

    with patch(
        "app.services.workhour_approve_service.NotificationService"
    ) as MockNotifService:
        mock_notif = AsyncMock()
        MockNotifService.return_value = mock_notif

        result = await service.batch_approve(
            db=db,
            hour_ids=[wh1.id],
            action="approve",
            approver_user_id=approver_user_id,
        )

    assert result["approved_count"] == 0
    assert result["rejected_count"] == 0
    assert len(result["failed"]) == 1
    assert "SOD" in result["failed"][0]["reason"]
    # 状态未变
    assert wh1.status == "confirmed"


@pytest.mark.asyncio
async def test_wrong_status_rejected(service):
    """非 confirmed 状态不可审批"""
    staff_id = uuid.uuid4()
    approver_user_id = uuid.uuid4()
    approver_staff_id = uuid.uuid4()

    wh_draft = FakeWorkHour(id=uuid.uuid4(), staff_id=staff_id, status="draft")
    wh_approved = FakeWorkHour(id=uuid.uuid4(), staff_id=staff_id, status="approved")

    db = AsyncMock()
    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            # 审批人 staff_id
            return FakeScalarResult(approver_staff_id)
        elif call_count[0] == 2:
            # WorkHour 列表
            return FakeResult([wh_draft, wh_approved])
        else:
            return FakeScalarResult(None)

    db.execute = mock_execute
    db.commit = AsyncMock()

    with patch(
        "app.services.workhour_approve_service.NotificationService"
    ) as MockNotifService:
        mock_notif = AsyncMock()
        MockNotifService.return_value = mock_notif

        result = await service.batch_approve(
            db=db,
            hour_ids=[wh_draft.id, wh_approved.id],
            action="approve",
            approver_user_id=approver_user_id,
        )

    assert result["approved_count"] == 0
    assert result["rejected_count"] == 0
    assert len(result["failed"]) == 2
    assert "draft" in result["failed"][0]["reason"]
    assert "approved" in result["failed"][1]["reason"]


@pytest.mark.asyncio
async def test_record_not_found(service):
    """记录不存在时返回 failed"""
    approver_user_id = uuid.uuid4()
    approver_staff_id = uuid.uuid4()
    missing_id = uuid.uuid4()

    db = AsyncMock()
    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            # 审批人 staff_id
            return FakeScalarResult(approver_staff_id)
        elif call_count[0] == 2:
            # WorkHour 列表 — 没有找到任何记录
            return FakeResult([])
        else:
            return FakeScalarResult(None)

    db.execute = mock_execute
    db.commit = AsyncMock()

    with patch(
        "app.services.workhour_approve_service.NotificationService"
    ) as MockNotifService:
        mock_notif = AsyncMock()
        MockNotifService.return_value = mock_notif

        result = await service.batch_approve(
            db=db,
            hour_ids=[missing_id],
            action="approve",
            approver_user_id=approver_user_id,
        )

    assert result["approved_count"] == 0
    assert len(result["failed"]) == 1
    assert "不存在" in result["failed"][0]["reason"]


@pytest.mark.asyncio
async def test_idempotency_returns_cached(service):
    """幂等性：相同 key 返回缓存结果"""
    cached_result = {"approved_count": 3, "rejected_count": 0, "failed": []}

    with patch.object(
        service, "_check_idempotency", return_value=cached_result
    ):
        db = AsyncMock()
        result = await service.batch_approve(
            db=db,
            hour_ids=[uuid.uuid4()],
            action="approve",
            approver_user_id=uuid.uuid4(),
            idempotency_key="test-key-123",
        )

    assert result == cached_result
    # db.execute 不应被调用（幂等命中直接返回）
    db.execute.assert_not_called()
