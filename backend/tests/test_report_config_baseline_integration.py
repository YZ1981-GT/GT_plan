"""报表配置主模板回填 + 联动 集成测试

**Validates: Requirements 1.2, 2.2**
**Properties: E1, E3**

全链路集成测试覆盖两条完整业务链：
1. 项目优化→提交候选→admin 审核→合并回主模板→其他项目受益
2. 主模板更新→克隆项目 is_stale→banner→选择性同步
"""

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.report_models import (
    FinancialReportType,
    ReportConfig,
    ReportConfigBaseline,
)
from app.services.report_config_service import ReportConfigService

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

STANDARD = "soe_consolidated"
PROJECT_A_ID = uuid.uuid4()
PROJECT_B_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
ADMIN_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每次测试独立的 SQLite 内存数据库 session"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session



def _make_standard_config(row_code: str, formula: str, row_number: int = 1) -> ReportConfig:
    """创建 standard 级配置行"""
    return ReportConfig(
        id=uuid.uuid4(),
        report_type=FinancialReportType.balance_sheet,
        row_number=row_number,
        row_code=row_code,
        row_name=f"Row {row_code}",
        indent_level=0,
        formula=formula,
        applicable_standard=STANDARD,
        is_total_row=False,
    )


def _make_project_config(
    project_id: uuid.UUID, row_code: str, formula: str, row_number: int = 1
) -> ReportConfig:
    """创建项目级配置行（模拟 clone_report_config 后的状态）"""
    return ReportConfig(
        id=uuid.uuid4(),
        report_type=FinancialReportType.balance_sheet,
        row_number=row_number,
        row_code=row_code,
        row_name=f"Row {row_code}",
        indent_level=0,
        formula=formula,
        applicable_standard=f"project:{project_id}",
        is_total_row=False,
    )


# ==================================================================
# Chain 1: 项目优化→提交候选→admin 审核→合并回主模板→其他项目受益
# Validates: Requirements 1.2, Property E1
# ==================================================================


