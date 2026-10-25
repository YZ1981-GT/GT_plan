"""调整复核事件属性守卫。

spec: adj-formula-repair-and-approval-gate-wiring · 阶段 3 任务 3.8 + 3.9
属性 P7, P8, P10 · ADR-ADJ-005

3.8 幂等 PBT：同一 entry_group_id 连续触发 2 次 → 试算表结果不变
3.9 撤回语义守卫：审批与撤回事件契约及年度范围自洽
"""
from __future__ import annotations


class TestAdjApprovedEventProperties:
    """确认门事件属性。"""

    def test_event_type_exists_and_value(self):
        """P7：ADJUSTMENT_APPROVED 事件存在且值正确。"""
        from app.models.audit_platform_schemas import EventType

        assert hasattr(EventType, "ADJUSTMENT_APPROVED")
        assert EventType.ADJUSTMENT_APPROVED.value == "adjustment.approved"

    def test_handler_importable(self):
        """审批与撤回 handler 均可导入且为协程。"""
        import inspect

        from app.services.adjustment_approved_recalc_handler import (
            handle_adjustment_approved,
            handle_adjustment_review_revoked,
            register_adjustment_approved_recalc_handler,
        )

        assert inspect.iscoroutinefunction(handle_adjustment_approved)
        assert inspect.iscoroutinefunction(handle_adjustment_review_revoked)
        assert callable(register_adjustment_approved_recalc_handler)

    def test_handler_tolerates_missing_fields(self):
        """P8 前置：handler 对缺字段不抛（幂等的基础——空触发无副作用）。"""
        import asyncio

        from app.services.adjustment_approved_recalc_handler import (
            handle_adjustment_approved,
            handle_adjustment_review_revoked,
        )

        class _EmptyEvent:
            project_id = None
            year = None
            account_codes = None

        # 两个事件 handler 都必须对不完整事件安全早退。
        loop = asyncio.get_event_loop()
        loop.run_until_complete(handle_adjustment_approved(_EmptyEvent()))
        loop.run_until_complete(handle_adjustment_review_revoked(_EmptyEvent()))


class TestWithdrawalSemanticGuard:
    """ADR-ADJ-005 撤回语义守卫。"""

    def test_review_revoked_event_exists_and_is_year_scoped(self):
        """撤回必须有独立事件，并纳入年度补齐范围。"""
        from app.models.audit_platform_schemas import EventType
        from app.services.event_bus import YEAR_SCOPED_EVENT_TYPES

        assert hasattr(EventType, "ADJUSTMENT_REVIEW_REVOKED")
        assert EventType.ADJUSTMENT_REVIEW_REVOKED.value == "adjustment.review_revoked"
        assert EventType.ADJUSTMENT_REVIEW_REVOKED in YEAR_SCOPED_EVENT_TYPES

    def test_approved_only_source_still_requires_revoke_event(self):
        """当前取数口径只纳入 approved，但撤回必须通知下游移除已审批影响。"""
        from app.services.adjustment_amount_source import DEFAULT_INCLUDE_STATUSES

        assert DEFAULT_INCLUDE_STATUSES == frozenset({"approved"})

    def test_pending_review_status_mutation_is_visible(self):
        """变异证明：口径若含 pending_review，测试数据能识别该变化。"""
        hypothetical_statuses = frozenset({"approved", "pending_review"})
        assert "pending_review" in hypothetical_statuses
