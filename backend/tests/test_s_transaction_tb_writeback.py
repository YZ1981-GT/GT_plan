"""S 类交易型底稿 TB 回写 service 层测试.

覆盖:
- writeback_audited_amount: v2 正数口径 + flush-only
- writeback_batch: 批量回写
- resolve_auto_data: auto_data_source + field_overrides 合并逻辑
- componentType 校验
- S4/S5/S6/S8/S9/S10 resolver 注册
- WORKPAPER_SAVED 事件发布
- disclosure:note-text-updated 通知端点

Requirements: 9.1, 9.2, 9.3, 9.4
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.s_transaction_tb_writeback_service import (
    S_TRANSACTION_COMPONENT_TYPES,
    STransactionTBWritebackService,
    _get_resolver_name,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 常量 / fixture
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_ID = uuid4()
YEAR = 2025


class FakeTrialBalanceRow:
    """模拟 TrialBalance ORM 行"""

    def __init__(self, code: str, unadj: float = 100.0, aje: float = 0, audited: float | None = None):
        self.standard_account_code = code
        self.unadjusted_amount = Decimal(str(unadj))
        self.aje_adjustment = Decimal(str(aje))
        self.audited_amount = Decimal(str(audited)) if audited is not None else None
        self.is_deleted = False


@pytest.fixture
def mock_db():
    """创建 mock AsyncSession"""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# 单元测试: componentType 注册
# ═══════════════════════════════════════════════════════════════════════════════


class TestComponentTypeRegistry:
    """S 类交易型 componentType 注册完整性"""

    def test_four_component_types_registered(self):
        """4 个 componentType 在支持集合中（含 a-program-console）."""
        assert "s4-nonmonetary-exchange" in S_TRANSACTION_COMPONENT_TYPES
        assert "s5-debt-restructuring" in S_TRANSACTION_COMPONENT_TYPES
        assert "s6-fund-occupation" in S_TRANSACTION_COMPONENT_TYPES
        assert "a-program-console" in S_TRANSACTION_COMPONENT_TYPES

    def test_resolver_name_mapping(self):
        """各 wp_code 对应正确的 resolver 名称."""
        assert _get_resolver_name("S4") == "s4_nonmonetary_exchange_data"
        assert _get_resolver_name("S5") == "s5_debt_restructuring_data"
        assert _get_resolver_name("S6") == "s6_fund_occupation_data"
        assert _get_resolver_name("S8") == "s8_lease_data"
        assert _get_resolver_name("S9") == "s9_ecommerce_data"
        assert _get_resolver_name("S10") == "s10_environment_data"

    def test_unknown_wp_code_returns_none(self):
        """未知 wp_code 返回 None."""
        assert _get_resolver_name("S99") is None
        assert _get_resolver_name("") is None


# ═══════════════════════════════════════════════════════════════════════════════
# 单元测试: writeback_audited_amount
# ═══════════════════════════════════════════════════════════════════════════════


class TestWritebackAuditedAmount:
    """审定金额回写测试"""

    @pytest.mark.asyncio
    async def test_writeback_v2_positive(self, mock_db):
        """v2 正数口径：audited_amount 存储为正数."""
        fake_row = FakeTrialBalanceRow("1601", unadj=5000, audited=4800)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        svc = STransactionTBWritebackService(mock_db)
        result = await svc.writeback_audited_amount(
            project_id=PROJECT_ID,
            year=YEAR,
            account_code="1601",
            audited_amount=5200.50,
            component_type="s4-nonmonetary-exchange",
            wp_code="S4",
        )

        # 验证正数存储
        assert fake_row.audited_amount == Decimal("5200.5")
        assert result["account_code"] == "1601"
        assert result["audited_amount"] == "5200.5"
        assert result["previous_amount"] == "4800"

        # 验证仅 flush 不 commit
        mock_db.flush.assert_awaited_once()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_writeback_negative_converts_to_positive(self, mock_db):
        """负数输入自动取绝对值（v2 正数口径）."""
        fake_row = FakeTrialBalanceRow("2202", audited=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        svc = STransactionTBWritebackService(mock_db)
        result = await svc.writeback_audited_amount(
            project_id=PROJECT_ID,
            year=YEAR,
            account_code="2202",
            audited_amount=-800.0,
            wp_code="S5",
        )

        # 负数转正
        assert fake_row.audited_amount == Decimal("800.0")
        assert result["previous_amount"] is None

    @pytest.mark.asyncio
    async def test_writeback_invalid_component_type(self, mock_db):
        """不合法的 componentType 抛 ValueError."""
        svc = STransactionTBWritebackService(mock_db)

        with pytest.raises(ValueError, match="不属于 S 类交易型"):
            await svc.writeback_audited_amount(
                project_id=PROJECT_ID,
                year=YEAR,
                account_code="1601",
                audited_amount=100,
                component_type="d-form-table",
            )

    @pytest.mark.asyncio
    async def test_writeback_account_not_found(self, mock_db):
        """科目不存在抛 LookupError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        svc = STransactionTBWritebackService(mock_db)

        with pytest.raises(LookupError, match="未找到科目"):
            await svc.writeback_audited_amount(
                project_id=PROJECT_ID,
                year=YEAR,
                account_code="9999",
                audited_amount=100,
            )

    @pytest.mark.asyncio
    async def test_flush_not_commit(self, mock_db):
        """确认 service 层仅 flush 不 commit（Req 9.3）."""
        fake_row = FakeTrialBalanceRow("1901")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        svc = STransactionTBWritebackService(mock_db)
        await svc.writeback_audited_amount(
            project_id=PROJECT_ID,
            year=YEAR,
            account_code="1901",
            audited_amount=200,
            wp_code="S8",
        )

        # 核心断言：flush 被调用，commit 未被调用
        mock_db.flush.assert_awaited_once()
        mock_db.commit.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# 单元测试: writeback_batch