class TestChain1ProjectOptimizeToMasterMerge:
    """全链路 1：项目优化→提交候选→admin 审核→合并回主模板→其他项目受益"""

    @pytest.mark.asyncio
    async def test_full_chain_project_to_master_to_other_projects(
        self, db_session: AsyncSession
    ):
        """
        完整链路：
        1. 创建 standard 配置（主模板）
        2. 克隆到项目 A（模拟 clone_report_config）
        3. 项目 A 修改公式（项目优化）
        4. 项目 A 提交候选（suggest_to_master）
        5. admin 审核通过（review_candidate approved=True）
        6. 验证 standard 主模板已更新
        7. 克隆到项目 B（新项目）
        8. 验证项目 B 获得了更新后的公式
        """
        svc = ReportConfigService(db_session)

        # Step 1: 创建 standard 级配置（主模板）
        master_row = _make_standard_config("BS001", "TB(1001)")
        db_session.add(master_row)
        await db_session.flush()

        # Step 2: 模拟克隆到项目 A
        project_a_row = _make_project_config(PROJECT_A_ID, "BS001", "TB(1001)")
        db_session.add(project_a_row)
        await db_session.flush()

        # Step 3: 项目 A 优化公式（直接修改模拟 update_config）
        project_a_row.formula = "TB(1001)+TB(1002)"
        await db_session.flush()

        # Step 4: 项目 A 提交候选
        candidate_id = await svc.suggest_to_master(
            project_id=PROJECT_A_ID,
            row_code="BS001",
            report_type="balance_sheet",
            standard=STANDARD,
            submitted_by=USER_ID,
        )

        # 验证候选状态为 pending（E1: 受控传播，未审核不合并）
        result = await db_session.execute(
            select(ReportConfigBaseline).where(
                ReportConfigBaseline.id == candidate_id
            )
        )
        candidate = result.scalar_one()
        assert candidate.status == "pending"
        assert candidate.candidate_formula == "TB(1001)+TB(1002)"

        # 验证此时 standard 主模板未变（E1: pending 不合并）
        master_result = await db_session.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == STANDARD,
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == sa.false(),
            )
        )
        master_check = master_result.scalar_one()
        assert master_check.formula == "TB(1001)", "pending 状态不应合并到主模板"

        # Step 5: admin 审核通过
        await svc.review_candidate(
            candidate_id=candidate_id,
            approved=True,
            reviewer=ADMIN_ID,
        )

        # Step 6: 验证 standard 主模板已更新
        master_result2 = await db_session.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == STANDARD,
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == sa.false(),
            )
        )
        master_updated = master_result2.scalar_one()
        assert master_updated.formula == "TB(1001)+TB(1002)", "审核通过后主模板应更新"

        # Step 7: 克隆到项目 B（新项目，使用 clone_report_config）
        project_b_standard = f"project:{PROJECT_B_ID}"
        # 手动模拟 clone（因为 clone_report_config 需要完整 standard 数据）
        clone_b = ReportConfig(
            report_type=FinancialReportType.balance_sheet,
            row_number=master_updated.row_number,
            row_code=master_updated.row_code,
            row_name=master_updated.row_name,
            indent_level=master_updated.indent_level,
            formula=master_updated.formula,
            applicable_standard=project_b_standard,
            is_total_row=master_updated.is_total_row,
        )
        db_session.add(clone_b)
        await db_session.flush()

        # Step 8: 验证项目 B 获得了更新后的公式
        result_b = await db_session.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == project_b_standard,
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == sa.false(),
            )
        )
        project_b_row = result_b.scalar_one()
        assert project_b_row.formula == "TB(1001)+TB(1002)", (
            "新克隆项目应获得更新后的主模板公式"
        )

    @pytest.mark.asyncio
    async def test_rejected_candidate_does_not_propagate(
        self, db_session: AsyncSession
    ):
        """驳回的候选不影响主模板，后续克隆项目不受影响（E1 反面验证）"""
        svc = ReportConfigService(db_session)

        # 创建 standard + 项目 A 克隆
        master_row = _make_standard_config("BS002", "TB(1122)")
        project_a_row = _make_project_config(PROJECT_A_ID, "BS002", "TB(1122)+TB(1123)")
        db_session.add_all([master_row, project_a_row])
        await db_session.flush()

        # 提交候选
        candidate_id = await svc.suggest_to_master(
            project_id=PROJECT_A_ID,
            row_code="BS002",
            report_type="balance_sheet",
            standard=STANDARD,
            candidate_formula="TB(1122)+TB(1123)",
            submitted_by=USER_ID,
        )

        # admin 驳回
        await svc.review_candidate(
            candidate_id=candidate_id,
            approved=False,
            reviewer=ADMIN_ID,
        )

        # 验证主模板未变
        master_result = await db_session.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == STANDARD,
                ReportConfig.row_code == "BS002",
                ReportConfig.is_deleted == sa.false(),
            )
        )
        master_check = master_result.scalar_one()
        assert master_check.formula == "TB(1122)", "驳回后主模板不应变化"


# ==================================================================
# Chain 2: 主模板更新→克隆项目 is_stale→选择性同步
# Validates: Requirements 2.2, Property E3
# ==================================================================


