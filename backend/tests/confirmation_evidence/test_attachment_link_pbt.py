"""confirmation-attachment-ocr-linkage — Property 9 & 12 PBT（Task 3.4）

Property 9: 回函件强绑发函件
  role=inbound 的 link 必有 paired_outbound_attachment_id（且指向同函证 outbound）；
  无发函件不得挂回函件；单份自动/多份指定。

Property 12: 附件计数批量无 N+1
  list_attachment_counts(ids[]) 单次 GROUP BY 查询返回全部函证计数。

Testing approach: mock-based 纯逻辑测试（不依赖真实 PG16），验证服务层行为。

_Requirements: 3.4, 3.5, 3.6_
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from hypothesis import given, assume, settings
from hypothesis import strategies as st


# ─── Strategies ───────────────────────────────────────────────────────────────


def st_uuid():
    """Generate random UUIDs for test data."""
    return st.builds(uuid.uuid4)


def st_outbound_count():
    """Generate number of existing outbound links: 0, 1, or multiple."""
    return st.integers(min_value=0, max_value=5)


# ════════════════════════════════════════════════════════════════════════════════
# Property 9: 回函件强绑发函件
# Validates: Requirements 3.5, 3.6
# ════════════════════════════════════════════════════════════════════════════════


class TestProperty9InboundPairsOutbound:
    """P9: role=inbound 必有 paired_outbound 且指向同函证 outbound；
    无发函件不得挂回函件；单份自动/多份指定。
    """

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_no_outbound_blocks_inbound(self, data):
        """**Validates: Requirements 3.5**

        无发函件时，挂回函件应被拒绝（ValueError）。
        """
        confirmation_id = data.draw(st_uuid())
        attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())

        # Mock DB: confirmation exists, no outbound links
        mock_confirmation = MagicMock()
        mock_confirmation.project_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []  # 0 outbound links

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=lambda model, id: mock_confirmation)
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.confirmation_evidence_service import link_attachment

        with pytest.raises(ValueError, match="无发函件不得单独挂回函件"):
            await link_attachment(
                mock_db,
                confirmation_id=confirmation_id,
                attachment_id=attachment_id,
                role="inbound",
                actor_user_id=actor_id,
            )

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_single_outbound_auto_pairs(self, data):
        """**Validates: Requirements 3.6**

        单份发函件时，回函件自动绑定到该唯一发函件。
        paired_outbound_attachment_id == 该 outbound 的 attachment_id。
        """
        confirmation_id = data.draw(st_uuid())
        inbound_attachment_id = data.draw(st_uuid())
        outbound_attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())

        # Mock: confirmation exists
        mock_confirmation = MagicMock()
        mock_confirmation.project_id = uuid.uuid4()

        # Mock: single outbound link exists
        mock_outbound_link = MagicMock()
        mock_outbound_link.attachment_id = outbound_attachment_id

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_outbound_link]

        # Track added objects
        added_objects = []

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=lambda model, id: mock_confirmation)
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        mock_db.flush = AsyncMock()

        from app.services.confirmation_evidence_service import link_attachment

        result = await link_attachment(
            mock_db,
            confirmation_id=confirmation_id,
            attachment_id=inbound_attachment_id,
            role="inbound",
            actor_user_id=actor_id,
        )

        # Core assertion: auto-paired to the single outbound
        assert result.paired_outbound_attachment_id == outbound_attachment_id
        assert result.role == "inbound"

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_multiple_outbound_requires_specification(self, data):
        """**Validates: Requirements 3.6**

        多份发函件时，挂回函件须指定 paired_outbound_id，否则拒绝。
        """
        confirmation_id = data.draw(st_uuid())
        inbound_attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())

        # Mock: confirmation exists
        mock_confirmation = MagicMock()
        mock_confirmation.project_id = uuid.uuid4()

        # Mock: multiple outbound links (2+)
        outbound_links = [MagicMock(attachment_id=uuid.uuid4()) for _ in range(2)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = outbound_links

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=lambda model, id: mock_confirmation)
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.confirmation_evidence_service import link_attachment

        # Without specifying paired_outbound_id → should raise
        with pytest.raises(ValueError, match="有多份发函件时须指定配对发函件"):
            await link_attachment(
                mock_db,
                confirmation_id=confirmation_id,
                attachment_id=inbound_attachment_id,
                role="inbound",
                paired_outbound_id=None,
                actor_user_id=actor_id,
            )

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_paired_outbound_must_belong_to_same_confirmation(self, data):
        """**Validates: Requirements 3.5**

        指定的 paired_outbound_attachment_id 必须指向同函证下的 outbound 附件，
        否则拒绝。
        """
        confirmation_id = data.draw(st_uuid())
        inbound_attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())
        wrong_outbound_id = data.draw(st_uuid())  # 不属于该函证

        # Mock: confirmation exists
        mock_confirmation = MagicMock()
        mock_confirmation.project_id = uuid.uuid4()

        # Mock: 2 outbound links (neither matches wrong_outbound_id)
        outbound_links = [MagicMock(attachment_id=uuid.uuid4()) for _ in range(2)]
        # Ensure wrong_outbound_id is NOT in the valid set
        assume(wrong_outbound_id not in {link.attachment_id for link in outbound_links})

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = outbound_links

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=lambda model, id: mock_confirmation)
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.confirmation_evidence_service import link_attachment

        with pytest.raises(ValueError, match="不属于该函证的发函件"):
            await link_attachment(
                mock_db,
                confirmation_id=confirmation_id,
                attachment_id=inbound_attachment_id,
                role="inbound",
                paired_outbound_id=wrong_outbound_id,
                actor_user_id=actor_id,
            )

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_valid_paired_outbound_accepted(self, data):
        """**Validates: Requirements 3.5, 3.6**

        多份发函件时指定合法的 paired_outbound_id 应成功。
        """
        confirmation_id = data.draw(st_uuid())
        inbound_attachment_id = data.draw(st_uuid())
        actor_id = data.draw(st_uuid())

        # Mock: confirmation exists
        mock_confirmation = MagicMock()
        mock_confirmation.project_id = uuid.uuid4()

        # Mock: 2 outbound links, pick one as the valid target
        valid_outbound_id = uuid.uuid4()
        outbound_links = [
            MagicMock(attachment_id=valid_outbound_id),
            MagicMock(attachment_id=uuid.uuid4()),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = outbound_links

        added_objects = []

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=lambda model, id: mock_confirmation)
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        mock_db.flush = AsyncMock()

        from app.services.confirmation_evidence_service import link_attachment

        result = await link_attachment(
            mock_db,
            confirmation_id=confirmation_id,
            attachment_id=inbound_attachment_id,
            role="inbound",
            paired_outbound_id=valid_outbound_id,
            actor_user_id=actor_id,
        )

        assert result.paired_outbound_attachment_id == valid_outbound_id
        assert result.role == "inbound"


# ════════════════════════════════════════════════════════════════════════════════
# Property 12: 附件计数批量无 N+1
# Validates: Requirements 3.4
# ════════════════════════════════════════════════════════════════════════════════


class TestProperty12BulkCountNoNPlusOne:
    """P12: list_attachment_counts(ids[]) 单次 GROUP BY 查询返回全部函证计数，
    不随函证数线性增加查询次数。
    """

    @pytest.mark.asyncio
    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=5)
    async def test_single_query_for_any_count(self, n):
        """**Validates: Requirements 3.4**

        无论传入多少 confirmation_ids，execute 只调一次（单次 GROUP BY）。
        """
        confirmation_ids = [uuid.uuid4() for _ in range(n)]

        # Mock DB: return some rows
        mock_rows = []
        for cid in confirmation_ids[:max(1, n // 2)]:
            # 模拟 GROUP BY 结果行
            row = MagicMock()
            row.confirmation_id = cid
            row.role = "outbound"
            row.cnt = 1
            mock_rows.append(row)

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.confirmation_evidence_service import list_attachment_counts

        result = await list_attachment_counts(mock_db, confirmation_ids)

        # Core assertion: execute called exactly once (single GROUP BY)
        assert mock_db.execute.call_count == 1, (
            f"list_attachment_counts({n} ids) 应只发一次查询，"
            f"实际 {mock_db.execute.call_count} 次"
        )

        # Result is a dict
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty_no_query(self):
        """**Validates: Requirements 3.4**

        空列表不发查询，直接返回空 dict。
        """
        mock_db = AsyncMock()

        from app.services.confirmation_evidence_service import list_attachment_counts

        result = await list_attachment_counts(mock_db, [])

        assert result == {}
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    @given(data=st.data())
    @settings(max_examples=5)
    async def test_counts_accuracy(self, data):
        """**Validates: Requirements 3.4**

        返回的 outbound/inbound 计数应正确反映 GROUP BY 结果。
        """
        cid1 = data.draw(st_uuid())
        cid2 = data.draw(st_uuid())
        assume(cid1 != cid2)

        # Simulate GROUP BY results:
        # cid1: 2 outbound, 1 inbound
        # cid2: 1 outbound, 0 inbound (only outbound row)
        mock_rows = [
            MagicMock(confirmation_id=cid1, role="outbound", cnt=2),
            MagicMock(confirmation_id=cid1, role="inbound", cnt=1),
            MagicMock(confirmation_id=cid2, role="outbound", cnt=1),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.confirmation_evidence_service import list_attachment_counts

        result = await list_attachment_counts(mock_db, [cid1, cid2])

        # Verify counts
        assert result[str(cid1)]["outbound"] == 2
        assert result[str(cid1)]["inbound"] == 1
        assert result[str(cid2)]["outbound"] == 1
        assert result[str(cid2)]["inbound"] == 0
