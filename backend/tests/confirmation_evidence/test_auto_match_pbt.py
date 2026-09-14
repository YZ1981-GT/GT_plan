"""confirmation-attachment-ocr-linkage — Property 8 PBT（Task 5.4）

Property 8: 自动匹配唯一命中才落
  auto_match 唯一命中才挂载并绑发函件；多义返回候选不挂载；无命中入 match_status=pending 队列；
  均不写台账正式结论；命中依据记入 match_evidence 可解释。

Testing approach: mock-based hypothesis max_examples=5，验证服务层行为。

**Validates: Requirements 6.2, 6.3, 6.4, 6.5, 10.4**
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, assume, settings
from hypothesis import strategies as st


# ─── Strategies ───────────────────────────────────────────────────────────────


def st_uuid():
    """Generate random UUIDs."""
    return st.builds(uuid.uuid4)


def st_counterparty():
    """Generate counterparty names for matching scenarios."""
    return st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=0x4E00, max_codepoint=0x9FFF),
        min_size=2,
        max_size=10,
    ).map(lambda s: s + "有限公司")


def st_amount():
    """Generate realistic amounts for matching."""
    return st.decimals(min_value=Decimal("100"), max_value=Decimal("99999999"), places=2, allow_nan=False, allow_infinity=False)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_confirmation_mock(
    *,
    cid: uuid.UUID | None = None,
    counterparty: str = "测试公司有限公司",
    book_amount: float | None = 10000.0,
    status: str = "sent",
    project_id: uuid.UUID | None = None,
    confirmed_amount: float | None = None,
):
    """Build a mock Confirmation object."""
    conf = MagicMock()
    conf.id = cid or uuid.uuid4()
    conf.counterparty = counterparty
    conf.book_amount = book_amount
    conf.status = status
    conf.project_id = project_id or uuid.uuid4()
    conf.confirmed_amount = confirmed_amount
    return conf


def _make_attachment_mock(
    *,
    att_id: uuid.UUID | None = None,
    ocr_fields_cache: dict | None = None,
):
    """Build a mock Attachment object."""
    att = MagicMock()
    att.id = att_id or uuid.uuid4()
    att.ocr_fields_cache = ocr_fields_cache
    att.reference_type = None
    att.reference_id = None
    return att


def _make_outbound_link_mock(*, attachment_id: uuid.UUID | None = None):
    """Build a mock ConfirmationAttachmentLink (outbound)."""
    link = MagicMock()
    link.attachment_id = attachment_id or uuid.uuid4()
    link.role = "outbound"
    return link


def _build_mock_db(
    *,
    attachment: MagicMock,
    candidates: list[MagicMock],
    outbound_links: list[MagicMock] | None = None,
):
    """Build a mock AsyncSession for auto_match tests.

    Handles the multi-call nature of auto_match:
    1. db.get(Attachment, id) → attachment
    2. db.execute(candidates query) → candidates
    3. db.execute(outbound query) → outbound_links (for unique match path)
    4. db.get(Attachment, id) → attachment (for setting reference in _auto_link)
    """
    if outbound_links is None:
        outbound_links = [_make_outbound_link_mock()]

    mock_db = AsyncMock()

    # Track objects added to session
    added_objects = []
    mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
    mock_db._added_objects = added_objects
    mock_db.flush = AsyncMock()

    # db.get calls: first for attachment, then potentially for attachment again in _auto_link
    mock_db.get = AsyncMock(return_value=attachment)

    # db.execute calls sequence:
    # 1st call: candidates query (SELECT Confirmation WHERE project_id AND status IN...)
    # 2nd call (unique match only): outbound links query
    candidates_result = MagicMock()
    candidates_result.scalars.return_value.all.return_value = candidates

    outbound_result = MagicMock()
    outbound_result.scalars.return_value.all.return_value = outbound_links

    mock_db.execute = AsyncMock(
        side_effect=[candidates_result, outbound_result]
    )

    return mock_db


# ════════════════════════════════════════════════════════════════════════════════
# Property 8: 自动匹配唯一命中才落
# ════════════════════════════════════════════════════════════════════════════════


class TestProperty8UniqueHitAutoLinks:
    """P8.1: Unique hit → auto-link with match_status='auto' and non-empty match_evidence."""

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_unique_hit_creates_link(self, data):
        """**Validates: Requirements 6.2**

        唯一命中一条发函记录时，auto_match SHALL 把回函件挂到该函证（创建 link），
        match_status='auto'，match_evidence 非空 dict。
        """
        project_id = data.draw(st_uuid())
        attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())
        counterparty_name = "北京测试科技有限公司"

        # Build scenario: exactly 1 matching confirmation (counterparty matches)
        matched_conf = _make_confirmation_mock(
            counterparty=counterparty_name,
            book_amount=50000.0,
            status="sent",
            project_id=project_id,
        )

        # Attachment with OCR cache that matches
        attachment = _make_attachment_mock(
            att_id=attachment_id,
            ocr_fields_cache={
                "reply_entity": counterparty_name,
                "reply_amount": 50000.0,
            },
        )

        outbound_link = _make_outbound_link_mock()

        mock_db = _build_mock_db(
            attachment=attachment,
            candidates=[matched_conf],
            outbound_links=[outbound_link],
        )

        from app.services.confirmation_evidence_service import auto_match

        result = await auto_match(
            mock_db,
            project_id=project_id,
            attachment_id=attachment_id,
            actor_user_id=actor_id,
        )

        # Core assertions for unique hit
        assert result["result"] == "unique_match"
        assert result["match_status"] == "auto"
        assert result["confirmation_id"] == str(matched_conf.id)

        # match_evidence must be non-empty dict
        assert isinstance(result["match_evidence"], dict)
        assert len(result["match_evidence"]) > 0

        # db.add was called (link + action_log created)
        assert mock_db.add.call_count >= 1, "auto_match unique hit should create link record"


class TestProperty8AmbiguousNoCandidatesNoLink:
    """P8.2: Multiple hits → ambiguous, return candidates, do NOT create link."""

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_multiple_hits_no_link(self, data):
        """**Validates: Requirements 6.3**

        多义命中（2+条发函记录匹配）时，auto_match SHALL 返回 result='ambiguous'
        + candidates 列表，但不创建任何 link 记录（db.add 不被调用于 ConfirmationAttachmentLink）。
        """
        project_id = data.draw(st_uuid())
        attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())
        counterparty_name = "上海多义匹配公司"

        # Build scenario: 2+ matching confirmations (same counterparty)
        num_matches = data.draw(st.integers(min_value=2, max_value=5))
        matched_confs = [
            _make_confirmation_mock(
                counterparty=counterparty_name,
                book_amount=float(10000 + i * 1000),
                status="sent",
                project_id=project_id,
            )
            for i in range(num_matches)
        ]

        # Attachment with OCR cache matching the shared counterparty
        attachment = _make_attachment_mock(
            att_id=attachment_id,
            ocr_fields_cache={
                "reply_entity": counterparty_name,
                "reply_amount": 10000.0,
            },
        )

        mock_db = _build_mock_db(
            attachment=attachment,
            candidates=matched_confs,
        )

        from app.services.confirmation_evidence_service import auto_match

        result = await auto_match(
            mock_db,
            project_id=project_id,
            attachment_id=attachment_id,
            actor_user_id=actor_id,
        )

        # Core assertions for ambiguous
        assert result["result"] == "ambiguous"
        assert "candidates" in result
        assert len(result["candidates"]) >= 2

        # db.add should NOT have been called (no link created)
        mock_db.add.assert_not_called()
        mock_db.flush.assert_not_called()


class TestProperty8NoHitPendingQueue:
    """P8.3: No hit → pending queue, no link created."""

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_no_hit_returns_pending(self, data):
        """**Validates: Requirements 6.4**

        无命中时，auto_match SHALL 返回 result='no_match' + match_status='pending'，
        不创建任何 link 记录，不写 confirmations 表。
        """
        project_id = data.draw(st_uuid())
        attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())

        # Build scenario: candidates exist but none match
        non_matching_confs = [
            _make_confirmation_mock(
                counterparty="完全不同的公司名A",
                book_amount=99999.0,
                status="sent",
                project_id=project_id,
            ),
            _make_confirmation_mock(
                counterparty="完全不同的公司名B",
                book_amount=88888.0,
                status="returned",
                project_id=project_id,
            ),
        ]

        # Attachment with OCR cache that won't match any candidate
        attachment = _make_attachment_mock(
            att_id=attachment_id,
            ocr_fields_cache={
                "reply_entity": "一家根本不存在的公司",
                "reply_amount": 12345.67,
            },
        )

        mock_db = _build_mock_db(
            attachment=attachment,
            candidates=non_matching_confs,
        )

        from app.services.confirmation_evidence_service import auto_match

        result = await auto_match(
            mock_db,
            project_id=project_id,
            attachment_id=attachment_id,
            actor_user_id=actor_id,
        )

        # Core assertions for no match
        assert result["result"] == "no_match"
        assert result["match_status"] == "pending"

        # db.add should NOT have been called
        mock_db.add.assert_not_called()
        mock_db.flush.assert_not_called()

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_no_candidates_at_all_returns_pending(self, data):
        """**Validates: Requirements 6.4**

        项目无候选函证（无 sent/returned 记录）时，直接返回 no_match。
        """
        project_id = data.draw(st_uuid())
        attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())

        # Attachment with OCR cache
        attachment = _make_attachment_mock(
            att_id=attachment_id,
            ocr_fields_cache={
                "reply_entity": "某某公司",
                "reply_amount": 5000.0,
            },
        )

        # No candidates in project
        candidates_result = MagicMock()
        candidates_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=attachment)
        mock_db.execute = AsyncMock(return_value=candidates_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        from app.services.confirmation_evidence_service import auto_match

        result = await auto_match(
            mock_db,
            project_id=project_id,
            attachment_id=attachment_id,
            actor_user_id=actor_id,
        )

        assert result["result"] == "no_match"
        assert result["match_status"] == "pending"
        mock_db.add.assert_not_called()


class TestProperty8NeverWritesFormalConclusion:
    """P8.4: In ALL three outcomes, auto_match never writes formal conclusions to confirmations table."""

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_unique_hit_does_not_modify_confirmation_fields(self, data):
        """**Validates: Requirements 6.2, 10.4**

        即使唯一命中，auto_match 也不修改 Confirmation.confirmed_amount 或 Confirmation.status。
        台账正式结论只能由 apply_reply（人工确认）落库。
        """
        project_id = data.draw(st_uuid())
        attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())
        counterparty_name = "武汉唯一命中公司"

        matched_conf = _make_confirmation_mock(
            counterparty=counterparty_name,
            book_amount=30000.0,
            status="sent",
            project_id=project_id,
            confirmed_amount=None,
        )

        # Record original values
        original_status = matched_conf.status
        original_confirmed_amount = matched_conf.confirmed_amount

        attachment = _make_attachment_mock(
            att_id=attachment_id,
            ocr_fields_cache={
                "reply_entity": counterparty_name,
                "reply_amount": 30000.0,
            },
        )

        outbound_link = _make_outbound_link_mock()

        mock_db = _build_mock_db(
            attachment=attachment,
            candidates=[matched_conf],
            outbound_links=[outbound_link],
        )

        from app.services.confirmation_evidence_service import auto_match

        await auto_match(
            mock_db,
            project_id=project_id,
            attachment_id=attachment_id,
            actor_user_id=actor_id,
        )

        # Core invariant: Confirmation fields unchanged
        assert matched_conf.status == original_status, (
            "auto_match MUST NOT change Confirmation.status"
        )
        assert matched_conf.confirmed_amount == original_confirmed_amount, (
            "auto_match MUST NOT change Confirmation.confirmed_amount"
        )

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_ambiguous_does_not_modify_any_confirmation(self, data):
        """**Validates: Requirements 6.3, 10.4**

        多义命中时，所有候选 Confirmation 的 status/confirmed_amount 不变。
        """
        project_id = data.draw(st_uuid())
        attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())
        counterparty_name = "深圳多义公司"

        confs = [
            _make_confirmation_mock(
                counterparty=counterparty_name,
                book_amount=float(20000 + i * 500),
                status="sent",
                project_id=project_id,
                confirmed_amount=None,
            )
            for i in range(3)
        ]

        # Record originals
        originals = [(c.status, c.confirmed_amount) for c in confs]

        attachment = _make_attachment_mock(
            att_id=attachment_id,
            ocr_fields_cache={
                "reply_entity": counterparty_name,
                "reply_amount": 20000.0,
            },
        )

        mock_db = _build_mock_db(
            attachment=attachment,
            candidates=confs,
        )

        from app.services.confirmation_evidence_service import auto_match

        await auto_match(
            mock_db,
            project_id=project_id,
            attachment_id=attachment_id,
            actor_user_id=actor_id,
        )

        # All confirmations unchanged
        for i, conf in enumerate(confs):
            assert conf.status == originals[i][0]
            assert conf.confirmed_amount == originals[i][1]


class TestProperty8MatchEvidenceInterpretable:
    """P8.5: When unique hit occurs, match_evidence contains interpretable fields."""

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_match_evidence_has_required_fields(self, data):
        """**Validates: Requirements 6.5**

        唯一命中时，match_evidence 至少含: matched_by (string), confidence (string),
        counterparty_matched (bool), amount_within_tolerance (bool)。
        """
        project_id = data.draw(st_uuid())
        attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())
        counterparty_name = "广州可解释公司"

        matched_conf = _make_confirmation_mock(
            counterparty=counterparty_name,
            book_amount=75000.0,
            status="sent",
            project_id=project_id,
        )

        attachment = _make_attachment_mock(
            att_id=attachment_id,
            ocr_fields_cache={
                "reply_entity": counterparty_name,
                "reply_amount": 75000.0,
            },
        )

        outbound_link = _make_outbound_link_mock()

        mock_db = _build_mock_db(
            attachment=attachment,
            candidates=[matched_conf],
            outbound_links=[outbound_link],
        )

        from app.services.confirmation_evidence_service import auto_match

        result = await auto_match(
            mock_db,
            project_id=project_id,
            attachment_id=attachment_id,
            actor_user_id=actor_id,
        )

        assert result["result"] == "unique_match"
        evidence = result["match_evidence"]

        # Required fields for interpretability
        assert "matched_by" in evidence, "match_evidence must contain 'matched_by'"
        assert isinstance(evidence["matched_by"], str), "matched_by must be string"
        assert len(evidence["matched_by"]) > 0, "matched_by must be non-empty"

        assert "confidence" in evidence, "match_evidence must contain 'confidence'"
        assert isinstance(evidence["confidence"], str), "confidence must be string"
        assert evidence["confidence"] in ("high", "medium", "low"), (
            f"confidence must be high/medium/low, got: {evidence['confidence']}"
        )

        assert "counterparty_matched" in evidence, "match_evidence must contain 'counterparty_matched'"
        assert isinstance(evidence["counterparty_matched"], bool), "counterparty_matched must be bool"

        assert "amount_within_tolerance" in evidence, "match_evidence must contain 'amount_within_tolerance'"
        assert isinstance(evidence["amount_within_tolerance"], bool), "amount_within_tolerance must be bool"

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_counterparty_exact_match_high_confidence(self, data):
        """**Validates: Requirements 6.5**

        精确名称匹配 + 金额容差内 → confidence='high', counterparty_matched=True,
        amount_within_tolerance=True.
        """
        project_id = data.draw(st_uuid())
        attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())
        counterparty_name = "成都精确匹配公司"
        amount = 42000.0

        matched_conf = _make_confirmation_mock(
            counterparty=counterparty_name,
            book_amount=amount,
            status="sent",
            project_id=project_id,
        )

        attachment = _make_attachment_mock(
            att_id=attachment_id,
            ocr_fields_cache={
                "reply_entity": counterparty_name,  # exact match
                "reply_amount": amount,  # within tolerance
            },
        )

        outbound_link = _make_outbound_link_mock()

        mock_db = _build_mock_db(
            attachment=attachment,
            candidates=[matched_conf],
            outbound_links=[outbound_link],
        )

        from app.services.confirmation_evidence_service import auto_match

        result = await auto_match(
            mock_db,
            project_id=project_id,
            attachment_id=attachment_id,
            actor_user_id=actor_id,
        )

        evidence = result["match_evidence"]
        assert evidence["counterparty_matched"] is True
        assert evidence["amount_within_tolerance"] is True
        assert evidence["confidence"] == "high"
        assert "exact" in evidence["matched_by"].lower() or "counterparty" in evidence["matched_by"].lower()
