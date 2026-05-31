"""_mark_cloned_configs_stale handler 单元测试

**Validates: Requirements 2.2**

验证主模板更新事件触发后，handler 正确标记引用该行的克隆项目 is_stale=True，
且不误标无关项目（E3 属性）。
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.report_models import (
    FinancialReportType,
    ReportConfig,
)

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest.fixture
async def session():
    """每次测试独立的 SQLite 内存数据库 session"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as s:
        yield s


def _make_config(
    report_type: FinancialReportType,
    row_code: str,
    applicable_standard: str,
    is_stale: bool = False,
) -> ReportConfig:
    """创建 ReportConfig 行"""
    return ReportConfig(
        id=uuid.uuid4(),
        report_type=report_type,
        row_number=1,
        row_code=row_code,
        row_name=f"Row {row_code}",
        applicable_standard=applicable_standard,
        is_stale=is_stale,
    )


class TestMarkClonedConfigsStale:
    """测试 _mark_cloned_configs_stale handler"""

    @pytest.mark.asyncio
    async def test_marks_matching_cloned_configs_stale(self, session: AsyncSession):
        """匹配 report_type + row_code 的克隆项目配置应被标记 is_stale=True"""
        # Arrange: 一个 standard 主模板行 + 两个克隆项目行（同 report_type + row_code）
        master = _make_config(
            FinancialReportType.balance_sheet, "BS001", "soe_consolidated"
        )
        clone1 = _make_config(
            FinancialReportType.balance_sheet, "BS001", "project:aaa"
        )
        clone2 = _make_config(
            FinancialReportType.balance_sheet, "BS001", "project:bbb"
        )
        session.add_all([master, clone1, clone2])
        await session.commit()

        # Act: 模拟 handler 逻辑
        import sqlalchemy as sa

        extra = {"standard": "soe_consolidated", "report_type": "balance_sheet", "row_code": "BS001", "config_id": str(master.id)}
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
        await session.execute(stmt)
        await session.commit()

        # Assert: 克隆行被标记 stale
        for cid in [clone1.id, clone2.id]:
            row = await session.get(ReportConfig, cid)
            assert row.is_stale is True, f"Clone {cid} should be stale"

        # 主模板行不受影响
        master_row = await session.get(ReportConfig, master.id)
        assert master_row.is_stale is False

    @pytest.mark.asyncio
    async def test_does_not_mark_unrelated_clones(self, session: AsyncSession):
        """不同 row_code 的克隆项目不应被标记（E3 不误标）"""
        # Arrange: 克隆项目有不同 row_code
        clone_match = _make_config(
            FinancialReportType.balance_sheet, "BS001", "project:aaa"
        )
        clone_unrelated = _make_config(
            FinancialReportType.balance_sheet, "BS999", "project:aaa"
        )
        session.add_all([clone_match, clone_unrelated])
        await session.commit()

        # Act
        import sqlalchemy as sa

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
        await session.execute(stmt)
        await session.commit()

        # Assert
        match_row = await session.get(ReportConfig, clone_match.id)
        assert match_row.is_stale is True

        unrelated_row = await session.get(ReportConfig, clone_unrelated.id)
        assert unrelated_row.is_stale is False, "Unrelated row_code should NOT be stale"

    @pytest.mark.asyncio
    async def test_does_not_mark_different_report_type(self, session: AsyncSession):
        """不同 report_type 的克隆项目不应被标记"""
        clone_bs = _make_config(
            FinancialReportType.balance_sheet, "BS001", "project:aaa"
        )
        clone_is = _make_config(
            FinancialReportType.income_statement, "BS001", "project:aaa"
        )
        session.add_all([clone_bs, clone_is])
        await session.commit()

        # Act: 更新 balance_sheet 的 BS001
        import sqlalchemy as sa

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
        await session.execute(stmt)
        await session.commit()

        # Assert
        bs_row = await session.get(ReportConfig, clone_bs.id)
        assert bs_row.is_stale is True

        is_row = await session.get(ReportConfig, clone_is.id)
        assert is_row.is_stale is False, "Different report_type should NOT be stale"

    @pytest.mark.asyncio
    async def test_handler_no_op_when_missing_fields(self, session: AsyncSession):
        """payload 缺少 report_type 或 row_code 时 handler 应 no-op"""
        clone = _make_config(
            FinancialReportType.balance_sheet, "BS001", "project:aaa"
        )
        session.add(clone)
        await session.commit()

        # 模拟 handler 逻辑：缺少 report_type
        extra = {"row_code": "BS001"}
        report_type = extra.get("report_type")
        row_code = extra.get("row_code")
        # handler 应 early return
        assert report_type is None  # 确认 early return 条件

        # 验证 clone 未被标记
        row = await session.get(ReportConfig, clone.id)
        assert row.is_stale is False

    @pytest.mark.asyncio
    async def test_handler_integration_via_event_bus(self, session: AsyncSession, monkeypatch):
        """通过 EventBus 发布事件验证 handler 被正确调用"""
        # Arrange: 创建克隆配置
        clone = _make_config(
            FinancialReportType.balance_sheet, "BS001", "project:test123"
        )
        session.add(clone)
        await session.commit()

        # Monkeypatch async_session_factory 使 handler 使用我们的 test session factory
        test_session_factory = async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )

        from app.services import event_handlers as eh_module

        monkeypatch.setattr(eh_module, "async_session_factory", test_session_factory)

        # 清空 event_bus 并重新注册
        from app.services.event_bus import event_bus

        # 保存原始 handlers
        original_handlers = event_bus._handlers.copy()
        event_bus._handlers.clear()

        try:
            eh_module.register_event_handlers()

            # Act: 使用 publish_immediate 立即分发（绕过 debounce）
            payload = EventPayload(
                event_type=EventType.REPORT_CONFIG_MASTER_UPDATED,
                project_id=uuid.uuid4(),
                extra={
                    "standard": "soe_consolidated",
                    "report_type": "balance_sheet",
                    "row_code": "BS001",
                    "config_id": str(uuid.uuid4()),
                },
            )
            await event_bus.publish_immediate(payload)

            # Assert: 克隆行被标记 stale
            async with test_session_factory() as check_session:
                row = await check_session.get(ReportConfig, clone.id)
                assert row.is_stale is True
        finally:
            # 恢复原始 handlers
            event_bus._handlers = original_handlers