# ═══════════════════════════════════════════════════════════════════════════════


class TestWritebackBatch:
    """批量回写测试"""

    @pytest.mark.asyncio
    async def test_batch_all_success(self, mock_db):
        """批量回写全部成功."""
        fake_rows = {
            "1601": FakeTrialBalanceRow("1601", audited=1000),
            "1701": FakeTrialBalanceRow("1701", audited=2000),
        }

        call_count = [0]

        async def mock_execute(stmt, *args, **kwargs):
            result = MagicMock()
            if call_count[0] < 2:
                code = ["1601", "1701"][call_count[0]]
                result.scalar_one_or_none.return_value = fake_rows[code]
            call_count[0] += 1
            return result

        mock_db.execute = mock_execute

        svc = STransactionTBWritebackService(mock_db)
        results = await svc.writeback_batch(
            project_id=PROJECT_ID,
            year=YEAR,
            rows=[
                {"account_code": "1601", "audited_amount": 1500},
                {"account_code": "1701", "audited_amount": 2500},
            ],
            component_type="s4-nonmonetary-exchange",
            wp_code="S4",
        )

        assert len(results) == 2
        assert all("error" not in r for r in results)

    @pytest.mark.asyncio
    async def test_batch_partial_failure(self, mock_db):
        """批量回写部分失败时不中断其他行."""
        fake_row = FakeTrialBalanceRow("1601", audited=1000)

        call_count = [0]

        async def mock_execute(stmt, *args, **kwargs):
            result = MagicMock()
            if call_count[0] == 0:
                result.scalar_one_or_none.return_value = fake_row
            else:
                result.scalar_one_or_none.return_value = None
            call_count[0] += 1
            return result

        mock_db.execute = mock_execute

        svc = STransactionTBWritebackService(mock_db)
        results = await svc.writeback_batch(
            project_id=PROJECT_ID,
            year=YEAR,
            rows=[
                {"account_code": "1601", "audited_amount": 1500},
                {"account_code": "9999", "audited_amount": 100},
            ],
            wp_code="S4",
        )

        assert len(results) == 2
        assert "error" not in results[0]
        assert "error" in results[1]


