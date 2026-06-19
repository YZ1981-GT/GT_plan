"""集成测试 — event_handlers_cycle_linkage._on_d_audit_determination_saved

Spec:   .kiro/specs/workpaper-render-config-refactor/ Sprint 2 Task 2.1
Design: §4 联动 Handler 测试设计
Reqs:   Req-2 mock async_session_factory 返回 in-memory DB session，构造 EventPayload，直调 handler 函数，断言 DB 写入

测试对象：
  _on_d_audit_determination_saved(payload: EventPayload) -> None
    D~N 类审定表保存 → 回写 audited_amount 到 trial_balance

验证场景：
  T1  D1-1 有效 rows → session.execute 被调用 + commit
  T2  无效 wp_code（不匹配 ^[D-N]\\d+-1$）→ 直接 return，无 DB 操作
  T3  空 rows → 直接 return
  T4  多行 rows → 每行生成一条 update 语句
  T5  audited_amount 非数字 → 跳过该行，继续处理其他行
  T6  commit 后如有更新 → 发布 TRIAL_BALANCE_UPDATED 事件
"""

from __future__ import annotations

import sys
import types
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.audit_platform_models import TrialBalance


# ---------------------------------------------------------------------------
# 修复 handler 内 lazy import 路径：handler 引用 app.models.trial_balance_models
# 但实际 TrialBalance 定义在 app.models.audit_platform_models。
# 在测试环境中注册别名模块使 handler 的 lazy import 能正常解析。
# ---------------------------------------------------------------------------
_tb_module = types.ModuleType("app.models.trial_balance_models")
_tb_module.TrialBalance = TrialBalance  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.trial_balance_models", _tb_module)


# ---------------------------------------------------------------------------
# Mock Session：捕获 execute 调用 + 模拟 rowcount
# ---------------------------------------------------------------------------


class _CapturingSession:
    """模拟 AsyncSession — 捕获 .execute() 调用的语句."""

    def __init__(self, row_count: int = 1):
        self.executed_stmts: list = []
        self.committed = False
        self.rolled_back = False
        self._row_count = row_count

    async def execute(self, stmt, *args, **kwargs):
        self.executed_stmts.append(stmt)
        result = MagicMock()
        result.rowcount = self._row_count
        return result

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """返回一个可捕获 DB 操作的 mock session."""
    return _CapturingSession(row_count=1)


@pytest.fixture
def patch_session_factory(mock_session, monkeypatch):
    """Patch async_session_factory 使 handler 使用 mock session."""

    @asynccontextmanager
    async def _fake_factory(*args, **kwargs):
        yield mock_session

    monkeypatch.setattr(
        "app.services.event_handlers_cycle_linkage.async_session_factory",
        _fake_factory,
    )


@pytest.fixture
def patch_event_bus(monkeypatch):
    """Patch event_bus.publish_immediate 使之不真正发布事件."""
    mock_publish = AsyncMock()
    monkeypatch.setattr(
        "app.services.event_handlers_cycle_linkage.event_bus.publish_immediate",
        mock_publish,
    )
    return mock_publish


