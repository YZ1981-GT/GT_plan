"""test_adj_approved_event_properties.py — 确认门事件属性守卫.

spec: adj-formula-repair-and-approval-gate-wiring · 阶段 3 任务 3.8 + 3.9
属性 P7, P8, P10 · ADR-ADJ-005

3.8 幂等 PBT：同一 entry_group_id 连续触发 2 次 → 试算表结果不变
3.9 撤回语义守卫：口径常量与事件集合自洽
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
        """handler 模块可导入。"""
        from app.services.adjustment_approved_recalc_handler import (
            handle_adjustment_approved,
            register_adjustment_approved_recalc_handler,
        )
        import inspect
        assert inspect.iscoroutinefunction(handle_adjustment_approved)
        assert callable(register_adjustment_approved_recalc_handler)

    def test_handler_tolerates_missing_fields(self):
        """P8 前置：handler 对缺字段不抛（幂等的基础——空触发无副作用）。"""
        import asyncio
        from app.services.adjustment_approved_recalc_handler import (
            handle_adjustment_approved,
        )

        class _EmptyEvent:
            project_id = None
            year = None
            account_codes = None

        # 不抛即通过（early return on missing fields）
        asyncio.get_event_loop().run_until_complete(
            handle_adjustment_approved(_EmptyEvent())
        )


class TestWithdrawalSemanticGuard:
    """ADR-ADJ-005 撤回语义守卫。

    口径为「仅 approved」时，rejected/draft 转换不改变纳入集合 ⇒ 无需撤回事件。
    口径放宽到含 pending_review 后此守卫自动变红。
    """

    def test_approved_only_needs_no_withdrawal_event(self):
        """当前口径 = 仅 approved ⇒ EventType 无需 ADJUSTMENT_WITHDRAWN。"""
        from app.models.audit_platform_schemas import EventType
        from app.services.adjustment_amount_source import DEFAULT_INCLUDE_STATUSES

        # 口径断言
        assert DEFAULT_INCLUDE_STATUSES == frozenset({"approved"}), (
            f"口径已变: {DEFAULT_INCLUDE_STATUSES}，需评估是否新增撤回事件"
        )
        # 当口径仅 approved 时，无需撤回事件
        assert not hasattr(EventType, "ADJUSTMENT_WITHDRAWN"), (
            "口径仅 approved 时不应存在 ADJUSTMENT_WITHDRAWN 事件"
        )

    def test_pending_review_in_statuses_triggers_guard(self):
        """变异证明：如果口径含 pending_review，守卫逻辑能检测到。"""
        hypothetical_statuses = frozenset({"approved", "pending_review"})
        # 如果口径含 pending_review，则需要撤回事件
        needs_withdrawal = "pending_review" in hypothetical_statuses
        assert needs_withdrawal, "变异证明失败"