# ═══════════════════════════════════════════════════════════════════════════════
# 单元测试: resolve_auto_data
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveAutoData:
    """自动取数 + field_overrides 测试"""

    @pytest.mark.asyncio
    async def test_resolver_called_for_s4(self, mock_db):
        """S4 调用 s4_nonmonetary_exchange_data resolver."""
        mock_field_override_svc = MagicMock()
        mock_field_override_svc.get_batch = AsyncMock(return_value={})

        resolver_result = {
            "summary": "S4非货币性资产: 3个科目",
            "accounts": {"1601": {"audited": 5000}},
            "total_audited": 5000,
        }

        async def fake_resolver(db, pid, year, source, **kw):
            return resolver_result

        with patch(
            "app.services.auto_data_resolvers.resolve_auto_data_source",
            side_effect=fake_resolver,
        ) as mock_resolver, patch(
            "app.services.s_transaction_tb_writeback_service.FieldOverrideService",
            return_value=mock_field_override_svc,
        ):
            svc = STransactionTBWritebackService(mock_db)
            result = await svc.resolve_auto_data(
                project_id=PROJECT_ID,
                year=YEAR,
                wp_code="S4",
            )

            mock_resolver.assert_awaited_once_with(
                mock_db, PROJECT_ID, YEAR, "s4_nonmonetary_exchange_data",
            )
            assert result["auto_resolved"]["total_audited"] == 5000
            assert result["final"]["total_audited"] == 5000

    @pytest.mark.asyncio
    async def test_field_overrides_take_precedence(self, mock_db):
        """field_overrides 覆盖 resolver 自动值."""
        mock_field_override_svc = MagicMock()
        mock_field_override_svc.get_batch = AsyncMock(return_value={})

        async def fake_resolver(db, pid, year, source, **kw):
            return {
                "summary": "S5 债权人/债务人",
                "creditor_total": 1000,
                "debtor_total": 2000,
            }

        with patch(
            "app.services.auto_data_resolvers.resolve_auto_data_source",
            side_effect=fake_resolver,
        ), patch(
            "app.services.s_transaction_tb_writeback_service.FieldOverrideService",
            return_value=mock_field_override_svc,
        ):
            svc = STransactionTBWritebackService(mock_db)
            result = await svc.resolve_auto_data(
                project_id=PROJECT_ID,
                year=YEAR,
                wp_code="S5",
                field_overrides={"creditor_total": 1500},
            )

            # field_overrides 覆盖了 resolver 的值
            assert result["final"]["creditor_total"] == 1500
            # 未覆盖的保留 resolver 值
            assert result["final"]["debtor_total"] == 2000
            assert result["overrides_applied"]["creditor_total"] == 1500

    @pytest.mark.asyncio
    async def test_persisted_overrides_applied(self, mock_db):
        """持久化 field_overrides 应用到结果."""
        mock_field_override_svc = MagicMock()
        mock_field_override_svc.get_batch = AsyncMock(return_value={
            "item1": {"occupation_total": "5000", "custom_field": "override"},
        })

        async def fake_resolver(db, pid, year, source, **kw):
            return {
                "summary": "S6资金占用",
                "occupation_total": 3000,
            }

        with patch(
            "app.services.auto_data_resolvers.resolve_auto_data_source",
            side_effect=fake_resolver,
        ), patch(
            "app.services.s_transaction_tb_writeback_service.FieldOverrideService",
            return_value=mock_field_override_svc,
        ):
            svc = STransactionTBWritebackService(mock_db)
            result = await svc.resolve_auto_data(
                project_id=PROJECT_ID,
                year=YEAR,
                wp_code="S6",
            )

            # 持久化覆盖
            assert result["final"]["occupation_total"] == "5000"
            assert result["final"]["custom_field"] == "override"