@pytest.fixture
def sample_project_id():
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOnDAuditDeterminationSaved:
    """_on_d_audit_determination_saved 集成测试."""

    @pytest.mark.asyncio
    async def test_d1_1_writeback_updates_tb(
        self, mock_session, patch_session_factory, patch_event_bus, sample_project_id
    ):
        """T1: 发 WORKPAPER_SAVED with wp_code=D1-1 + rows → TB audited_amount 被更新."""
        from app.services.event_handlers_cycle_linkage import (
            _on_d_audit_determination_saved,
        )

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "D1-1",
                "parsed_data": {
                    "rows": [
                        {"standard_account_code": "1001", "audited_amount": "100000.50"},
                        {"standard_account_code": "1002", "audited_amount": "250000.00"},
                    ]
                },
            },
        )

        await _on_d_audit_determination_saved(payload)

        # 应该执行了 2 条 update 语句
        assert len(mock_session.executed_stmts) == 2
        assert mock_session.committed is True
        assert mock_session.rolled_back is False

        # 应该发布了 TRIAL_BALANCE_UPDATED 事件
        patch_event_bus.assert_awaited_once()
        call_args = patch_event_bus.call_args[0][0]
        assert call_args.event_type == EventType.TRIAL_BALANCE_UPDATED
        assert call_args.project_id == sample_project_id
        assert call_args.year == 2025

    @pytest.mark.asyncio
    async def test_invalid_wp_code_skips(
        self, mock_session, patch_session_factory, patch_event_bus, sample_project_id
    ):
        """T2: 非审定表编码（如 D1-2, A1, C1）直接 return，无 DB 操作."""
        from app.services.event_handlers_cycle_linkage import (
            _on_d_audit_determination_saved,
        )

        for wp_code in ["D1-2", "A1", "C2-1", "S1-1", "D0"]:
            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=sample_project_id,
                year=2025,
                extra={
                    "wp_code": wp_code,
                    "parsed_data": {
                        "rows": [{"standard_account_code": "1001", "audited_amount": "100"}]
                    },
                },
            )
            await _on_d_audit_determination_saved(payload)

        # 不应有任何 DB 操作
        assert len(mock_session.executed_stmts) == 0
        assert mock_session.committed is False

    @pytest.mark.asyncio
    async def test_empty_rows_skips(
        self, mock_session, patch_session_factory, patch_event_bus, sample_project_id
    ):
        """T3: rows 为空 → 直接 return."""
        from app.services.event_handlers_cycle_linkage import (
            _on_d_audit_determination_saved,
        )

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "D1-1",
                "parsed_data": {"rows": []},
            },
        )

        await _on_d_audit_determination_saved(payload)

        assert len(mock_session.executed_stmts) == 0
        assert mock_session.committed is False

    @pytest.mark.asyncio
    async def test_multiple_cycles_accepted(
        self, mock_session, patch_session_factory, patch_event_bus, sample_project_id
    ):
        """T4: K8-1, N5-1 等其他循环审定表也能正常处理."""
        from app.services.event_handlers_cycle_linkage import (
            _on_d_audit_determination_saved,
        )

        for wp_code in ["K8-1", "N5-1", "G1-1", "H1-1"]:
            # 重置 session 状态
            mock_session.executed_stmts.clear()
            mock_session.committed = False

            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=sample_project_id,
                year=2025,
                extra={
                    "wp_code": wp_code,
                    "parsed_data": {
                        "rows": [
                            {"standard_account_code": "6001", "audited_amount": "50000"},
                        ]
                    },
                },
            )

            await _on_d_audit_determination_saved(payload)

            assert len(mock_session.executed_stmts) == 1, f"{wp_code} 应生成 1 条 update"
            assert mock_session.committed is True, f"{wp_code} 应 commit"

    @pytest.mark.asyncio
    async def test_invalid_audited_amount_skipped(
        self, mock_session, patch_session_factory, patch_event_bus, sample_project_id
    ):
        """T5: audited_amount 非数字（如 'N/A'）→ 跳过该行，继续其他行."""
        from app.services.event_handlers_cycle_linkage import (
            _on_d_audit_determination_saved,
        )

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "D1-1",
                "parsed_data": {
                    "rows": [
                        {"standard_account_code": "1001", "audited_amount": "N/A"},
                        {"standard_account_code": "1002", "audited_amount": "200.00"},
                        {"standard_account_code": "1003", "audited_amount": "not_a_number"},
                    ]
                },
            },
        )

        await _on_d_audit_determination_saved(payload)

        # 只有 1002 那条是有效的
        assert len(mock_session.executed_stmts) == 1
        assert mock_session.committed is True

    @pytest.mark.asyncio
    async def test_publish_event_on_successful_update(
        self, mock_session, patch_session_factory, patch_event_bus, sample_project_id
    ):
        """T6: commit 后有更新 → 发布 TRIAL_BALANCE_UPDATED 并携带来源信息."""
        from app.services.event_handlers_cycle_linkage import (
            _on_d_audit_determination_saved,
        )

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            account_codes=["1001"],
            extra={
                "wp_code": "F2-1",
                "parsed_data": {
                    "rows": [
                        {"standard_account_code": "1001", "audited_amount": "999.99"},
                    ]
                },
            },
        )

        await _on_d_audit_determination_saved(payload)

        # 验证发布的事件
        patch_event_bus.assert_awaited_once()
        published_payload = patch_event_bus.call_args[0][0]
        assert published_payload.event_type == EventType.TRIAL_BALANCE_UPDATED
        assert published_payload.project_id == sample_project_id
        assert published_payload.year == 2025
        assert published_payload.extra["source"] == "d_audit_determination:F2-1"

    @pytest.mark.asyncio
    async def test_no_publish_when_zero_updates(
        self, patch_session_factory, patch_event_bus, sample_project_id, monkeypatch
    ):
        """当 rowcount=0（未匹配任何行）时，不应发布事件."""
        from app.services.event_handlers_cycle_linkage import (
            _on_d_audit_determination_saved,
        )

        # 使用 rowcount=0 的 session
        zero_session = _CapturingSession(row_count=0)

        @asynccontextmanager
        async def _zero_factory(*args, **kwargs):
            yield zero_session

        monkeypatch.setattr(
            "app.services.event_handlers_cycle_linkage.async_session_factory",
            _zero_factory,
        )

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "D1-1",
                "parsed_data": {
                    "rows": [
                        {"standard_account_code": "9999", "audited_amount": "100"},
                    ]
                },
            },
        )

        await _on_d_audit_determination_saved(payload)

        # session 被调用了但 rowcount=0 → 不发布事件
        assert len(zero_session.executed_stmts) == 1
        assert zero_session.committed is True
        patch_event_bus.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_project_id_or_year_skips(self, mock_session, patch_session_factory):
        """缺少 project_id 或 year 时直接 return."""
        from app.services.event_handlers_cycle_linkage import (
            _on_d_audit_determination_saved,
        )

        # year=None 场景
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid.uuid4(),
            year=None,
            extra={
                "wp_code": "D1-1",
                "parsed_data": {
                    "rows": [{"standard_account_code": "1001", "audited_amount": "100"}]
                },
            },
        )

        await _on_d_audit_determination_saved(payload)
        assert len(mock_session.executed_stmts) == 0

    @pytest.mark.asyncio
    async def test_account_code_field_fallback(
        self, mock_session, patch_session_factory, patch_event_bus, sample_project_id
    ):
        """rows 中用 account_code（而非 standard_account_code）也能正常处理."""
        from app.services.event_handlers_cycle_linkage import (
            _on_d_audit_determination_saved,
        )

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "D1-1",
                "parsed_data": {
                    "rows": [
                        {"account_code": "1001", "audited_amount": "300.00"},
                    ]
                },
            },
        )

        await _on_d_audit_determination_saved(payload)

        assert len(mock_session.executed_stmts) == 1
        assert mock_session.committed is True