class TestChain2MasterUpdateToStaleSyncFlow:
    """全链路 2：主模板更新→克隆项目 is_stale→选择性同步"""

    @pytest.mark.asyncio
    async def test_full_chain_master_update_stale_and_sync(
        self, db_session: AsyncSession
    ):
        """
        完整链路：
        1. 创建 standard 配置（主模板）
        2. 克隆到项目 A（模拟已有克隆项目）
        3. 更新 standard 配置（模拟 update_config 触发事件）
        4. 模拟 handler 标记克隆项目 is_stale=True
        5. 验证 is_stale=True
        6. 调用 apply_master_update(keep_local=True) 同步
        7. 验证同步完成 + is_stale 清除
        """
        svc = ReportConfigService(db_session)

        # Step 1: 创建 standard 级配置
        master_rows = [
            _make_standard_config("BS001", "TB(1001)", row_number=1),
            _make_standard_config("BS002", "TB(1122)", row_number=2),
        ]
        db_session.add_all(master_rows)
        await db_session.flush()

        # Step 2: 克隆到项目 A
        project_a_rows = [
            _make_project_config(PROJECT_A_ID, "BS001", "TB(1001)+TB(1002)", row_number=1),
            _make_project_config(PROJECT_A_ID, "BS002", "TB(1122)", row_number=2),
        ]
        db_session.add_all(project_a_rows)
        await db_session.flush()

        # Step 3: 更新 standard 配置（模拟 update_config 修改主模板 BS001 公式）
        master_result = await db_session.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == STANDARD,
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == sa.false(),
            )
        )
        master_bs001 = master_result.scalar_one()
        master_bs001.formula = "TB(1001)+TB(1012)"
        await db_session.flush()

        # Step 4: 模拟 _mark_cloned_configs_stale handler 逻辑
        # （集成测试中直接执行 handler 的核心 SQL 逻辑，不依赖 EventBus 异步分发）
        stmt = (
            sa.update(ReportConfig)
            .where(
                ReportConfig.applicable_standard.like("project:%"),
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == sa.false(),
            )
            .where(
                sa.cast(ReportConfig.report_type, sa.String) == "balance_sheet"
            )
            .values(is_stale=True)
        )
        await db_session.execute(stmt)
        await db_session.flush()

        # Step 5: 验证 is_stale=True（仅 BS001 被标记，BS002 不受影响 — E3）
        project_a_standard = f"project:{PROJECT_A_ID}"
        result_all = await db_session.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == project_a_standard,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        project_rows = {r.row_code: r for r in result_all.scalars().all()}

        assert project_rows["BS001"].is_stale is True, "BS001 应被标记 stale"
        assert project_rows["BS002"].is_stale is False, "BS002 不应被误标 stale（E3）"

        # Step 6: 调用 apply_master_update(keep_local=True) 同步
        updated_count = await svc.apply_master_update(
            project_id=PROJECT_A_ID,
            standard=STANDARD,
            keep_local=True,
        )

        # Step 7: 验证同步完成
        # BS001: 项目公式 "TB(1001)+TB(1002)" ≠ 主模板 "TB(1001)+TB(1012)"
        #   → keep_local=True 保留本地覆盖，但 is_stale 清除
        # BS002: 项目公式 "TB(1122)" == 主模板 "TB(1122)" → 同步（无变化但计入 updated）
        result_after = await db_session.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == project_a_standard,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        rows_after = {r.row_code: r for r in result_after.scalars().all()}

        # BS001 保留本地覆盖（keep_local=True）
        assert rows_after["BS001"].formula == "TB(1001)+TB(1002)", (
            "keep_local=True 应保留项目自定义公式"
        )
        # is_stale 已清除
        assert rows_after["BS001"].is_stale is False, "同步后 is_stale 应清除"
        assert rows_after["BS002"].is_stale is False, "同步后 is_stale 应清除"

    @pytest.mark.asyncio
    async def test_stale_only_marks_matching_row(self, db_session: AsyncSession):
        """E3 属性验证：主模板某行更新只标记引用该行的克隆项目，不误标无关行"""
        # 创建 standard 配置（两行）
        master_rows = [
            _make_standard_config("BS001", "TB(1001)", row_number=1),
            _make_standard_config("BS002", "TB(1122)", row_number=2),
        ]
        db_session.add_all(master_rows)
        await db_session.flush()

        # 两个项目各克隆了不同的行
        project_a_bs001 = _make_project_config(PROJECT_A_ID, "BS001", "TB(1001)")
        project_a_bs002 = _make_project_config(PROJECT_A_ID, "BS002", "TB(1122)")
        project_b_bs001 = _make_project_config(PROJECT_B_ID, "BS001", "TB(1001)")
        project_b_bs002 = _make_project_config(PROJECT_B_ID, "BS002", "TB(1122)")
        db_session.add_all([project_a_bs001, project_a_bs002, project_b_bs001, project_b_bs002])
        await db_session.flush()

        # 模拟主模板 BS001 更新 → handler 只标 BS001 的克隆
        stmt = (
            sa.update(ReportConfig)
            .where(
                ReportConfig.applicable_standard.like("project:%"),
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == sa.false(),
            )
            .where(
                sa.cast(ReportConfig.report_type, sa.String) == "balance_sheet"
            )
            .values(is_stale=True)
        )
        await db_session.execute(stmt)
        await db_session.flush()

        # 验证：两个项目的 BS001 都被标记，BS002 不受影响
        for pid in [PROJECT_A_ID, PROJECT_B_ID]:
            result = await db_session.execute(
                select(ReportConfig).where(
                    ReportConfig.applicable_standard == f"project:{pid}",
                    ReportConfig.is_deleted == sa.false(),
                )
            )
            rows = {r.row_code: r for r in result.scalars().all()}
            assert rows["BS001"].is_stale is True, f"Project {pid} BS001 should be stale"
            assert rows["BS002"].is_stale is False, f"Project {pid} BS002 should NOT be stale"

    @pytest.mark.asyncio
    async def test_apply_master_update_keep_local_false_overwrites(
        self, db_session: AsyncSession
    ):
        """keep_local=False 时覆盖项目自定义公式"""
        svc = ReportConfigService(db_session)

        # standard + 项目克隆
        master = _make_standard_config("BS001", "TB(1001)+TB(1012)")
        project_row = _make_project_config(PROJECT_A_ID, "BS001", "TB(1001)+TB(1002)")
        project_row.is_stale = True
        db_session.add_all([master, project_row])
        await db_session.flush()

        # 同步（不保留本地）
        updated = await svc.apply_master_update(
            project_id=PROJECT_A_ID,
            standard=STANDARD,
            keep_local=False,
        )
        assert updated == 1

        # 验证公式被覆盖
        result = await db_session.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == f"project:{PROJECT_A_ID}",
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one()
        assert row.formula == "TB(1001)+TB(1012)", "keep_local=False 应覆盖项目公式"
        assert row.is_stale is False, "同步后 is_stale 应清除"