# ═══════════════════════════════════════════════════════════════════════════════
# 集成测试: resolver 注册
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolverRegistration:
    """验证 S 类交易型 resolver 已正确注册"""

    def test_s4_resolver_registered(self):
        """s4_nonmonetary_exchange_data 已注册到 auto_data_resolvers."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "s4_nonmonetary_exchange_data" in sources

    def test_s5_resolver_registered(self):
        """s5_debt_restructuring_data 已注册到 auto_data_resolvers."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "s5_debt_restructuring_data" in sources

    def test_s6_resolver_registered(self):
        """s6_fund_occupation_data 已注册到 auto_data_resolvers."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "s6_fund_occupation_data" in sources

    def test_s8_resolver_registered(self):
        """s8_lease_data 已注册到 auto_data_resolvers."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "s8_lease_data" in sources

    def test_s9_resolver_registered(self):
        """s9_ecommerce_data 已注册到 auto_data_resolvers."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "s9_ecommerce_data" in sources

    def test_s10_resolver_registered(self):
        """s10_environment_data 已注册到 auto_data_resolvers."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "s10_environment_data" in sources

    def test_existing_resolvers_not_broken(self):
        """确认现有 resolver 未被破坏."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        # 之前已有的 S 类 resolver
        assert "non_recurring_items_from_tb" in sources
        assert "eps_data_from_tb" in sources
        assert "revenue_audited_for_s20" in sources


# ═══════════════════════════════════════════════════════════════════════════════
# 集成测试: router endpoints 可达
# ═══════════════════════════════════════════════════════════════════════════════


class TestRouterEndpoints:
    """验证 router endpoint 正确注册"""

    def test_router_prefix(self):
        """router prefix 为 /api/s-transaction."""
        from app.routers.s_transaction_calculation import router
        assert router.prefix == "/api/s-transaction"

    def test_tb_writeback_endpoint_exists(self):
        """tb-writeback 端点已注册."""
        from app.routers.s_transaction_calculation import router
        routes = [r.path for r in router.routes]
        assert any("tb-writeback" in r and "batch" not in r for r in routes)

    def test_tb_writeback_batch_endpoint_exists(self):
        """tb-writeback-batch 端点已注册."""
        from app.routers.s_transaction_calculation import router
        routes = [r.path for r in router.routes]
        assert any("tb-writeback-batch" in r for r in routes)

    def test_auto_data_endpoint_exists(self):
        """auto-data 端点已注册."""
        from app.routers.s_transaction_calculation import router
        routes = [r.path for r in router.routes]
        assert any("auto-data" in r for r in routes)

    def test_disclosure_notify_endpoint_exists(self):
        """disclosure-notify 端点已注册（Req 9.4）."""
        from app.routers.s_transaction_calculation import router
        routes = [r.path for r in router.routes]
        assert any("disclosure-notify" in r for r in routes)


# ═══════════════════════════════════════════════════════════════════════════════
# WORKPAPER_SAVED 事件发布测试 (Req 9.3)
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkpaperSavedEventPublish:
    """验证 TB 回写成功后发布 WORKPAPER_SAVED 事件."""

    def test_router_imports_event_bus(self):
        """router 中 WORKPAPER_SAVED 发布代码引用正确的模块."""
        import inspect
        from app.routers.s_transaction_calculation import s_transaction_tb_writeback
        source = inspect.getsource(s_transaction_tb_writeback)
        assert "EventType.WORKPAPER_SAVED" in source
        assert "event_bus.publish" in source
        assert "s_transaction_tb_writeback" in source

    def test_batch_router_publishes_workpaper_saved(self):
        """批量回写 router 中包含 WORKPAPER_SAVED 发布."""
        import inspect
        from app.routers.s_transaction_calculation import s_transaction_tb_writeback_batch
        source = inspect.getsource(s_transaction_tb_writeback_batch)
        assert "EventType.WORKPAPER_SAVED" in source
        assert "event_bus.publish" in source

    def test_batch_writeback_publishes_only_on_success(self):
        """批量回写仅在 success_count > 0 时发布事件."""
        import inspect
        from app.routers.s_transaction_calculation import s_transaction_tb_writeback_batch
        source = inspect.getsource(s_transaction_tb_writeback_batch)
        assert "if success_count > 0:" in source


# ═══════════════════════════════════════════════════════════════════════════════
# disclosure:note-text-updated 通知端点测试 (Req 9.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDisclosureNotify:
    """验证 S4/S5 非经常性损益披露通知端点."""

    def test_disclosure_notify_only_s4_s5(self):
        """disclosure-notify 仅支持 S4/S5."""
        import inspect
        from app.routers.s_transaction_calculation import s_transaction_disclosure_notify
        source = inspect.getsource(s_transaction_disclosure_notify)
        assert '"S4"' in source
        assert '"S5"' in source
        assert "disclosure:note-text-updated" in source

    def test_disclosure_notify_broadcasts_raw(self):
        """disclosure-notify 使用 broadcast_raw 广播 SSE."""
        import inspect
        from app.routers.s_transaction_calculation import s_transaction_disclosure_notify
        source = inspect.getsource(s_transaction_disclosure_notify)
        assert "broadcast_raw" in source
        assert "non_recurring" in source
