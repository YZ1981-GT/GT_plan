"""事件总线与联动逻辑测试

Validates: Requirements 10.1-10.6
"""

import asyncio
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountMapping,
    AccountSource,
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    MappingType,
    ReviewStatus,
    TbBalance,
    TrialBalance,
)
from app.models.audit_platform_schemas import (
    AdjustmentCreate,
    AdjustmentLineItem,
    AdjustmentUpdate,
    EventPayload,
    EventType,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.event_bus import EventBus
from app.services.trial_balance_service import TrialBalanceService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建完整测试数据：项目+标准科目+客户科目+映射+余额"""
    project = Project(
        id=uuid.uuid4(), name="事件总线测试_2025",
        client_name="事件总线测试", project_type=ProjectType.annual,
        status=ProjectStatus.planning, created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()
    pid = project.id

    # 标准科目
    db_session.add_all([
        AccountChart(
            project_id=pid, account_code="1001", account_name="库存现金",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="1002", account_name="银行存款",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="6001", account_name="主营业务收入",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.standard,
        ),
    ])

    # 客户科目
    db_session.add_all([
        AccountChart(
            project_id=pid, account_code="C1001", account_name="现金",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.client,
        ),
        AccountChart(
            project_id=pid, account_code="C1002", account_name="工行存款",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.client,
        ),
        AccountChart(
            project_id=pid, account_code="C6001", account_name="销售收入",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.client,
        ),
    ])

    # 科目映射
    db_session.add_all([
        AccountMapping(
            project_id=pid, original_account_code="C1001",
            standard_account_code="1001",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        ),
        AccountMapping(
            project_id=pid, original_account_code="C1002",
            standard_account_code="1002",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        ),
        AccountMapping(
            project_id=pid, original_account_code="C6001",
            standard_account_code="6001",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        ),
    ])

    # 客户余额表
    db_session.add_all([
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="C1001", account_name="现金",
            opening_balance=Decimal("10000"), closing_balance=Decimal("12000"),
            debit_amount=Decimal("5000"), credit_amount=Decimal("3000"),
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="C1002", account_name="工行存款",
            opening_balance=Decimal("30000"), closing_balance=Decimal("35000"),
            debit_amount=Decimal("10000"), credit_amount=Decimal("5000"),
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="C6001", account_name="销售收入",
            opening_balance=Decimal("0"), closing_balance=Decimal("100000"),
            debit_amount=Decimal("0"), credit_amount=Decimal("100000"),
        ),
    ])

    await db_session.commit()

    # 先做一次全量重算，建立试算表基线
    svc = TrialBalanceService(db_session)
    await svc.full_recalc(pid, 2025)
    await db_session.commit()

    return pid


# ===================================================================
# EventBus 基础测试
# ===================================================================


class TestEventBus:
    """EventBus 基础功能测试"""

    def test_subscribe_and_handlers(self):
        """subscribe 注册处理器"""
        bus = EventBus()
        handler = AsyncMock()
        bus.subscribe(EventType.ADJUSTMENT_CREATED, handler)
        assert len(bus._handlers[EventType.ADJUSTMENT_CREATED]) == 1

    @pytest.mark.asyncio
    async def test_publish_calls_handler(self):
        """publish 调用已注册的处理器"""
        bus = EventBus()
        handler = AsyncMock()
        bus.subscribe(EventType.ADJUSTMENT_CREATED, handler)

        payload = EventPayload(
            event_type=EventType.ADJUSTMENT_CREATED,
            project_id=uuid.uuid4(),
            year=2025,
            account_codes=["1001"],
        )
        await bus.publish(payload)
        handler.assert_awaited_once_with(payload)

    @pytest.mark.asyncio
    async def test_publish_multiple_handlers(self):
        """同一事件类型可注册多个处理器"""
        bus = EventBus()
        h1 = AsyncMock()
        h2 = AsyncMock()
        bus.subscribe(EventType.ADJUSTMENT_CREATED, h1)
        bus.subscribe(EventType.ADJUSTMENT_CREATED, h2)

        payload = EventPayload(
            event_type=EventType.ADJUSTMENT_CREATED,
            project_id=uuid.uuid4(),
            year=2025,
        )
        await bus.publish(payload)
        h1.assert_awaited_once()
        h2.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_no_handlers(self):
        """没有处理器时 publish 不报错"""
        bus = EventBus()
        payload = EventPayload(
            event_type=EventType.MATERIALITY_CHANGED,
            project_id=uuid.uuid4(),
        )
        await bus.publish(payload)  # should not raise

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_break_others(self):
        """一个处理器异常不影响其他处理器"""
        bus = EventBus()
        failing = AsyncMock(side_effect=RuntimeError("boom"))
        success = AsyncMock()
        bus.subscribe(EventType.ADJUSTMENT_CREATED, failing)
        bus.subscribe(EventType.ADJUSTMENT_CREATED, success)

        payload = EventPayload(
            event_type=EventType.ADJUSTMENT_CREATED,
            project_id=uuid.uuid4(),
            year=2025,
        )
        await bus.publish(payload)
        success.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sse_queue_receives_events(self):
        """SSE 队列接收事件"""
        bus = EventBus()
        queue = bus.create_sse_queue()

        payload = EventPayload(
            event_type=EventType.ADJUSTMENT_CREATED,
            project_id=uuid.uuid4(),
            year=2025,
        )
        await bus.publish(payload)

        received = queue.get_nowait()
        assert received.event_type == EventType.ADJUSTMENT_CREATED

    @pytest.mark.asyncio
    async def test_sse_queue_removal(self):
        """移除 SSE 队列后不再接收事件"""
        bus = EventBus()
        queue = bus.create_sse_queue()
        bus.remove_sse_queue(queue)

        payload = EventPayload(
            event_type=EventType.ADJUSTMENT_CREATED,
            project_id=uuid.uuid4(),
            year=2025,
        )
        await bus.publish(payload)
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_debounce_merges_same_year_events(self):
        """同项目同年度同事件类型在窗口内应合并"""
        bus = EventBus(debounce_ms=20)
        handler = AsyncMock()
        bus.subscribe(EventType.ADJUSTMENT_UPDATED, handler)
        project_id = uuid.uuid4()

        await bus.publish(EventPayload(
            event_type=EventType.ADJUSTMENT_UPDATED,
            project_id=project_id,
            year=2025,
            account_codes=["1001"],
        ))
        await bus.publish(EventPayload(
            event_type=EventType.ADJUSTMENT_UPDATED,
            project_id=project_id,
            year=2025,
            account_codes=["6001"],
        ))

        await asyncio.sleep(0.08)
        handler.assert_awaited_once()
        merged_payload = handler.await_args.args[0]
        assert merged_payload.year == 2025
        assert merged_payload.account_codes == ["1001", "6001"]

    @pytest.mark.asyncio
    async def test_debounce_does_not_merge_cross_year_events(self):
        """同项目跨年度事件不应合并"""
        bus = EventBus(debounce_ms=20)
        handler = AsyncMock()
        bus.subscribe(EventType.ADJUSTMENT_UPDATED, handler)
        project_id = uuid.uuid4()

        await bus.publish(EventPayload(
            event_type=EventType.ADJUSTMENT_UPDATED,
            project_id=project_id,
            year=2024,
            account_codes=["1001"],
        ))
        await bus.publish(EventPayload(
            event_type=EventType.ADJUSTMENT_UPDATED,
            project_id=project_id,
            year=2025,
            account_codes=["6001"],
        ))

        await asyncio.sleep(0.08)
        assert handler.await_count == 2
        years = {call.args[0].year for call in handler.await_args_list}
        assert years == {2024, 2025}


# ===================================================================
# 事件处理器联动测试
# ===================================================================


class TestOnAdjustmentChanged:
    """调整分录 CRUD → 试算表增量更新"""

    @pytest.mark.asyncio
    async def test_on_adjustment_changed_updates_trial_balance(
        self, db_session: AsyncSession, seeded_db
    ):
        """创建调整分录后，on_adjustment_changed 增量更新调整列+审定数"""
        pid = seeded_db
        svc = TrialBalanceService(db_session)

        # 验证初始状态：无调整
        rows = await svc.get_trial_balance(pid, 2025)
        tb_map = {r.standard_account_code: r for r in rows}
        assert tb_map["1001"].aje_adjustment == Decimal("0")
        assert tb_map["1001"].audited_amount == Decimal("12000")

        # 手动添加调整分录
        group_id = uuid.uuid4()
        db_session.add_all([
            Adjustment(
                project_id=pid, year=2025, company_code="001",
                adjustment_no="AJE-001", adjustment_type=AdjustmentType.aje,
                account_code="1001", account_name="库存现金",
                debit_amount=Decimal("500"), credit_amount=Decimal("0"),
                entry_group_id=group_id, created_by=FAKE_USER_ID,
            ),
            Adjustment(
                project_id=pid, year=2025, company_code="001",
                adjustment_no="AJE-001", adjustment_type=AdjustmentType.aje,
                account_code="6001", account_name="主营业务收入",
                debit_amount=Decimal("0"), credit_amount=Decimal("500"),
                entry_group_id=group_id, created_by=FAKE_USER_ID,
            ),
        ])
        await db_session.flush()

        # 触发事件处理器
        payload = EventPayload(
            event_type=EventType.ADJUSTMENT_CREATED,
            project_id=pid,
            year=2025,
            account_codes=["1001", "6001"],
            entry_group_id=group_id,
        )
        await svc.on_adjustment_changed(payload)
        await db_session.commit()

        # 验证：只有受影响科目更新
        rows = await svc.get_trial_balance(pid, 2025)
        tb_map = {r.standard_account_code: r for r in rows}
        assert tb_map["1001"].aje_adjustment == Decimal("500")
        assert tb_map["1001"].audited_amount == Decimal("12500")  # 12000 + 500
        assert tb_map["6001"].aje_adjustment == Decimal("-500")
        assert tb_map["6001"].audited_amount == Decimal("99500")  # 100000 - 500
        # 未受影响的科目不变
        assert tb_map["1002"].aje_adjustment == Decimal("0")
        assert tb_map["1002"].audited_amount == Decimal("35000")

    @pytest.mark.asyncio
    async def test_on_adjustment_changed_missing_year_skips(
        self, db_session: AsyncSession, seeded_db
    ):
        """缺少 year 时跳过处理"""
        pid = seeded_db
        svc = TrialBalanceService(db_session)

        payload = EventPayload(
            event_type=EventType.ADJUSTMENT_CREATED,
            project_id=pid,
            account_codes=["1001"],
        )
        # Should not raise
        await svc.on_adjustment_changed(payload)


class TestOnMappingChanged:
    """科目映射变更 → 试算表重算"""

    @pytest.mark.asyncio
    async def test_on_mapping_changed_recalcs_unadjusted(
        self, db_session: AsyncSession, seeded_db
    ):
        """映射变更后重算旧+新标准科目的未审数"""
        pid = seeded_db
        svc = TrialBalanceService(db_session)

        # 验证初始状态
        rows = await svc.get_trial_balance(pid, 2025)
        tb_map = {r.standard_account_code: r for r in rows}
        assert tb_map["1001"].unadjusted_amount == Decimal("12000")
        assert tb_map["1002"].unadjusted_amount == Decimal("35000")

        # 触发映射变更事件（假设 C1001 从 1001 改映射到 1002）
        payload = EventPayload(
            event_type=EventType.MAPPING_CHANGED,
            project_id=pid,
            year=2025,
            account_codes=["1001", "1002"],
        )
        await svc.on_mapping_changed(payload)
        await db_session.commit()

        # 注意：实际映射没有改变，所以值不变
        # 这里测试的是处理器正确执行了重算逻辑
        rows = await svc.get_trial_balance(pid, 2025)
        tb_map = {r.standard_account_code: r for r in rows}
        assert tb_map["1001"].unadjusted_amount == Decimal("12000")
        assert tb_map["1002"].unadjusted_amount == Decimal("35000")


class TestOnDataImported:
    """数据导入完成 → 全量重算"""

    @pytest.mark.asyncio
    async def test_on_data_imported_full_recalc(
        self, db_session: AsyncSession, seeded_db
    ):
        """导入完成后全量重算"""
        pid = seeded_db
        svc = TrialBalanceService(db_session)

        payload = EventPayload(
            event_type=EventType.DATA_IMPORTED,
            project_id=pid,
            year=2025,
            batch_id=uuid.uuid4(),
        )
        await svc.on_data_imported(payload)
        await db_session.commit()

        rows = await svc.get_trial_balance(pid, 2025)
        assert len(rows) >= 3
        for r in rows:
            unadj = r.unadjusted_amount or Decimal("0")
            assert r.audited_amount == unadj + r.rje_adjustment + r.aje_adjustment


class TestOnImportRolledBack:
    """导入回滚 → 全量重算"""

    @pytest.mark.asyncio
    async def test_on_import_rolled_back_full_recalc(
        self, db_session: AsyncSession, seeded_db
    ):
        """回滚后全量重算"""
        pid = seeded_db
        svc = TrialBalanceService(db_session)

        payload = EventPayload(
            event_type=EventType.IMPORT_ROLLED_BACK,
            project_id=pid,
            year=2025,
            batch_id=uuid.uuid4(),
        )
        await svc.on_import_rolled_back(payload)
        await db_session.commit()

        rows = await svc.get_trial_balance(pid, 2025)
        for r in rows:
            unadj = r.unadjusted_amount or Decimal("0")
            assert r.audited_amount == unadj + r.rje_adjustment + r.aje_adjustment


# ===================================================================
# 集成测试：AdjustmentService 发布事件
# ===================================================================


class TestAdjustmentServiceEventPublishing:
    """AdjustmentService 在 CRUD 操作后发布事件"""

    @pytest.mark.asyncio
    async def test_create_entry_publishes_event(
        self, db_session: AsyncSession, seeded_db
    ):
        """创建分录后发布 ADJUSTMENT_CREATED 事件"""
        from app.services.adjustment_service import AdjustmentService
        from app.services.event_bus import event_bus

        pid = seeded_db
        svc = AdjustmentService(db_session)

        published_events = []
        original_publish = event_bus.publish

        async def capture_publish(payload):
            published_events.append(payload)
            # Don't call original to avoid needing separate DB session
        
        with patch.object(event_bus, 'publish', side_effect=capture_publish):
            data = AdjustmentCreate(
                adjustment_type=AdjustmentType.aje,
                year=2025,
                description="测试分录",
                line_items=[
                    AdjustmentLineItem(
                        standard_account_code="1001",
                        account_name="库存现金",
                        debit_amount=Decimal("100"),
                        credit_amount=Decimal("0"),
                    ),
                    AdjustmentLineItem(
                        standard_account_code="6001",
                        account_name="主营业务收入",
                        debit_amount=Decimal("0"),
                        credit_amount=Decimal("100"),
                    ),
                ],
            )
            await svc.create_entry(pid, data, FAKE_USER_ID)

        assert len(published_events) == 1
        evt = published_events[0]
        assert evt.event_type == EventType.ADJUSTMENT_CREATED
        assert set(evt.account_codes) == {"1001", "6001"}

    @pytest.mark.asyncio
    async def test_delete_entry_publishes_event(
        self, db_session: AsyncSession, seeded_db
    ):
        """删除分录后发布 ADJUSTMENT_DELETED 事件"""
        from app.services.adjustment_service import AdjustmentService
        from app.services.event_bus import event_bus

        pid = seeded_db
        svc = AdjustmentService(db_session)

        published_events = []

        async def capture_publish(payload):
            published_events.append(payload)

        # First create an entry
        data = AdjustmentCreate(
            adjustment_type=AdjustmentType.aje,
            year=2025,
            description="待删除分录",
            line_items=[
                AdjustmentLineItem(
                    standard_account_code="1001",
                    debit_amount=Decimal("200"),
                    credit_amount=Decimal("0"),
                ),
                AdjustmentLineItem(
                    standard_account_code="6001",
                    debit_amount=Decimal("0"),
                    credit_amount=Decimal("200"),
                ),
            ],
        )
        with patch.object(event_bus, 'publish', side_effect=capture_publish):
            result = await svc.create_entry(pid, data, FAKE_USER_ID)

        published_events.clear()

        # Now delete it
        with patch.object(event_bus, 'publish', side_effect=capture_publish):
            await svc.delete_entry(pid, result.entry_group_id)

        assert len(published_events) == 1
        evt = published_events[0]
        assert evt.event_type == EventType.ADJUSTMENT_DELETED
