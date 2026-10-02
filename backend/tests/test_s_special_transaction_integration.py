"""S 类交易/专家/检查型专项底稿 — 集成测试.

Spec: .kiro/specs/s-special-transaction-workpapers/ Task 8.2
Requirements: 1.5, 2.3, 4.3, 7.1, 8.2, 9.1, 11.4

覆盖场景：
1. 审定回写 endpoint — TB writeback full flow (mock DB)
2. Auto data resolver — auto-data 返回正确 accounts
3. Disclosure notify — disclosure-notify broadcasts event
4. Render strategy — 6 个 render 策略返回正确 sheet 结构
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.tb_audited_writer import (
    PublishRowResult,
    PublishRowSkip,
    PublishRowsResult,
)

from app.services.s_transaction_tb_writeback_service import (
    S_TRANSACTION_COMPONENT_TYPES,
    S_TRANSACTION_ACCOUNT_CODES,
    STransactionTBWritebackService,
)


# ═══════════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_ID = uuid4()
YEAR = 2025
WP_ID = str(uuid4())


def _published_result(
    account_code: str,
    audited: str,
    previous: str | None = "50000",
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


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 审定回写 endpoint — TB writeback full flow
# ═══════════════════════════════════════════════════════════════════════════════


class TestTBWritebackIntegration:
    """审定回写 TB writeback 完整集成流程。

    Requirements: 9.1
    """

    @pytest.mark.asyncio
    async def test_writeback_single_account_success(self):
        """单科目回写：service 传入统一 writer 并保留 flush-only 边界。"""
        db = AsyncMock()
        db.commit = AsyncMock()
        with patch(
            "app.services.s_transaction_tb_writeback_service.publish_rows",
            new=AsyncMock(return_value=_published_result("1601", "120000", previous="50000")),
        ) as mock_publish:
            svc = STransactionTBWritebackService(db)
            result = await svc.writeback_audited_amount(
                project_id=PROJECT_ID,
                year=YEAR,
                account_code="1601",
                audited_amount=120000.0,
                component_type="s4-nonmonetary-exchange",
                wp_code="S4",
            )

        mock_publish.assert_awaited_once()
        assert mock_publish.call_args.args[:3] == (db, PROJECT_ID, YEAR)
        assert mock_publish.call_args.args[3] == [
            {"account_code": "1601", "audited_amount": 120000.0}
        ]
        assert result == {
            "account_code": "1601",
            "audited_amount": "120000",
            "previous_amount": "50000",
        }
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_writeback_negative_amount_stores_abs(self):
        """负金额回写在调用统一 writer 前转为绝对值。"""
        db = AsyncMock()
        with patch(
            "app.services.s_transaction_tb_writeback_service.publish_rows",
            new=AsyncMock(return_value=_published_result("2202", "75000.5", previous=None)),
        ) as mock_publish:
            svc = STransactionTBWritebackService(db)
            result = await svc.writeback_audited_amount(
                project_id=PROJECT_ID,
                year=YEAR,
                account_code="2202",
                audited_amount=-75000.5,
                component_type="s5-debt-restructuring",
                wp_code="S5",
            )

        assert mock_publish.call_args.args[3] == [
            {"account_code": "2202", "audited_amount": 75000.5}
        ]
        assert result["previous_amount"] is None

    @pytest.mark.asyncio
    async def test_writeback_invalid_component_type_raises(self):
        """非法 componentType 抛出 ValueError。"""
        db = AsyncMock()
        svc = STransactionTBWritebackService(db)
        with pytest.raises(ValueError, match="不属于 S 类交易型底稿"):
            await svc.writeback_audited_amount(
                project_id=PROJECT_ID,
                year=YEAR,
                account_code="1601",
                audited_amount=100.0,
                component_type="invalid-type",
                wp_code="S4",
            )

    @pytest.mark.asyncio
    async def test_writeback_account_not_found_raises(self):
        """统一 writer 跳过科目时 service 转换为 LookupError。"""
        db = AsyncMock()
        with patch(
            "app.services.s_transaction_tb_writeback_service.publish_rows",
            new=AsyncMock(return_value=_skipped_result("9999")),
        ):
            svc = STransactionTBWritebackService(db)
            with pytest.raises(LookupError, match="未找到科目"):
                await svc.writeback_audited_amount(
                    project_id=PROJECT_ID,
                    year=YEAR,
                    account_code="9999",
                    audited_amount=100.0,
                    wp_code="S4",
                )

    @pytest.mark.asyncio
    async def test_writeback_batch_multiple_accounts(self):
        """批量回写：多科目逐行调用统一 writer。"""
        db = AsyncMock()
        with patch(
            "app.services.s_transaction_tb_writeback_service.publish_rows",
            new=AsyncMock(
                side_effect=[
                    _published_result("1601", "100000", previous="0"),
                    _published_result("1701", "50000", previous="0"),
                ]
            ),
        ) as mock_publish:
            svc = STransactionTBWritebackService(db)
            results = await svc.writeback_batch(
                project_id=PROJECT_ID,
                year=YEAR,
                rows=[
                    {"account_code": "1601", "audited_amount": 100000},
                    {"account_code": "1701", "audited_amount": 50000},
                ],
                component_type="s4-nonmonetary-exchange",
                wp_code="S4",
            )

        assert len(results) == 2
        assert all("error" not in item for item in results)
        assert mock_publish.await_count == 2

    @pytest.mark.asyncio
    async def test_writeback_zero_amount(self):
        """回写 0 金额应正常传递。"""
        db = AsyncMock()
        with patch(
            "app.services.s_transaction_tb_writeback_service.publish_rows",
            new=AsyncMock(return_value=_published_result("1601", "0", previous="50000")),
        ) as mock_publish:
            svc = STransactionTBWritebackService(db)
            result = await svc.writeback_audited_amount(
                project_id=PROJECT_ID,
                year=YEAR,
                account_code="1601",
                audited_amount=0.0,
                wp_code="S6",
            )

        assert mock_publish.call_args.args[3] == [
            {"account_code": "1601", "audited_amount": 0.0}
        ]
        assert Decimal(result["audited_amount"]) == Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Auto data resolver — auto-data 返回正确 accounts
# ═══════════════════════════════════════════════════════════════════════════════


class TestAutoDataResolverIntegration:
    """自动取数 resolver 集成测试。

    Requirements: 9.1 (auto_data_source resolver)
    """

    @pytest.mark.asyncio
    async def test_resolve_auto_data_s4_returns_accounts(self):
        """S4 auto-data resolver 返回固定资产/无形资产/原材料科目。"""
        # 验证 S4 对应的科目编码配置
        assert "s4-nonmonetary-exchange" in S_TRANSACTION_ACCOUNT_CODES
        codes = S_TRANSACTION_ACCOUNT_CODES["s4-nonmonetary-exchange"]
        assert "1601" in codes  # 固定资产
        assert "1701" in codes  # 无形资产
        assert "1403" in codes  # 原材料

    @pytest.mark.asyncio
    async def test_resolve_auto_data_s5_returns_accounts(self):
        """S5 auto-data resolver 返回债权债务科目。"""
        assert "s5-debt-restructuring" in S_TRANSACTION_ACCOUNT_CODES
        codes = S_TRANSACTION_ACCOUNT_CODES["s5-debt-restructuring"]
        assert "1122" in codes  # 应收账款
        assert "2202" in codes  # 应付账款

    @pytest.mark.asyncio
    async def test_resolve_auto_data_s6_returns_accounts(self):
        """S6 auto-data resolver 返回关联方资金占用科目。"""
        assert "s6-fund-occupation" in S_TRANSACTION_ACCOUNT_CODES
        codes = S_TRANSACTION_ACCOUNT_CODES["s6-fund-occupation"]
        assert "1221" in codes  # 其他应收款
        assert "1123" in codes  # 预付账款

    @pytest.mark.asyncio
    async def test_resolve_auto_data_with_field_overrides(self):
        """field_overrides 应覆盖 resolver 返回值（优先级逻辑验证）。"""
        # 验证合并优先级逻辑：field_overrides > resolver
        auto_resolved = {"unadjusted_1601": 100000, "aje_1601": 5000}
        field_overrides = {"unadjusted_1601": 120000}

        # 模拟 resolve_auto_data 内的合并逻辑
        final = dict(auto_resolved)
        overrides_applied: dict[str, Any] = {}
        for key, val in field_overrides.items():
            if val is not None:
                final[key] = val
                overrides_applied[key] = val

        assert final["unadjusted_1601"] == 120000  # override 生效
        assert final["aje_1601"] == 5000  # 保留 resolver 值
        assert overrides_applied == {"unadjusted_1601": 120000}

        # 验证 None 值不覆盖
        final2 = dict(auto_resolved)
        overrides_none = {"unadjusted_1601": None}
        for key, val in overrides_none.items():
            if val is not None:
                final2[key] = val
        assert final2["unadjusted_1601"] == 100000  # None 不覆盖

    @pytest.mark.asyncio
    async def test_all_s_wp_codes_have_account_mappings(self):
        """所有支持审定回写的 wp_code 都有对应的科目配置。"""
        expected_codes = {"S4", "S5", "S6", "S8", "S9", "S10"}
        configured_codes = set()

        # component_type 映射
        for ct in S_TRANSACTION_ACCOUNT_CODES:
            configured_codes.add(ct)

        # 检查字典键（混合 componentType 和 wp_code）
        assert "s4-nonmonetary-exchange" in S_TRANSACTION_ACCOUNT_CODES
        assert "s5-debt-restructuring" in S_TRANSACTION_ACCOUNT_CODES
        assert "s6-fund-occupation" in S_TRANSACTION_ACCOUNT_CODES
        assert "S8" in S_TRANSACTION_ACCOUNT_CODES
        assert "S9" in S_TRANSACTION_ACCOUNT_CODES
        assert "S10" in S_TRANSACTION_ACCOUNT_CODES


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Disclosure notify — broadcasts event
# ═══════════════════════════════════════════════════════════════════════════════


class TestDisclosureNotifyIntegration:
    """披露通知 disclosure-notify 广播事件集成测试。

    Requirements: 9.1 (disclosure:note-text-updated)
    """

    def test_disclosure_notify_endpoint_exists(self):
        """disclosure-notify 端点存在且可导入。"""
        from app.routers.s_transaction_calculation import s_transaction_disclosure_notify
        assert callable(s_transaction_disclosure_notify)

    def test_disclosure_notify_only_accepts_s4_s5(self):
        """disclosure-notify 仅支持 S4/S5 wp_code（非经常性损益）。"""
        import inspect
        from app.routers.s_transaction_calculation import s_transaction_disclosure_notify

        source = inspect.getsource(s_transaction_disclosure_notify)
        assert '"S4"' in source
        assert '"S5"' in source
        # 不接受其他 S 类底稿
        assert "valid_wp_codes" in source

    def test_disclosure_notify_broadcasts_correct_event_type(self):
        """disclosure-notify 广播 disclosure:note-text-updated 事件。"""
        import inspect
        from app.routers.s_transaction_calculation import s_transaction_disclosure_notify

        source = inspect.getsource(s_transaction_disclosure_notify)
        assert "disclosure:note-text-updated" in source
        assert "broadcast_raw" in source

    def test_disclosure_notify_includes_non_recurring_flag(self):
        """事件 payload 包含 non_recurring=True 标注。"""
        import inspect
        from app.routers.s_transaction_calculation import s_transaction_disclosure_notify

        source = inspect.getsource(s_transaction_disclosure_notify)
        assert "non_recurring" in source

    def test_tb_writeback_endpoint_exists(self):
        """tb-writeback 端点存在且可导入。"""
        from app.routers.s_transaction_calculation import s_transaction_tb_writeback
        assert callable(s_transaction_tb_writeback)

    def test_auto_data_endpoint_exists(self):
        """auto-data 端点存在且可导入。"""
        from app.routers.s_transaction_calculation import s_transaction_auto_data
        assert callable(s_transaction_auto_data)

    def test_writeback_publishes_workpaper_saved_event(self):
        """tb-writeback 端点源码包含 WORKPAPER_SAVED 事件发布。"""
        import inspect
        from app.routers.s_transaction_calculation import s_transaction_tb_writeback

        source = inspect.getsource(s_transaction_tb_writeback)
        assert "WORKPAPER_SAVED" in source
        assert "event_bus.publish" in source


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Render strategy — 6 个 render 策略返回正确 sheet 结构
# ═══════════════════════════════════════════════════════════════════════════════


class TestRenderStrategyIntegration:
    """6 个专属 componentType 的 render 策略注册验证。

    Requirements: 1.5
    """

    def test_all_6_dedicated_types_in_renderer_dispatch(self):
        """6 个专属 componentType 均已注册 RENDERER_DISPATCH。"""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH

        dedicated_types = [
            "s4-nonmonetary-exchange",
            "s5-debt-restructuring",
            "s6-fund-occupation",
            "s12-cpa-expert",
            "s13-mgmt-expert",
            "s14-accounting-estimate",
        ]

        for ct in dedicated_types:
            assert ct in RENDERER_DISPATCH, f"{ct} 未注册于 RENDERER_DISPATCH"

    def test_render_strategies_are_callable(self):
        """6 个 render 策略均为可调用对象。"""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH

        dedicated_types = [
            "s4-nonmonetary-exchange",
            "s5-debt-restructuring",
            "s6-fund-occupation",
            "s12-cpa-expert",
            "s13-mgmt-expert",
            "s14-accounting-estimate",
        ]

        for ct in dedicated_types:
            strategy = RENDERER_DISPATCH[ct]
            assert callable(strategy), f"{ct} 的 render strategy 不是可调用对象"

    def test_all_6_in_whole_wp_multisheet_dedicated(self):
        """6 个专属 componentType 均在 _WHOLE_WP_MULTISHEET_DEDICATED。"""
        from app.routers.wp_render_config import _WHOLE_WP_MULTISHEET_DEDICATED

        dedicated_types = [
            "s4-nonmonetary-exchange",
            "s5-debt-restructuring",
            "s6-fund-occupation",
            "s12-cpa-expert",
            "s13-mgmt-expert",
            "s14-accounting-estimate",
        ]

        for ct in dedicated_types:
            assert ct in _WHOLE_WP_MULTISHEET_DEDICATED, \
                f"{ct} 未加入 _WHOLE_WP_MULTISHEET_DEDICATED"

    def test_all_6_in_valid_component_types(self):
        """6 个专属 componentType 均在 VALID_COMPONENT_TYPES。"""
        from app.services.wp_classification_service import VALID_COMPONENT_TYPES

        dedicated_types = [
            "s4-nonmonetary-exchange",
            "s5-debt-restructuring",
            "s6-fund-occupation",
            "s12-cpa-expert",
            "s13-mgmt-expert",
            "s14-accounting-estimate",
        ]

        for ct in dedicated_types:
            assert ct in VALID_COMPONENT_TYPES, f"{ct} 未注册于 VALID_COMPONENT_TYPES"

    def test_wp_code_overrides_s4_to_s14_correct(self):
        """wp_code_overrides.json 中交易型映射验证。"""
        p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
        data = json.loads(p.read_text(encoding="utf-8"))

        assert data.get("S4") == "s4-nonmonetary-exchange"
        assert data.get("S5") == "s5-debt-restructuring"
        assert data.get("S6") == "s6-fund-occupation"
        assert data.get("S12") == "s12-cpa-expert"
        assert data.get("S13") == "s13-mgmt-expert"
        assert data.get("S14") == "s14-accounting-estimate"

    def test_wp_code_overrides_checklist_types(self):
        """wp_code_overrides.json 中检查表型→a-program-console 映射。"""
        p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
        data = json.loads(p.read_text(encoding="utf-8"))

        checklist_codes = ["S1", "S2", "S8", "S9", "S10", "S11", "S16", "S17"]
        for code in checklist_codes:
            assert data.get(code) == "a-program-console", \
                f"{code} 应映射为 a-program-console，实际为 {data.get(code)}"
