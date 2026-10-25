"""S 类计算型底稿 TB 回写 service 层测试.

覆盖:
- writeback_audited_amount: v2 正数口径 + flush-only
- writeback_batch: 批量回写
- resolve_auto_data: auto_data_source + field_overrides 合并逻辑
- componentType 校验
- s3_policy_change_data resolver 注册

Requirements: 7.1, 7.2, 7.4
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.tb_audited_writer import (
    PublishRowResult,
    PublishRowSkip,
    PublishRowsResult,
)

from app.services.s_estimate_tb_writeback_service import (
    S_ESTIMATE_COMPONENT_TYPES,
    SEstimateTBWritebackService,
    _get_resolver_name,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 常量 / fixture
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_ID = uuid4()
YEAR = 2025


def _published_result(
    account_code: str,
    audited: str,
    previous: str | None = "800",
) -> PublishRowsResult:
    return PublishRowsResult(
        updated_account_codes=[account_code],
        updated_rows=[
            PublishRowResult(
                account_code=account_code,
                audited_amount=Decimal(audited),
                previous_amount=Decimal(previous) if previous is not None else None,
                published_at=datetime.now(timezone.utc),
            )
        ],
    )


def _skipped_result(account_code: str) -> PublishRowsResult:
    return PublishRowsResult(
        skipped=[PublishRowSkip(account_code, "未找到未删除的试算表行")]
    )


@pytest.fixture
def mock_db():
    """创建 mock AsyncSession；统一 writer 的 flush 由其自身测试负责。"""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# 单元测试: componentType 注册
# ═══════════════════════════════════════════════════════════════════════════════


class TestComponentTypeRegistry:
    """S 类 componentType 注册完整性"""

    def test_four_types_registered(self):
        """4 个 S 类 componentType 在支持集合中."""
        assert "s3-policy-change" in S_ESTIMATE_COMPONENT_TYPES
        assert "s15-eps-roe" in S_ESTIMATE_COMPONENT_TYPES
        assert "s20-revenue-deduction" in S_ESTIMATE_COMPONENT_TYPES
        assert "s21-data-asset" in S_ESTIMATE_COMPONENT_TYPES
        assert len(S_ESTIMATE_COMPONENT_TYPES) == 4

    def test_resolver_name_mapping(self):
        """各 componentType 对应正确的 resolver 名称."""
        assert _get_resolver_name("s15-eps-roe") == "eps_data_from_tb"
        assert _get_resolver_name("s20-revenue-deduction") == "revenue_audited_for_s20"
        assert _get_resolver_name("s3-policy-change") == "s3_policy_change_data"
        assert _get_resolver_name("s21-data-asset") is None  # 独立计算

    def test_unknown_type_returns_none(self):
        """未知 componentType 返回 None."""
        assert _get_resolver_name("unknown-type") is None


# ═══════════════════════════════════════════════════════════════════════════════
# 单元测试: writeback_audited_amount
# ═══════════════════════════════════════════════════════════════════════════════


class TestWritebackAuditedAmount:
    """审定金额回写测试"""

    @pytest.mark.asyncio
    async def test_writeback_v2_positive(self, mock_db):
        """v2 正数口径：统一 writer 收到正数并返回旧值."""
        with patch(
            "app.services.s_estimate_tb_writeback_service.publish_rows",
            new=AsyncMock(return_value=_published_result("6001", "1500.5")),
        ) as mock_publish:
            svc = SEstimateTBWritebackService(mock_db)
            result = await svc.writeback_audited_amount(
                project_id=PROJECT_ID,
                year=YEAR,
                account_code="6001",
                audited_amount=1500.50,
                component_type="s20-revenue-deduction",
            )

        mock_publish.assert_awaited_once()
        assert mock_publish.call_args.args[:3] == (mock_db, PROJECT_ID, YEAR)
        assert mock_publish.call_args.args[3] == [
            {"account_code": "6001", "audited_amount": 1500.5}
        ]
        assert mock_publish.call_args.kwargs == {
            "source": "s-estimate:s20-revenue-deduction"
        }
        assert result == {
            "account_code": "6001",
            "audited_amount": "1500.5",
            "previous_amount": "800",
        }
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_writeback_negative_converts_to_positive(self, mock_db):
        """负数输入交给统一 writer 前自动取绝对值."""
        with patch(
            "app.services.s_estimate_tb_writeback_service.publish_rows",
            new=AsyncMock(return_value=_published_result("4001", "500", previous=None)),
        ) as mock_publish:
            svc = SEstimateTBWritebackService(mock_db)
            result = await svc.writeback_audited_amount(
                project_id=PROJECT_ID,
                year=YEAR,
                account_code="4001",
                audited_amount=-500.0,
            )

        assert mock_publish.call_args.args[3] == [
            {"account_code": "4001", "audited_amount": 500.0}
        ]
        assert result["previous_amount"] is None

    @pytest.mark.asyncio
    async def test_writeback_invalid_component_type(self, mock_db):
        """不合法的 componentType 抛 ValueError."""
        svc = SEstimateTBWritebackService(mock_db)

        with pytest.raises(ValueError, match="不属于 S 类"):
            await svc.writeback_audited_amount(
                project_id=PROJECT_ID,
                year=YEAR,
                account_code="6001",
                audited_amount=100,
                component_type="d-form-table",
            )

    @pytest.mark.asyncio
    async def test_writeback_account_not_found(self, mock_db):
        """统一 writer 跳过目标行时转换为 LookupError."""
        with patch(
            "app.services.s_estimate_tb_writeback_service.publish_rows",
            new=AsyncMock(return_value=_skipped_result("9999")),
        ):
            svc = SEstimateTBWritebackService(mock_db)

            with pytest.raises(LookupError, match="未找到科目"):
                await svc.writeback_audited_amount(
                    project_id=PROJECT_ID,
                    year=YEAR,
                    account_code="9999",
                    audited_amount=100,
                )

    @pytest.mark.asyncio
    async def test_flush_not_commit(self, mock_db):
        """service 仅使用统一 writer，不在自身 commit."""
        with patch(
            "app.services.s_estimate_tb_writeback_service.publish_rows",
            new=AsyncMock(return_value=_published_result("6001", "200")),
        ):
            svc = SEstimateTBWritebackService(mock_db)
            await svc.writeback_audited_amount(
                project_id=PROJECT_ID,
                year=YEAR,
                account_code="6001",
                audited_amount=200,
            )

        mock_db.commit.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# 单元测试: writeback_batch
# ═══════════════════════════════════════════════════════════════════════════════


class TestWritebackBatch:
    """批量回写测试"""

    @pytest.mark.asyncio
    async def test_batch_all_success(self, mock_db):
        """批量回写全部成功，逐行调用统一 writer."""
        with patch(
            "app.services.s_estimate_tb_writeback_service.publish_rows",
            new=AsyncMock(
                side_effect=[
                    _published_result("6001", "1500", previous="100"),
                    _published_result("6051", "300", previous="200"),
                ]
            ),
        ) as mock_publish:
            svc = SEstimateTBWritebackService(mock_db)
            results = await svc.writeback_batch(
                project_id=PROJECT_ID,
                year=YEAR,
                rows=[
                    {"account_code": "6001", "audited_amount": 1500},
                    {"account_code": "6051", "audited_amount": 300},
                ],
                component_type="s20-revenue-deduction",
            )

        assert len(results) == 2
        assert all("error" not in item for item in results)
        assert [item["account_code"] for item in results] == ["6001", "6051"]
        assert mock_publish.await_count == 2
        assert mock_publish.call_args_list[0].args[3] == [
            {"account_code": "6001", "audited_amount": 1500.0}
        ]
        assert mock_publish.call_args_list[1].args[3] == [
            {"account_code": "6051", "audited_amount": 300.0}
        ]

    @pytest.mark.asyncio
    async def test_batch_partial_failure(self, mock_db):
        """批量回写部分失败时不中断其他行."""
        with patch(
            "app.services.s_estimate_tb_writeback_service.publish_rows",
            new=AsyncMock(
                side_effect=[
                    _published_result("6001", "1500", previous="100"),
                    _skipped_result("9999"),
                ]
            ),
        ):
            svc = SEstimateTBWritebackService(mock_db)
            results = await svc.writeback_batch(
                project_id=PROJECT_ID,
                year=YEAR,
                rows=[
                    {"account_code": "6001", "audited_amount": 1500},
                    {"account_code": "9999", "audited_amount": 100},
                ],
            )

        assert len(results) == 2
        assert "error" not in results[0]
        assert results[0]["account_code"] == "6001"
        assert "error" in results[1]
        assert "未找到科目" in results[1]["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# 单元测试: resolve_auto_data
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveAutoData:
    """自动取数 + field_overrides 测试"""

    @pytest.mark.asyncio
    async def test_resolver_called_for_s15(self, mock_db):
        """S15 调用 eps_data_from_tb resolver."""
        mock_field_override_svc = MagicMock()
        mock_field_override_svc.get_batch = AsyncMock(return_value={})

        resolver_result = {
            "summary": "净利润 1000, 股本 500",
            "net_profit": 1000,
            "shares_outstanding": 500,
        }

        async def fake_resolver(db, pid, year, source, **kw):
            return resolver_result

        with patch(
            "app.services.auto_data_resolvers.resolve_auto_data_source",
            side_effect=fake_resolver,
        ) as mock_resolver, patch(
            "app.services.s_estimate_tb_writeback_service.FieldOverrideService",
            return_value=mock_field_override_svc,
        ):
            svc = SEstimateTBWritebackService(mock_db)
            result = await svc.resolve_auto_data(
                project_id=PROJECT_ID,
                year=YEAR,
                component_type="s15-eps-roe",
            )

            mock_resolver.assert_awaited_once_with(
                mock_db, PROJECT_ID, YEAR, "eps_data_from_tb",
            )
            assert result["auto_resolved"]["net_profit"] == 1000
            assert result["final"]["net_profit"] == 1000

    @pytest.mark.asyncio
    async def test_field_overrides_take_precedence(self, mock_db):
        """field_overrides 覆盖 resolver 自动值."""
        mock_field_override_svc = MagicMock()
        mock_field_override_svc.get_batch = AsyncMock(return_value={})

        async def fake_resolver(db, pid, year, source, **kw):
            return {
                "summary": "主营 1000, 其他 200",
                "main_revenue": 1000,
                "other_revenue": 200,
                "total_revenue": 1200,
            }

        with patch(
            "app.services.auto_data_resolvers.resolve_auto_data_source",
            side_effect=fake_resolver,
        ), patch(
            "app.services.s_estimate_tb_writeback_service.FieldOverrideService",
            return_value=mock_field_override_svc,
        ):
            svc = SEstimateTBWritebackService(mock_db)
            result = await svc.resolve_auto_data(
                project_id=PROJECT_ID,
                year=YEAR,
                component_type="s20-revenue-deduction",
                field_overrides={"main_revenue": 1500},
            )

            # field_overrides 覆盖了 resolver 的值
            assert result["final"]["main_revenue"] == 1500
            # 未覆盖的保留 resolver 值
            assert result["final"]["other_revenue"] == 200
            assert result["overrides_applied"]["main_revenue"] == 1500

    @pytest.mark.asyncio
    async def test_s21_no_resolver(self, mock_db):
        """S21 无 resolver，resolve_auto_data 返回空 auto_resolved."""
        mock_field_override_svc = MagicMock()
        mock_field_override_svc.get_batch = AsyncMock(return_value={})

        with patch(
            "app.services.auto_data_resolvers.resolve_auto_data_source",
            side_effect=AsyncMock(return_value=None),
        ) as mock_resolver, patch(
            "app.services.s_estimate_tb_writeback_service.FieldOverrideService",
            return_value=mock_field_override_svc,
        ):
            svc = SEstimateTBWritebackService(mock_db)
            result = await svc.resolve_auto_data(
                project_id=PROJECT_ID,
                year=YEAR,
                component_type="s21-data-asset",
            )

            # S21 resolver_name 为 None，不会调用 resolver
            mock_resolver.assert_not_awaited()
            assert result["auto_resolved"] == {}
            assert result["final"] == {}

    @pytest.mark.asyncio
    async def test_invalid_component_type_raises(self, mock_db):
        """不支持的 componentType 抛 ValueError."""
        svc = SEstimateTBWritebackService(mock_db)

        with pytest.raises(ValueError, match="不支持的 componentType"):
            await svc.resolve_auto_data(
                project_id=PROJECT_ID,
                year=YEAR,
                component_type="invalid-type",
            )

    @pytest.mark.asyncio
    async def test_persisted_overrides_applied(self, mock_db):
        """持久化 field_overrides 应用到结果."""
        mock_field_override_svc = MagicMock()
        mock_field_override_svc.get_batch = AsyncMock(return_value={
            "item1": {"net_profit": "2000", "custom_field": "hello"},
        })

        async def fake_resolver(db, pid, year, source, **kw):
            return {
                "summary": "净利润 1000",
                "net_profit": 1000,
            }

        with patch(
            "app.services.auto_data_resolvers.resolve_auto_data_source",
            side_effect=fake_resolver,
        ), patch(
            "app.services.s_estimate_tb_writeback_service.FieldOverrideService",
            return_value=mock_field_override_svc,
        ):
            svc = SEstimateTBWritebackService(mock_db)
            result = await svc.resolve_auto_data(
                project_id=PROJECT_ID,
                year=YEAR,
                component_type="s15-eps-roe",
            )

            # 持久化覆盖
            assert result["final"]["net_profit"] == "2000"
            assert result["final"]["custom_field"] == "hello"


# ═══════════════════════════════════════════════════════════════════════════════
# 集成测试: resolver 注册
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolverRegistration:
    """验证 S 类 resolver 已正确注册"""

    def test_s3_policy_change_data_registered(self):
        """s3_policy_change_data 已注册到 auto_data_resolvers."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "s3_policy_change_data" in sources

    def test_eps_data_from_tb_registered(self):
        """eps_data_from_tb 已注册到 auto_data_resolvers."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "eps_data_from_tb" in sources

    def test_revenue_audited_for_s20_registered(self):
        """revenue_audited_for_s20 已注册到 auto_data_resolvers."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "revenue_audited_for_s20" in sources

    def test_non_recurring_items_still_registered(self):
        """non_recurring_items_from_tb 依然注册（确认没破坏）."""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "non_recurring_items_from_tb" in sources