# ---------------------------------------------------------------------------
# _on_c_control_test_saved 集成测试
# ---------------------------------------------------------------------------


class _CapturingFieldOverrideService:
    """捕获 FieldOverrideService.set() 调用参数."""

    def __init__(self):
        self.calls: list[dict] = []

    async def set(self, **kwargs):
        self.calls.append(kwargs)


class TestOnCControlTestSaved:
    """_on_c_control_test_saved 集成测试.

    Spec:   .kiro/specs/workpaper-render-config-refactor/ Sprint 2 Task 2.2
    Design: §4 联动 Handler 测试设计
    Reqs:   Req-2 发送 WORKPAPER_SAVED + wp_code=C2-1 → 验证 field_overrides 写入

    验证场景：
      T1  C2 有效 payload → FieldOverrideService.set 被调用 3 次（conclusion + tested_controls + deviation_count）
      T2  无效 wp_code（C1, C16, D1-1）→ 直接 return，无 DB 操作
      T3  缺少 project_id 或 year → 直接 return
      T4  只有 deviation_count（无 conclusion/tested_controls）→ 仅 1 次 set
      T5  多个循环 C3~C15 → scope 按循环名映射正确
    """

    @pytest.fixture
    def capturing_svc(self):
        """返回一个可捕获 set() 调用的 mock FieldOverrideService."""
        return _CapturingFieldOverrideService()

    @pytest.fixture
    def mock_c_session(self):
        """返回一个基础 mock session（仅需 commit/rollback）."""
        return _CapturingSession(row_count=0)

    @pytest.fixture
    def patch_c_session_factory(self, mock_c_session, monkeypatch):
        """Patch async_session_factory 使 handler 使用 mock session."""

        @asynccontextmanager
        async def _fake_factory(*args, **kwargs):
            yield mock_c_session

        monkeypatch.setattr(
            "app.services.event_handlers_cycle_linkage.async_session_factory",
            _fake_factory,
        )

    @pytest.fixture
    def patch_field_override_svc(self, capturing_svc, monkeypatch):
        """Patch FieldOverrideService 使 handler 使用 capturing_svc.

        handler 内部做 `from app.services.field_override_service import FieldOverrideService`
        lazy import，需要 patch 源模块的类。
        """
        monkeypatch.setattr(
            "app.services.field_override_service.FieldOverrideService",
            lambda session: capturing_svc,
        )

    @pytest.fixture
    def patch_invalidate_cache(self, monkeypatch):
        """Patch invalidate_auto_cache."""
        mock_fn = MagicMock()
        monkeypatch.setattr(
            "app.services.event_handlers_cycle_linkage.invalidate_auto_cache",
            mock_fn,
        )
        return mock_fn

    @pytest.mark.asyncio
    async def test_c2_writes_field_overrides(
        self,
        capturing_svc,
        mock_c_session,
        patch_c_session_factory,
        patch_field_override_svc,
        patch_invalidate_cache,
        sample_project_id,
    ):
        """T1: 发 WORKPAPER_SAVED with wp_code=C2 → field_overrides 写入 scope=control_test_result:销售收入."""
        from app.services.event_handlers_cycle_linkage import (
            _on_c_control_test_saved,
        )

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "C2",
                "parsed_data": {
                    "conclusion": "有效",
                    "tested_controls": 5,
                    "deviation_count": 1,
                },
            },
        )

        await _on_c_control_test_saved(payload)

        # 应该调用 3 次 set：conclusion + tested_controls + deviation_count
        assert len(capturing_svc.calls) == 3
        assert mock_c_session.committed is True
        assert mock_c_session.rolled_back is False

        # 验证 scope 正确
        expected_scope = "control_test_result:销售收入"
        for call in capturing_svc.calls:
            assert call["scope"] == expected_scope
            assert call["project_id"] == sample_project_id
            assert call["year"] == 2025
            assert call["item_key"] == "C2"

        # 验证各字段
        fields = {c["field"]: c["value"] for c in capturing_svc.calls}
        assert fields["conclusion"] == "有效"
        assert fields["tested_controls"] == "5"
        assert fields["deviation_count"] == "1"

        # invalidate_auto_cache 被调用
        patch_invalidate_cache.assert_called_once_with(sample_project_id, 2025)

    @pytest.mark.asyncio
    async def test_invalid_wp_code_skips(
        self,
        capturing_svc,
        mock_c_session,
        patch_c_session_factory,
        patch_field_override_svc,
        patch_invalidate_cache,
        sample_project_id,
    ):
        """T2: 非 C2~C15 编码（如 C1, C16, D1-1, C2-1）→ 直接 return，无 DB 操作."""
        from app.services.event_handlers_cycle_linkage import (
            _on_c_control_test_saved,
        )

        for wp_code in ["C1", "C16", "C0", "D1-1", "C2-1", "A1", ""]:
            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=sample_project_id,
                year=2025,
                extra={
                    "wp_code": wp_code,
                    "parsed_data": {
                        "conclusion": "有效",
                        "tested_controls": 3,
                        "deviation_count": 0,
                    },
                },
            )
            await _on_c_control_test_saved(payload)

        # 不应有任何 set 调用
        assert len(capturing_svc.calls) == 0
        assert mock_c_session.committed is False

    @pytest.mark.asyncio
    async def test_missing_project_id_or_year_skips(
        self,
        capturing_svc,
        mock_c_session,
        patch_c_session_factory,
        patch_field_override_svc,
        patch_invalidate_cache,
    ):
        """T3: 缺少 project_id 或 year → 直接 return."""
        from app.services.event_handlers_cycle_linkage import (
            _on_c_control_test_saved,
        )

        # year=None
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid.uuid4(),
            year=None,
            extra={
                "wp_code": "C2",
                "parsed_data": {"conclusion": "有效", "deviation_count": 0},
            },
        )
        await _on_c_control_test_saved(payload)
        assert len(capturing_svc.calls) == 0

    @pytest.mark.asyncio
    async def test_only_deviation_count_when_no_conclusion(
        self,
        capturing_svc,
        mock_c_session,
        patch_c_session_factory,
        patch_field_override_svc,
        patch_invalidate_cache,
        sample_project_id,
    ):
        """T4: 无 conclusion 和 tested_controls → 只写 deviation_count（1 次 set）."""
        from app.services.event_handlers_cycle_linkage import (
            _on_c_control_test_saved,
        )

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "C5",
                "parsed_data": {
                    "deviation_count": 2,
                },
            },
        )

        await _on_c_control_test_saved(payload)

        # 只有 deviation_count 一条（conclusion 和 tested_controls 为 falsy 跳过）
        assert len(capturing_svc.calls) == 1
        assert capturing_svc.calls[0]["field"] == "deviation_count"
        assert capturing_svc.calls[0]["value"] == "2"
        assert capturing_svc.calls[0]["scope"] == "control_test_result:投资"

    @pytest.mark.asyncio
    async def test_multiple_cycles_scope_mapping(
        self,
        mock_c_session,
        patch_c_session_factory,
        patch_invalidate_cache,
        sample_project_id,
        monkeypatch,
    ):
        """T5: C3~C15 各循环 scope 映射正确."""
        from app.services.event_handlers_cycle_linkage import (
            _on_c_control_test_saved,
        )

        expected_mappings = {
            "C3": "货币资金",
            "C7": "在建工程",
            "C10": "职工薪酬",
            "C15": "关联方",
        }

        for wp_code, expected_cycle in expected_mappings.items():
            svc = _CapturingFieldOverrideService()

            monkeypatch.setattr(
                "app.services.field_override_service.FieldOverrideService",
                lambda session, _svc=svc: _svc,
            )

            # 重置 session
            mock_c_session.committed = False

            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=sample_project_id,
                year=2025,
                extra={
                    "wp_code": wp_code,
                    "parsed_data": {
                        "conclusion": "有效",
                        "tested_controls": 3,
                        "deviation_count": 0,
                    },
                },
            )

            await _on_c_control_test_saved(payload)

            assert mock_c_session.committed is True, f"{wp_code} 应 commit"
            expected_scope = f"control_test_result:{expected_cycle}"
            for call in svc.calls:
                assert call["scope"] == expected_scope, (
                    f"{wp_code} scope 应为 {expected_scope}, 实际 {call['scope']}"
                )