# ==================================================================
# Chain 2 补充: 真实 EventBus 分发路径（改进点 5）
# 验证 register_event_handlers + publish_immediate 完整链路
# ==================================================================


class TestChain2RealEventBusDispatch:
    """通过真实 EventBus 分发验证 handler 注册 + 触发 + 标记 stale 完整链路"""

    @pytest.mark.asyncio
    async def test_real_event_bus_marks_stale(self, db_session: AsyncSession, monkeypatch):
        """
        真实 EventBus 链路：
        1. 创建克隆项目配置
        2. 注册 event_handlers
        3. publish_immediate REPORT_CONFIG_MASTER_UPDATED
        4. 验证 handler 被触发且 is_stale=True
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker as asm

        # Step 1: 创建克隆项目配置
        clone_row = _make_project_config(PROJECT_A_ID, "BS001", "TB(1001)")
        db_session.add(clone_row)
        await db_session.commit()

        # Step 2: monkeypatch handler 使用的 session factory 指向测试 DB
        test_session_factory = asm(test_engine, class_=AsyncSession, expire_on_commit=False)

        from app.services import event_handlers as eh_module
        monkeypatch.setattr(eh_module, "async_session_factory", test_session_factory)

        # Step 3: 清空 event_bus 并重新注册 handlers
        from app.services.event_bus import event_bus
        original_handlers = event_bus._handlers.copy()
        event_bus._handlers.clear()

        try:
            eh_module.register_event_handlers()

            # Step 4: 通过真实 EventBus 发布事件
            from app.models.audit_platform_schemas import EventPayload, EventType

            payload = EventPayload(
                event_type=EventType.REPORT_CONFIG_MASTER_UPDATED,
                project_id=PROJECT_A_ID,
                extra={
                    "standard": STANDARD,
                    "report_type": "balance_sheet",
                    "row_code": "BS001",
                    "config_id": str(uuid.uuid4()),
                },
            )
            await event_bus.publish_immediate(payload)

            # Step 5: 验证 handler 被触发 → is_stale=True
            async with test_session_factory() as check_session:
                result = await check_session.execute(
                    select(ReportConfig).where(
                        ReportConfig.id == clone_row.id,
                    )
                )
                row = result.scalar_one()
                assert row.is_stale is True, (
                    "真实 EventBus 分发后 handler 应标记 is_stale=True"
                )
        finally:
            event_bus._handlers = original_handlers