# ═══════════════════════════════════════════════════════════════════════════════
# 集成测试: router endpoints 可达
# ═══════════════════════════════════════════════════════════════════════════════


class TestRouterEndpoints:
    """验证 router endpoint 正确注册"""

    def test_router_prefix(self):
        """router prefix 为 /api/s-estimate."""
        from app.routers.s_estimate_calculation import router
        assert router.prefix == "/api/s-estimate"

    def test_tb_writeback_endpoint_exists(self):
        """tb-writeback 端点已注册."""
        from app.routers.s_estimate_calculation import router
        routes = [r.path for r in router.routes]
        assert any("tb-writeback" in r and "batch" not in r for r in routes)

    def test_tb_writeback_batch_endpoint_exists(self):
        """tb-writeback-batch 端点已注册."""
        from app.routers.s_estimate_calculation import router
        routes = [r.path for r in router.routes]
        assert any("tb-writeback-batch" in r for r in routes)

    def test_auto_data_endpoint_exists(self):
        """auto-data 端点已注册."""
        from app.routers.s_estimate_calculation import router
        routes = [r.path for r in router.routes]
        assert any("auto-data" in r for r in routes)


# ═══════════════════════════════════════════════════════════════════════════════
# WORKPAPER_SAVED 事件发布测试 (Req 7.3, Task 5.2)
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkpaperSavedEventPublish:
    """验证 TB 回写成功后发布 WORKPAPER_SAVED 事件."""

    def test_router_imports_event_bus(self):
        """router 中 WORKPAPER_SAVED 发布代码引用正确的模块."""
        import inspect
        from app.routers.s_estimate_calculation import s_estimate_tb_writeback
        source = inspect.getsource(s_estimate_tb_writeback)
        assert "EventType.WORKPAPER_SAVED" in source
        assert "event_bus.publish" in source
        assert "s_estimate_tb_writeback" in source

    def test_batch_router_publishes_workpaper_saved(self):
        """批量回写 router 中包含 WORKPAPER_SAVED 发布."""
        import inspect
        from app.routers.s_estimate_calculation import s_estimate_tb_writeback_batch
        source = inspect.getsource(s_estimate_tb_writeback_batch)
        assert "EventType.WORKPAPER_SAVED" in source
        assert "event_bus.publish" in source
        assert "s_estimate_tb_writeback_batch" in source

    def test_single_writeback_payload_has_required_fields(self):
        """单科目回写 payload 包含 wp_id, wp_code, trigger, account_code."""
        import inspect
        from app.routers.s_estimate_calculation import s_estimate_tb_writeback
        source = inspect.getsource(s_estimate_tb_writeback)
        assert '"wp_id"' in source
        assert '"wp_code"' in source
        assert '"trigger"' in source
        assert '"account_code"' in source
        assert '"audited_amount"' in source

    def test_batch_writeback_publishes_only_on_success(self):
        """批量回写仅在 success_count > 0 时发布事件."""
        import inspect
        from app.routers.s_estimate_calculation import s_estimate_tb_writeback_batch
        source = inspect.getsource(s_estimate_tb_writeback_batch)
        assert "if success_count > 0:" in source