# ---------------------------------------------------------------------------
# _on_f_workpaper_conclusion_saved 集成测试
# ---------------------------------------------------------------------------


class TestOnFWorkpaperConclusionSaved:
    """_on_f_workpaper_conclusion_saved 集成测试.

    Spec:   .kiro/specs/workpaper-render-config-refactor/ Sprint 2 Task 2.3
    Design: §4 联动 Handler 测试设计
    Reqs:   Req-2 发送 WORKPAPER_SAVED with wp_code=F1-3 → field_overrides scope=f_procedure_status 写入

    验证场景：
      T1  F2-21 有效 payload → FieldOverrideService.set 被调用 2 次（conclusion + status）
      T2  无效 wp_code（F1-3, F2-20, F2-27, D1-1）→ 直接 return，无 DB 操作
      T3  缺少 project_id 或 year → 直接 return
      T4  无 conclusion → 只写 status="in_progress"（1 次 set）
      T5  多种 conclusion 字段 fallback（summary_conclusion / overall_conclusion）
    """

    @pytest.fixture
    def capturing_svc(self):
        """返回一个可捕获 set() 调用的 mock FieldOverrideService."""
        return _CapturingFieldOverrideService()

    @pytest.fixture
    def mock_f_session(self):
        """返回一个基础 mock session."""
        return _CapturingSession(row_count=0)

    @pytest.fixture
    def patch_f_session_factory(self, mock_f_session, monkeypatch):
        """Patch async_session_factory 使 handler 使用 mock session."""

        @asynccontextmanager
        async def _fake_factory(*args, **kwargs):
            yield mock_f_session

        monkeypatch.setattr(
            "app.services.event_handlers_cycle_linkage.async_session_factory",
            _fake_factory,
        )

    @pytest.fixture
    def patch_f_field_override_svc(self, capturing_svc, monkeypatch):
        """Patch FieldOverrideService 使 handler 使用 capturing_svc."""
        monkeypatch.setattr(
            "app.services.field_override_service.FieldOverrideService",
            lambda session: capturing_svc,
        )

    @pytest.fixture
    def patch_f_invalidate_cache(self, monkeypatch):
        """Patch invalidate_auto_cache."""
        mock_fn = MagicMock()
        monkeypatch.setattr(
            "app.services.event_handlers_cycle_linkage.invalidate_auto_cache",
            mock_fn,
        )
        return mock_fn

    @pytest.mark.asyncio
    async def test_f2_21_writes_field_overrides(
        self,
        capturing_svc,
        mock_f_session,
        patch_f_session_factory,
        patch_f_field_override_svc,
        patch_f_invalidate_cache,
        sample_project_id,
    ):
        """T1: 发 WORKPAPER_SAVED with wp_code=F2-21 → field_overrides 写入 scope=f_procedure_status:F2-21."""
        from app.services.event_handlers_cycle_linkage import (
            _on_f_workpaper_conclusion_saved,
        )

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "F2-21",
                "parsed_data": {
                    "conclusion": "存货盘点无异常",
                    "status": "completed",
                },
            },
        )

        await _on_f_workpaper_conclusion_saved(payload)

        # 应该调用 2 次 set：conclusion + status
        assert len(capturing_svc.calls) == 2
        assert mock_f_session.committed is True
        assert mock_f_session.rolled_back is False

        # 验证 scope 正确
        expected_scope = "f_procedure_status:F2-21"
        for call in capturing_svc.calls:
            assert call["scope"] == expected_scope
            assert call["project_id"] == sample_project_id
            assert call["year"] == 2025
            assert call["item_key"] == "F2-21"

        # 验证各字段
        fields = {c["field"]: c["value"] for c in capturing_svc.calls}
        assert fields["conclusion"] == "存货盘点无异常"
        assert fields["status"] == "completed"

        # invalidate_auto_cache 被调用
        patch_f_invalidate_cache.assert_called_once_with(sample_project_id, 2025)

    @pytest.mark.asyncio
    async def test_invalid_wp_code_skips(
        self,
        capturing_svc,
        mock_f_session,
        patch_f_session_factory,
        patch_f_field_override_svc,
        patch_f_invalidate_cache,
        sample_project_id,
    ):
        """T2: 非 F 类结论底稿编码 → 直接 return，无 DB 操作.

        _F_CONCLUSION_RANGES = [(21,26),(29,35),(38,44),(47,49),(55,58)]
        有效: F2-21~F2-26, F2-29~F2-35, F2-38~F2-44, F2-47~F2-49, F2-55~F2-58
        无效: F1-3, F2-20, F2-27, F2-28, F2-50, D1-1, C2
        """
        from app.services.event_handlers_cycle_linkage import (
            _on_f_workpaper_conclusion_saved,
        )

        invalid_codes = ["F1-3", "F2-20", "F2-27", "F2-28", "F2-50", "D1-1", "C2", "F2-0", ""]
        for wp_code in invalid_codes:
            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=sample_project_id,
                year=2025,
                extra={
                    "wp_code": wp_code,
                    "parsed_data": {
                        "conclusion": "无异常",
                        "status": "completed",
                    },
                },
            )
            await _on_f_workpaper_conclusion_saved(payload)

        # 不应有任何 set 调用
        assert len(capturing_svc.calls) == 0
        assert mock_f_session.committed is False

    @pytest.mark.asyncio
    async def test_missing_project_id_or_year_skips(
        self,
        capturing_svc,
        mock_f_session,
        patch_f_session_factory,
        patch_f_field_override_svc,
        patch_f_invalidate_cache,
    ):
        """T3: 缺少 project_id 或 year → 直接 return."""
        from app.services.event_handlers_cycle_linkage import (
            _on_f_workpaper_conclusion_saved,
        )

        # year=None
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid.uuid4(),
            year=None,
            extra={
                "wp_code": "F2-21",
                "parsed_data": {"conclusion": "无异常", "status": "completed"},
            },
        )
        await _on_f_workpaper_conclusion_saved(payload)
        assert len(capturing_svc.calls) == 0
        assert mock_f_session.committed is False

    @pytest.mark.asyncio
    async def test_no_conclusion_writes_only_status(
        self,
        capturing_svc,
        mock_f_session,
        patch_f_session_factory,
        patch_f_field_override_svc,
        patch_f_invalidate_cache,
        sample_project_id,
    ):
        """T4: 无 conclusion → 只写 status="in_progress"（1 次 set）."""
        from app.services.event_handlers_cycle_linkage import (
            _on_f_workpaper_conclusion_saved,
        )

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "F2-30",
                "parsed_data": {
                    "status": "in_progress",
                    # 无 conclusion / summary_conclusion / overall_conclusion / audit_conclusion
                },
            },
        )

        await _on_f_workpaper_conclusion_saved(payload)

        # 只有 status 一条 set（conclusion 为 falsy 跳过）
        assert len(capturing_svc.calls) == 1
        assert capturing_svc.calls[0]["field"] == "status"
        assert capturing_svc.calls[0]["value"] == "in_progress"
        assert capturing_svc.calls[0]["scope"] == "f_procedure_status:F2-30"
        assert mock_f_session.committed is True

    @pytest.mark.asyncio
    async def test_conclusion_fallback_fields(
        self,
        mock_f_session,
        patch_f_session_factory,
        patch_f_invalidate_cache,
        sample_project_id,
        monkeypatch,
    ):
        """T5: conclusion 从 summary_conclusion / overall_conclusion / audit_conclusion 逐级 fallback."""
        from app.services.event_handlers_cycle_linkage import (
            _on_f_workpaper_conclusion_saved,
        )

        fallback_fields = [
            ("summary_conclusion", "汇总结论OK"),
            ("overall_conclusion", "整体结论无异常"),
            ("audit_conclusion", "审计结论合格"),
        ]

        for field_name, field_value in fallback_fields:
            svc = _CapturingFieldOverrideService()
            monkeypatch.setattr(
                "app.services.field_override_service.FieldOverrideService",
                lambda session, _svc=svc: _svc,
            )
            mock_f_session.committed = False

            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=sample_project_id,
                year=2025,
                extra={
                    "wp_code": "F2-55",
                    "parsed_data": {
                        field_name: field_value,
                        "status": "completed",
                    },
                },
            )

            await _on_f_workpaper_conclusion_saved(payload)

            # 应有 2 次 set（conclusion + status）
            assert len(svc.calls) == 2, f"{field_name} 应生成 2 次 set"
            fields = {c["field"]: c["value"] for c in svc.calls}
            assert fields["conclusion"] == field_value, (
                f"{field_name} conclusion 应为 {field_value}"
            )
            assert fields["status"] == "completed"
            assert mock_f_session.committed is True
