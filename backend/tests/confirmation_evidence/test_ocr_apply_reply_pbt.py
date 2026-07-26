"""confirmation-attachment-ocr-linkage — Property 3/4/5/6/7 PBT（Task 4.5）

OCR 识别 + 比对 + 人工确认回填 的 Property-Based Testing。

- Property 3: 差异计算与容差（diff + ±0.01，任一缺失不判相符）
- Property 4: 主体名称不符预警不被金额相符掩盖
- Property 5: OCR 结果不自动落库（governed=false，无 apply_reply 时台账不变）
- Property 6: 回填人工修正优先 + 双值留痕
- Property 7: 回填状态建议由用户确认不自动定终态

测试框架：hypothesis max_examples=5（mock-based 纯逻辑测试）

_Requirements: 4.2, 4.3, 4.4, 5.1, 5.2, 5.4, 10.2, 10.3_
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, assume, settings
from hypothesis import strategies as st


# ─── 共享常量 ─────────────────────────────────────────────────────────────────
DEFAULT_TOLERANCE = Decimal("0.01")


# ─── 共享 fixtures / helpers ──────────────────────────────────────────────────


def _make_mock_db(
    *,
    confirmation=None,
    attachment=None,
    link=None,
):
    """构造 mock AsyncSession，按需配置 get/execute 返回值。"""
    db = AsyncMock()

    async def mock_get(model, id_val):
        from app.models.confirmation_models import Confirmation, ConfirmationAttachmentLink
        from app.models.attachment_models import Attachment

        if model is Confirmation and confirmation is not None:
            return confirmation
        if model is Attachment and attachment is not None:
            return attachment
        if model is ConfirmationAttachmentLink and link is not None:
            return link
        return None

    db.get = AsyncMock(side_effect=mock_get)
    db.flush = AsyncMock()
    db.add = MagicMock()

    return db


def _make_confirmation(
    *,
    book_amount=None,
    counterparty=None,
    confirmed_amount=None,
    status="sent",
    diff_amount=None,
):
    """构造 mock Confirmation 记录。"""
    c = MagicMock()
    c.id = uuid.uuid4()
    c.project_id = uuid.uuid4()
    c.book_amount = book_amount
    c.counterparty = counterparty
    c.confirmed_amount = confirmed_amount
    c.status = status
    c.diff_amount = diff_amount
    c.reply_date = None
    return c


def _make_attachment(*, ocr_fields_cache=None):
    """构造 mock Attachment。"""
    a = MagicMock()
    a.id = uuid.uuid4()
    a.ocr_fields_cache = ocr_fields_cache
    a.ocr_status = "completed"
    return a


def _make_link(*, confirmation_id, attachment_id):
    """构造 mock ConfirmationAttachmentLink。"""
    link = MagicMock()
    link.id = uuid.uuid4()
    link.confirmation_id = confirmation_id
    link.attachment_id = attachment_id
    link.role = "inbound"
    return link


# ════════════════════════════════════════════════════════════════════════════
# Property 3: 差异计算与容差
# Validates: Requirements 4.2, 4.6, 5.2, 10.2
# ════════════════════════════════════════════════════════════════════════════


class TestProperty3DiffAndTolerance:
    """P3: diff=book−confirmed；|diff|≤0.01 判相符；任一缺失不产生相符。"""

    @given(
        book=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("9999999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        reply=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("9999999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_diff_calculation_and_tolerance(self, book, reply):
        """**Validates: Requirements 4.2, 10.2**

        extract_and_compare 的 diff = book_amount − reply_amount；
        |diff| ≤ 0.01 → matched，否则 → discrepancy。
        """
        from app.services.confirmation_evidence_service import extract_and_compare

        confirmation = _make_confirmation(
            book_amount=float(book), counterparty="测试公司"
        )
        attachment = _make_attachment()
        link = _make_link(
            confirmation_id=confirmation.id, attachment_id=attachment.id
        )

        # Mock OCR 返回指定金额
        ocr_result = {
            "reply_amount": float(reply),
            "reply_date": "2025-06-30",
            "reply_entity": "测试公司",
            "confidence": "high",
        }

        db = _make_mock_db(
            confirmation=confirmation, attachment=attachment, link=link
        )

        # Mock execute 返回 link
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.confirmation_evidence_service.AttachmentService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.extract_confirmation_reply = AsyncMock(return_value=ocr_result)

            result = await extract_and_compare(db, attachment.id)

        # 验证 diff 计算
        expected_diff = float(Decimal(str(float(book))) - Decimal(str(float(reply))))
        assert result["diff"] == pytest.approx(expected_diff, abs=1e-10)

        # 验证容差判定
        if abs(expected_diff) <= float(DEFAULT_TOLERANCE):
            assert result["match_verdict"] == "matched"
        else:
            assert result["match_verdict"] == "discrepancy"

    @given(
        reply=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("9999999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_missing_book_amount_never_matched(self, reply):
        """**Validates: Requirements 4.6**

        book_amount 缺失时不产生"相符"结论。
        """
        from app.services.confirmation_evidence_service import extract_and_compare

        # book_amount = None
        confirmation = _make_confirmation(
            book_amount=None, counterparty="测试公司"
        )
        attachment = _make_attachment()
        link = _make_link(
            confirmation_id=confirmation.id, attachment_id=attachment.id
        )

        ocr_result = {
            "reply_amount": float(reply),
            "reply_date": "2025-06-30",
            "reply_entity": "测试公司",
            "confidence": "high",
        }

        db = _make_mock_db(
            confirmation=confirmation, attachment=attachment, link=link
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.confirmation_evidence_service.AttachmentService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.extract_confirmation_reply = AsyncMock(return_value=ocr_result)

            result = await extract_and_compare(db, attachment.id)

        # book_amount 缺失 → 永不 matched
        assert result["match_verdict"] != "matched"
        assert result["match_verdict"] == "low_confidence"
        assert result["diff"] is None

    @given(
        book=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("9999999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_missing_reply_amount_never_matched(self, book):
        """**Validates: Requirements 4.6**

        reply_amount (OCR 抽取) 缺失时不产生"相符"结论。
        """
        from app.services.confirmation_evidence_service import extract_and_compare

        confirmation = _make_confirmation(
            book_amount=float(book), counterparty="测试公司"
        )
        attachment = _make_attachment()
        link = _make_link(
            confirmation_id=confirmation.id, attachment_id=attachment.id
        )

        # OCR 返回 reply_amount=None（识别失败）
        ocr_result = {
            "reply_amount": None,
            "reply_date": None,
            "reply_entity": "测试公司",
            "confidence": "low",
        }

        db = _make_mock_db(
            confirmation=confirmation, attachment=attachment, link=link
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.confirmation_evidence_service.AttachmentService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.extract_confirmation_reply = AsyncMock(return_value=ocr_result)

            result = await extract_and_compare(db, attachment.id)

        # reply_amount 缺失 → 永不 matched
        assert result["match_verdict"] != "matched"
        assert result["match_verdict"] == "low_confidence"
        assert result["diff"] is None


# ════════════════════════════════════════════════════════════════════════════
# Property 4: 主体名称不符预警不被金额相符掩盖
# Validates: Requirements 4.3
# ════════════════════════════════════════════════════════════════════════════


class TestProperty4CounterpartyMismatch:
    """P4: 金额相符(matched)时,名称不一致仍标 counterparty_mismatch=true。"""

    @given(
        amount=st.decimals(
            min_value=Decimal("100"),
            max_value=Decimal("999999"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        entity_a=st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=2,
            max_size=10,
        ),
        entity_b=st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=2,
            max_size=10,
        ),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_mismatch_not_masked_by_amount_match(self, amount, entity_a, entity_b):
        """**Validates: Requirements 4.3**

        即使金额在容差内(matched)，主体名称不一致时
        counterparty_mismatch=true 仍然存在。
        """
        assume(entity_a.strip() != entity_b.strip())
        assume(len(entity_a.strip()) > 0 and len(entity_b.strip()) > 0)

        from app.services.confirmation_evidence_service import extract_and_compare

        # 金额完全相等 → 一定在容差内 → matched
        confirmation = _make_confirmation(
            book_amount=float(amount), counterparty=entity_a
        )
        attachment = _make_attachment()
        link = _make_link(
            confirmation_id=confirmation.id, attachment_id=attachment.id
        )

        ocr_result = {
            "reply_amount": float(amount),  # 完全相等，金额一定 matched
            "reply_date": "2025-06-30",
            "reply_entity": entity_b,  # 名称不同
            "confidence": "high",
        }

        db = _make_mock_db(
            confirmation=confirmation, attachment=attachment, link=link
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.confirmation_evidence_service.AttachmentService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.extract_confirmation_reply = AsyncMock(return_value=ocr_result)

            result = await extract_and_compare(db, attachment.id)

        # 核心断言：金额 matched 不掩盖名称不符预警
        assert result["match_verdict"] == "matched"
        assert result["counterparty_mismatch"] is True


# ════════════════════════════════════════════════════════════════════════════
# Property 5: OCR 结果不自动落库
# Validates: Requirements 4.4, 4.5, 5.3, 10.3
# ════════════════════════════════════════════════════════════════════════════


class TestProperty5OcrNoAutoWrite:
    """P5: extract_and_compare 恒 governed=false/requires_human_confirmation=true，
    仅写 ocr_fields_cache，无 apply_reply 时 confirmations 不变。"""

    @given(
        book=st.decimals(
            min_value=Decimal("100"),
            max_value=Decimal("999999"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        reply=st.decimals(
            min_value=Decimal("100"),
            max_value=Decimal("999999"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_governed_always_false(self, book, reply):
        """**Validates: Requirements 4.4, 10.3**

        extract_and_compare 返回值恒含 governed=False, requires_human_confirmation=True。
        """
        from app.services.confirmation_evidence_service import extract_and_compare

        original_status = "sent"
        original_confirmed = None

        confirmation = _make_confirmation(
            book_amount=float(book),
            counterparty="测试公司",
            status=original_status,
            confirmed_amount=original_confirmed,
        )
        attachment = _make_attachment()
        link = _make_link(
            confirmation_id=confirmation.id, attachment_id=attachment.id
        )

        ocr_result = {
            "reply_amount": float(reply),
            "reply_date": "2025-06-30",
            "reply_entity": "测试公司",
            "confidence": "high",
        }

        db = _make_mock_db(
            confirmation=confirmation, attachment=attachment, link=link
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.confirmation_evidence_service.AttachmentService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.extract_confirmation_reply = AsyncMock(return_value=ocr_result)

            result = await extract_and_compare(db, attachment.id)

        # P5 核心：governed 恒 false
        assert result["governed"] is False
        assert result["requires_human_confirmation"] is True

        # 台账 confirmed_amount/status 不变（OCR 不自动落库）
        assert confirmation.confirmed_amount == original_confirmed
        assert confirmation.status == original_status

    @given(
        book=st.decimals(
            min_value=Decimal("100"),
            max_value=Decimal("999999"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_no_apply_reply_leaves_confirmation_unchanged(self, book):
        """**Validates: Requirements 4.5, 5.3**

        仅调 extract_and_compare（不调 apply_reply）时，
        confirmation.confirmed_amount 和 confirmation.status 不变。
        """
        from app.services.confirmation_evidence_service import extract_and_compare

        original_status = "returned"
        original_confirmed_amount = 12345.67

        confirmation = _make_confirmation(
            book_amount=float(book),
            counterparty="测试公司",
            status=original_status,
            confirmed_amount=original_confirmed_amount,
        )
        attachment = _make_attachment()
        link = _make_link(
            confirmation_id=confirmation.id, attachment_id=attachment.id
        )

        ocr_result = {
            "reply_amount": 99999.99,
            "reply_date": "2025-06-30",
            "reply_entity": "OCR识别公司",
            "confidence": "high",
        }

        db = _make_mock_db(
            confirmation=confirmation, attachment=attachment, link=link
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = link
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.confirmation_evidence_service.AttachmentService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.extract_confirmation_reply = AsyncMock(return_value=ocr_result)

            await extract_and_compare(db, attachment.id)

        # 核心：OCR 后台账字段不变
        assert confirmation.confirmed_amount == original_confirmed_amount
        assert confirmation.status == original_status


# ════════════════════════════════════════════════════════════════════════════
# Property 6: 回填人工修正优先 + 双值留痕
# Validates: Requirements 5.1, 5.4, 5.5, 10.3
# ════════════════════════════════════════════════════════════════════════════


class TestProperty6ApplyReplyHumanOverride:
    """P6: apply_reply 落库用人工确认/修正后的值；
    confirmation_action_log.ocr_original 与 final_value 同时保留。"""

    @given(
        ocr_amount=st.floats(min_value=100.0, max_value=999999.0, allow_nan=False, allow_infinity=False),
        human_amount=st.floats(min_value=100.0, max_value=999999.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_human_override_takes_precedence(self, ocr_amount, human_amount):
        """**Validates: Requirements 5.1, 5.4**

        apply_reply 以人工确认值(confirmed_amount入参)落库，不用 OCR 原值。
        """
        assume(abs(ocr_amount - human_amount) > 0.02)  # 确保二者不同

        from app.services.confirmation_evidence_service import apply_reply

        book_amount = 50000.0
        confirmation = _make_confirmation(
            book_amount=book_amount,
            counterparty="测试公司",
            status="returned",
        )
        # OCR 原值保存在 attachment.ocr_fields_cache
        attachment = _make_attachment(
            ocr_fields_cache={"reply_amount": ocr_amount, "confidence": "medium"}
        )

        db = _make_mock_db(confirmation=confirmation, attachment=attachment)

        # 跟踪 add 的对象
        added_objects = []
        db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

        # patch event_bus 避免副作用
        # event_bus 在 apply_reply 函数体内局部导入，patch 其源模块
        with patch(
            "app.services.event_bus.event_bus",
            new=MagicMock(publish_immediate=AsyncMock()),
        ):
            result = await apply_reply(
                db,
                confirmation_id=confirmation.id,
                attachment_id=attachment.id,
                confirmed_amount=human_amount,
                reply_date="2025-06-30",
                target_status="matched",
                actor_user_id=uuid.uuid4(),
            )

        # 核心：落库的是人工值非 OCR 原值
        assert confirmation.confirmed_amount == human_amount
        assert result["confirmed_amount"] == human_amount

    @given(
        ocr_amount=st.floats(min_value=100.0, max_value=999999.0, allow_nan=False, allow_infinity=False),
        human_amount=st.floats(min_value=100.0, max_value=999999.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_action_log_preserves_both_values(self, ocr_amount, human_amount):
        """**Validates: Requirements 5.5, 10.3**

        confirmation_action_log 同时保留 ocr_original 与 final_value。
        """
        assume(abs(ocr_amount - human_amount) > 0.02)

        from app.services.confirmation_evidence_service import apply_reply
        from app.models.confirmation_models import ConfirmationActionLog

        confirmation = _make_confirmation(
            book_amount=50000.0,
            counterparty="测试公司",
            status="returned",
        )
        attachment = _make_attachment(
            ocr_fields_cache={"reply_amount": ocr_amount, "confidence": "high"}
        )

        db = _make_mock_db(confirmation=confirmation, attachment=attachment)

        added_objects = []
        db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

        with patch(
            "app.services.event_bus.event_bus",
            new=MagicMock(publish_immediate=AsyncMock()),
        ):
            await apply_reply(
                db,
                confirmation_id=confirmation.id,
                attachment_id=attachment.id,
                confirmed_amount=human_amount,
                reply_date="2025-06-30",
                target_status="discrepancy",
                actor_user_id=uuid.uuid4(),
            )

        # 找到 action_log 记录
        log_entries = [
            obj for obj in added_objects if isinstance(obj, ConfirmationActionLog)
        ]
        assert len(log_entries) == 1

        log = log_entries[0]
        assert log.action == "apply_reply"

        # ocr_original 保留原值
        assert log.ocr_original is not None
        assert log.ocr_original["reply_amount"] == ocr_amount

        # final_value 保留最终落库值
        assert log.final_value is not None
        assert log.final_value["confirmed_amount"] == human_amount


# ════════════════════════════════════════════════════════════════════════════
# Property 7: 回填状态建议由用户确认不自动定终态
# Validates: Requirements 5.2
# ════════════════════════════════════════════════════════════════════════════


class TestProperty7StatusSuggestionUserConfirm:
    """P7: 差异容差内建议 matched、容差外建议 discrepancy，
    但最终 status 以 apply_reply 入参 target_status 为准。"""

    @given(
        book=st.floats(min_value=1000.0, max_value=99999.0, allow_nan=False, allow_infinity=False),
        confirmed=st.floats(min_value=1000.0, max_value=99999.0, allow_nan=False, allow_infinity=False),
        target_status=st.sampled_from(["matched", "discrepancy"]),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_user_target_status_overrides_suggestion(
        self, book, confirmed, target_status
    ):
        """**Validates: Requirements 5.2**

        无论系统建议是 matched 还是 discrepancy，
        最终落库的 status 由 target_status 入参决定（用户确认）。
        """
        from app.services.confirmation_evidence_service import apply_reply

        confirmation = _make_confirmation(
            book_amount=book, counterparty="测试公司", status="returned"
        )
        attachment = _make_attachment(
            ocr_fields_cache={"reply_amount": confirmed}
        )

        db = _make_mock_db(confirmation=confirmation, attachment=attachment)
        db.add = MagicMock()

        with patch(
            "app.services.event_bus.event_bus",
            new=MagicMock(publish_immediate=AsyncMock()),
        ):
            result = await apply_reply(
                db,
                confirmation_id=confirmation.id,
                attachment_id=attachment.id,
                confirmed_amount=confirmed,
                reply_date="2025-06-30",
                target_status=target_status,
                actor_user_id=uuid.uuid4(),
            )

        # 核心断言：实际 status = 用户入参，非系统建议
        assert confirmation.status == target_status
        assert result["actual_status"] == target_status

        # 系统建议独立计算（不影响最终结果）
        diff = float(Decimal(str(book)) - Decimal(str(confirmed)))
        if abs(diff) <= float(DEFAULT_TOLERANCE):
            assert result["suggested_status"] == "matched"
        else:
            assert result["suggested_status"] == "discrepancy"

    @pytest.mark.asyncio
    async def test_within_tolerance_but_user_says_discrepancy(self):
        """**Validates: Requirements 5.2**

        金额差在容差内(系统建议matched)，但用户传 target_status='discrepancy'
        → 最终落库 status = discrepancy（用户确认为准）。
        """
        from app.services.confirmation_evidence_service import apply_reply

        # book=1000.00, confirmed=1000.005 → diff=0.005 < 0.01 → 系统建议 matched
        book_amount = 1000.00
        confirmed_amount = 999.995

        confirmation = _make_confirmation(
            book_amount=book_amount, counterparty="测试公司", status="returned"
        )
        attachment = _make_attachment(
            ocr_fields_cache={"reply_amount": confirmed_amount}
        )

        db = _make_mock_db(confirmation=confirmation, attachment=attachment)
        db.add = MagicMock()

        with patch(
            "app.services.event_bus.event_bus",
            new=MagicMock(publish_immediate=AsyncMock()),
        ):
            result = await apply_reply(
                db,
                confirmation_id=confirmation.id,
                attachment_id=attachment.id,
                confirmed_amount=confirmed_amount,
                reply_date="2025-06-30",
                target_status="discrepancy",  # 用户坚持差异
                actor_user_id=uuid.uuid4(),
            )

        # 系统建议 matched，但最终以用户为准
        assert result["suggested_status"] == "matched"
        assert result["actual_status"] == "discrepancy"
        assert confirmation.status == "discrepancy"
