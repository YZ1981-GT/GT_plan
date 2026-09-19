"""confirmation-attachment-ocr-linkage — Property 1-12 契约测试骨架（Task 1.3）

所有 Property 先标 xfail（占位），随各波实现后逐一转绿：
- M1 (Wave 1): P1 撤回单调 / P2 留痕不可篡改 / P10 权限
- M2 (Wave 2): P9 回函件强绑发函件 / P12 附件计数无 N+1
- M3 (Wave 3): P3 差异+容差 / P4 主体名称不符 / P5 OCR 不自动落库 /
               P6 回填人工修正优先 / P7 回填状态建议
- M4 (Wave 4): P8 自动匹配唯一命中
- M0+全局: P11 向后兼容

测试框架：hypothesis max_examples=5（conftest 已注册 profile）

_Requirements: 10.1, 10.5_
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, assume, settings
from hypothesis import strategies as st

# ─── 共享常量 ─────────────────────────────────────────────────────────────────
ALL_STATUSES = ("pending", "sent", "returned", "matched", "discrepancy")
TERMINAL_STATUSES = ("matched", "discrepancy")
DEFAULT_TOLERANCE = Decimal("0.01")

# status rank（与 design 一致）
STATUS_RANK = {"pending": 0, "sent": 1, "returned": 2, "matched": 3, "discrepancy": 3}

# 撤回目标（与 design 一致）
REVERSAL_TARGETS = {
    "pending": set(),
    "sent": {"pending"},
    "returned": {"sent", "pending"},
    "matched": {"returned", "sent", "pending"},
    "discrepancy": {"returned", "sent", "pending"},
}


# ════════════════════════════════════════════════════════════════════════════
# Property 1: 撤回单调回退 (reverse monotonic)
# Validates: Requirements 1.1, 1.2, 1.3, 10.1
# ════════════════════════════════════════════════════════════════════════════


class TestProperty1ReverseMonotonic:
    """P1: 撤回目标必须 rank 严格更早；pending 不可退；前进/同级被拒。"""

    @given(
        current=st.sampled_from(list(ALL_STATUSES)),
        target=st.sampled_from(list(ALL_STATUSES)),
    )
    @settings(max_examples=5)
    def test_reversal_only_to_strictly_earlier_rank(self, current, target):
        """**Validates: Requirements 1.1, 1.2**
        撤回合法 ⟺ target ∈ REVERSAL_TARGETS[current] ∧ rank[target] < rank[current]
        """
        is_valid_reversal = target in REVERSAL_TARGETS[current]
        if is_valid_reversal:
            assert STATUS_RANK[target] < STATUS_RANK[current]
        # 反之：rank 不严格更早的不在 REVERSAL_TARGETS 中
        if STATUS_RANK[target] >= STATUS_RANK[current]:
            assert target not in REVERSAL_TARGETS[current]

    def test_pending_cannot_reverse(self):
        """**Validates: Requirements 1.3**
        pending 是初始态，不可再撤回。
        """
        assert REVERSAL_TARGETS["pending"] == set()

    def test_matched_can_reverse_to_pending(self):
        """**Validates: Requirements 1.1, 1.2**
        matched 可一步退到底至 pending。
        """
        assert "pending" in REVERSAL_TARGETS["matched"]
        assert "returned" in REVERSAL_TARGETS["matched"]
        assert "sent" in REVERSAL_TARGETS["matched"]


# ════════════════════════════════════════════════════════════════════════════
# Property 2: 撤回与回填留痕不可篡改 (action_log append-only)
# Validates: Requirements 1.4, 8.3, 8.5
# ════════════════════════════════════════════════════════════════════════════


class TestProperty2ActionLogAppendOnly:
    """P2: 每次 reverse/apply_reply/match_assign 写一条 log，表禁 UPDATE/DELETE。"""

    @pytest.mark.asyncio
    async def test_reverse_creates_log_entry(self):
        """**Validates: Requirements 1.4**

        reverse_status 执行后 confirmation_action_log 应含 1 条 action='reverse' 记录。
        """
        import uuid
        from unittest.mock import AsyncMock, MagicMock
        from datetime import datetime, timezone
        from decimal import Decimal

        # 构造 mock session + mock confirmation record
        mock_record = MagicMock()
        mock_record.id = uuid.uuid4()
        mock_record.project_id = uuid.uuid4()
        mock_record.status = "sent"
        mock_record.confirmed_amount = None
        mock_record.diff_amount = None
        mock_record.created_by = uuid.uuid4()
        mock_record.counterparty = "测试公司"
        mock_record.updated_at = datetime.now(timezone.utc)
        # reply_date 不存在时安全
        type(mock_record).reply_date = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record

        # 跟踪 db.add 调用来验证 log 被创建
        added_objects = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        def capture_add(obj):
            added_objects.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        # 屏蔽事件发布（event_bus 在函数体内局部导入，无需 mock——已被 try/except 包裹）
        from app.services.confirmation_service import reverse_status

        await reverse_status(
            db=mock_db,
            confirmation_id=mock_record.id,
            target_status="pending",
            reason="测试撤回",
            actor_user_id=mock_record.created_by,
        )

        # 验证：至少有一个 ConfirmationActionLog 被 add
        from app.models.confirmation_models import ConfirmationActionLog

        log_entries = [
            obj for obj in added_objects
            if isinstance(obj, ConfirmationActionLog)
        ]
        assert len(log_entries) == 1, (
            f"reverse_status 执行后应写入恰好 1 条 action_log，实际 {len(log_entries)} 条"
        )
        entry = log_entries[0]
        assert entry.action == "reverse"
        assert entry.from_status == "sent"
        assert entry.to_status == "pending"
        assert entry.confirmation_id == mock_record.id
        assert entry.reason == "测试撤回"

    @pytest.mark.xfail(reason="需真实 PG16：append-only 触发器拒 UPDATE")
    def test_action_log_rejects_update(self):
        """**Validates: Requirements 8.3**

        confirmation_action_log 的 DB 触发器应拒绝 UPDATE 操作。
        真实 PG16 集成测试：INSERT 一条后 UPDATE 应抛 RAISE EXCEPTION。
        """
        # 此测试需要真实 PostgreSQL 16 + evgov_forbid_update 触发器
        # SQLite in-memory 无法验证触发器行为
        assert False, "confirmation_action_log UPDATE 应被触发器拒绝（需真实 PG16）"

    @pytest.mark.xfail(reason="需真实 PG16：append-only 触发器拒 DELETE")
    def test_action_log_rejects_delete(self):
        """**Validates: Requirements 8.3**

        confirmation_action_log 的 DB 触发器应拒绝 DELETE 操作。
        真实 PG16 集成测试：INSERT 一条后 DELETE 应抛 RAISE EXCEPTION。
        """
        # 此测试需要真实 PostgreSQL 16 + evgov_forbid_delete 触发器
        # SQLite in-memory 无法验证触发器行为
        assert False, "confirmation_action_log DELETE 应被触发器拒绝（需真实 PG16）"


# ════════════════════════════════════════════════════════════════════════════
# Property 3: 差异计算与容差 (diff + tolerance ±0.01)
# Validates: Requirements 4.2, 4.6, 5.2, 10.2
# ════════════════════════════════════════════════════════════════════════════


class TestProperty3DiffAndTolerance:
    """P3: diff=book−confirmed；|diff|≤0.01 判相符；任一缺失不产生相符。"""

    @pytest.mark.xfail(reason="Task 4.1 extract_and_compare 实现后转绿")
    @given(
        book=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("9999999.99"), places=2),
        confirmed=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("9999999.99"), places=2),
    )
    @settings(max_examples=5)
    def test_diff_equals_book_minus_confirmed(self, book, confirmed):
        """**Validates: Requirements 4.2, 10.2**"""
        diff = book - confirmed
        if abs(diff) <= DEFAULT_TOLERANCE:
            verdict = "matched"
        else:
            verdict = "discrepancy"
        # 占位：extract_and_compare 应产出同样的 verdict
        assert False, f"extract_and_compare({book},{confirmed}) 应产出 verdict={verdict}"

    @pytest.mark.xfail(reason="Task 4.1 extract_and_compare 实现后转绿")
    @given(
        book=st.one_of(st.none(), st.just(Decimal("0"))),
    )
    @settings(max_examples=5)
    def test_missing_amount_never_matched(self, book):
        """**Validates: Requirements 4.6**
        book_amount 或 confirmed_amount 任一缺失，不产生"相符"结论。
        """
        assert False, "任一金额缺失时 verdict 不应为 matched"


# ════════════════════════════════════════════════════════════════════════════
# Property 4: 主体名称不符预警 (counterparty mismatch)
# Validates: Requirements 4.3
# ════════════════════════════════════════════════════════════════════════════


class TestProperty4CounterpartyMismatch:
    """P4: OCR 主体名称与 counterparty 不一致时 counterparty_mismatch=true。"""

    @pytest.mark.xfail(reason="Task 4.1 extract_and_compare 实现后转绿")
    @given(
        entity_a=st.text(min_size=2, max_size=10),
        entity_b=st.text(min_size=2, max_size=10),
    )
    @settings(max_examples=5)
    def test_mismatch_flagged_when_names_differ(self, entity_a, entity_b):
        """**Validates: Requirements 4.3**
        名称不一致时预警，不因金额相符而掩盖。
        """
        assume(entity_a != entity_b)
        assert False, "名称不一致时应标 counterparty_mismatch=true"


# ════════════════════════════════════════════════════════════════════════════
# Property 5: OCR 不自动落库 (governed=false, no auto-write)
# Validates: Requirements 4.4, 4.5, 5.3, 10.3
# ════════════════════════════════════════════════════════════════════════════


class TestProperty5OcrNoAutoWrite:
    """P5: extract_and_compare 恒 governed=false，无 apply_reply 时台账不变。"""

    @pytest.mark.xfail(reason="Task 4.1 extract_and_compare 实现后转绿")
    def test_extract_result_always_governed_false(self):
        """**Validates: Requirements 4.4, 10.3**"""
        assert False, "extract_and_compare 返回值恒含 governed=False"

    @pytest.mark.xfail(reason="Task 4.1 extract_and_compare 实现后转绿")
    def test_no_apply_reply_means_no_台账_change(self):
        """**Validates: Requirements 4.5, 5.3**
        仅 extract_and_compare（不调 apply_reply）时，confirmed_amount/status 不变。
        """
        assert False, "OCR 抽取不应改变台账 confirmed_amount/status"


# ════════════════════════════════════════════════════════════════════════════
# Property 6: 回填人工修正优先 + 双值留痕 (apply_reply human override)
# Validates: Requirements 5.1, 5.4, 5.5, 10.3
# ════════════════════════════════════════════════════════════════════════════


class TestProperty6ApplyReplyHumanOverride:
    """P6: apply_reply 以人工确认/修正值落库；留痕保留 OCR 原值与最终值。"""

    @pytest.mark.xfail(reason="Task 4.2 apply_reply 实现后转绿")
    @given(
        ocr_amount=st.decimals(min_value=Decimal("100"), max_value=Decimal("999999"), places=2),
        human_amount=st.decimals(min_value=Decimal("100"), max_value=Decimal("999999"), places=2),
    )
    @settings(max_examples=5)
    def test_human_override_takes_precedence(self, ocr_amount, human_amount):
        """**Validates: Requirements 5.1, 5.4**"""
        assume(ocr_amount != human_amount)
        assert False, "apply_reply 应以 human_amount 落库非 ocr_amount"

    @pytest.mark.xfail(reason="Task 4.2 apply_reply 实现后转绿")
    def test_log_preserves_ocr_original_and_final_value(self):
        """**Validates: Requirements 5.5, 10.3**
        action_log.ocr_original 与 final_value 同时保留。
        """
        assert False, "action_log 应同时含 ocr_original 与 final_value"


# ════════════════════════════════════════════════════════════════════════════
# Property 7: 回填状态建议由用户确认 (status suggestion vs user input)
# Validates: Requirements 5.2
# ════════════════════════════════════════════════════════════════════════════


class TestProperty7StatusSuggestionUserConfirm:
    """P7: 容差内建议 matched，容差外建议 discrepancy，但最终以入参为准。"""

    @pytest.mark.xfail(reason="Task 4.2 apply_reply 实现后转绿")
    @given(
        target_status=st.sampled_from(["matched", "discrepancy"]),
    )
    @settings(max_examples=5)
    def test_apply_reply_respects_user_target_status(self, target_status):
        """**Validates: Requirements 5.2**
        apply_reply 的 target_status 入参=最终状态，不由系统自动定终态。
        """
        assert False, "apply_reply 应用入参 target_status 作最终状态"


# ════════════════════════════════════════════════════════════════════════════
# Property 8: 自动匹配唯一命中才落 (auto_match single hit only)
# Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 10.4
# ════════════════════════════════════════════════════════════════════════════


class TestProperty8AutoMatchSingleHit:
    """P8: 唯一命中才挂载+绑发函件；多义/无命中不落台账正式结论。"""

    @pytest.mark.xfail(reason="Task 5.1 auto_match 实现后转绿")
    def test_single_hit_attaches(self):
        """**Validates: Requirements 6.2, 10.4**"""
        assert False, "唯一命中时应挂载回函件到该函证"

    @pytest.mark.xfail(reason="Task 5.1 auto_match 实现后转绿")
    def test_multiple_hits_returns_candidates(self):
        """**Validates: Requirements 6.3**"""
        assert False, "多义时应返回候选列表不自动挂载"

    @pytest.mark.xfail(reason="Task 5.1 auto_match 实现后转绿")
    def test_no_hit_enters_queue(self):
        """**Validates: Requirements 6.4**"""
        assert False, "无命中时应入人工匹配队列"

    @pytest.mark.xfail(reason="Task 5.1 auto_match 实现后转绿")
    def test_match_evidence_recorded(self):
        """**Validates: Requirements 6.5**"""
        assert False, "匹配命中依据应记入 match_evidence 可解释"


# ════════════════════════════════════════════════════════════════════════════
# Property 9: 回函件强绑发函件 (inbound must pair outbound)
# Validates: Requirements 3.5, 3.6
# ════════════════════════════════════════════════════════════════════════════


class TestProperty9InboundPairsOutbound:
    """P9: role=inbound 必有 paired_outbound_attachment_id，无发函件不得挂回函件。"""

    @pytest.mark.xfail(reason="Task 3.1 link_attachment 实现后转绿")
    def test_inbound_requires_paired_outbound(self):
        """**Validates: Requirements 3.5**"""
        assert False, "role=inbound 时 paired_outbound_attachment_id 必填"

    @pytest.mark.xfail(reason="Task 3.1 link_attachment 实现后转绿")
    def test_no_outbound_blocks_inbound(self):
        """**Validates: Requirements 3.5**
        无发函件时不得单独挂回函件。
        """
        assert False, "无发函件时挂回函件应被拒绝"

    @pytest.mark.xfail(reason="Task 3.1 link_attachment 实现后转绿")
    def test_single_outbound_auto_binds(self):
        """**Validates: Requirements 3.6**
        单份发函件时，回函件自动绑定到它。
        """
        assert False, "单份发函件时回函件应自动绑定"


# ════════════════════════════════════════════════════════════════════════════
# Property 10: 权限门控 (permission gating)
# Validates: Requirements 1.6, 8.1, 8.2, 10.6
# ════════════════════════════════════════════════════════════════════════════


class TestProperty10PermissionGating:
    """P10: 撤回终态需现场经理+；低权限执行受限动作被拒且无副作用。"""

    @pytest.mark.asyncio
    async def test_reverse_terminal_requires_manager(self):
        """**Validates: Requirements 1.6, 8.2**

        当前状态为终态（matched/discrepancy）时，低权限用户（如审计助理）
        调用撤回端点应被 403 拒绝。
        """
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch
        from fastapi import HTTPException

        # 模拟低权限用户（审计助理 = assistant）
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.role = "assistant"

        # 模拟当前状态为终态 matched
        mock_confirmation = {
            "id": str(uuid.uuid4()),
            "status": "matched",
            "project_id": str(uuid.uuid4()),
        }

        mock_db = AsyncMock()

        with patch(
            "app.routers.confirmations.confirmation_service.get_confirmation",
            new_callable=AsyncMock,
            return_value=mock_confirmation,
        ):
            from app.routers.confirmations import reverse_confirmation, ReverseRequest

            body = ReverseRequest(target_status="returned", reason="测试低权限")

            with pytest.raises(HTTPException) as exc_info:
                await reverse_confirmation(
                    project_id=mock_confirmation["project_id"],
                    confirmation_id=mock_confirmation["id"],
                    body=body,
                    db=mock_db,
                    user=mock_user,
                )

            assert exc_info.value.status_code == 403
            assert "经理" in exc_info.value.detail or "权限" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_low_privilege_rejection_has_no_side_effect(self):
        """**Validates: Requirements 8.2, 10.6**

        低权限被拒后台账状态不应变化（reverse_status 从未被调用）。
        """
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch, call
        from fastapi import HTTPException

        # 模拟低权限用户
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.role = "assistant"

        confirmation_id = str(uuid.uuid4())
        project_id = str(uuid.uuid4())

        mock_confirmation = {
            "id": confirmation_id,
            "status": "discrepancy",  # 终态
            "project_id": project_id,
        }

        mock_db = AsyncMock()

        # 跟踪 reverse_status 是否被调用
        mock_reverse = AsyncMock()

        with patch(
            "app.routers.confirmations.confirmation_service.get_confirmation",
            new_callable=AsyncMock,
            return_value=mock_confirmation,
        ), patch(
            "app.routers.confirmations.confirmation_service.reverse_status",
            mock_reverse,
        ):
            from app.routers.confirmations import reverse_confirmation, ReverseRequest

            body = ReverseRequest(target_status="pending", reason="低权限测试")

            with pytest.raises(HTTPException) as exc_info:
                await reverse_confirmation(
                    project_id=project_id,
                    confirmation_id=confirmation_id,
                    body=body,
                    db=mock_db,
                    user=mock_user,
                )

            assert exc_info.value.status_code == 403

        # 核心断言：reverse_status 从未被调用 = 无副作用
        mock_reverse.assert_not_called()
        # db.commit 也不应被调用（状态没变）
        mock_db.commit.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# Property 11: 向后兼容 additive (backward compat)
# Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 10.5
# ════════════════════════════════════════════════════════════════════════════


class TestProperty11BackwardCompat:
    """P11: 未用新功能时既有端点逐字节等价；历史空值兼容。"""

    @pytest.mark.xfail(reason="Task 6.1 全量零回归门转绿")
    def test_existing_create_unchanged(self):
        """**Validates: Requirements 9.1**"""
        assert False, "未用新功能时 create_confirmation 行为不变"

    @pytest.mark.xfail(reason="Task 6.1 全量零回归门转绿")
    def test_existing_transition_unchanged(self):
        """**Validates: Requirements 9.1**"""
        assert False, "未用新功能时 transition_status(前进)行为不变"

    @pytest.mark.xfail(reason="Task 6.1 全量零回归门转绿")
    def test_sync_hub_from_summary_unchanged(self):
        """**Validates: Requirements 9.3**"""
        assert False, "syncHubFromSummary 行为不变"

    @pytest.mark.xfail(reason="Task 6.1 全量零回归门转绿")
    def test_extract_confirmation_reply_unchanged(self):
        """**Validates: Requirements 9.4**"""
        assert False, "extract_confirmation_reply 行为不变"

    @pytest.mark.xfail(reason="Task 6.1 零回归门转绿")
    def test_historical_records_display_without_error(self):
        """**Validates: Requirements 9.2**
        历史记录无 sent_date/reply_date/link 时正常展示空值。
        """
        assert False, "历史记录空新字段应兼容展示"


# ════════════════════════════════════════════════════════════════════════════
# Property 12: 附件计数批量无 N+1 (bulk count single query)
# Validates: Requirements 3.4
# ════════════════════════════════════════════════════════════════════════════


class TestProperty12BulkCountNoNPlusOne:
    """P12: list_attachment_counts(ids[]) 单次查询。"""

    @pytest.mark.xfail(reason="Task 3.1 list_attachment_counts 实现后转绿")
    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=5)
    def test_count_query_does_not_scale_linearly(self, n):
        """**Validates: Requirements 3.4**
        查询次数不随函证数线性增加。
        """
        assert False, f"list_attachment_counts({n}条) 应为单次查询"
