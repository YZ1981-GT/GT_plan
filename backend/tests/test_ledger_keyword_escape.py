"""关键词 LIKE 元字符转义测试（voucher-sampling-hardening Task 6）

无 DB：编译 build_ledger_query 的 SQL，断言含 LIKE 元字符的关键词被转义为字面量
（`%`→`\%`、`_`→`\_`、`\`→`\\`）且带 ESCAPE 子句。

Validates: Requirements 11.1, 11.2, 11.3
Properties: Property 21
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa

from app.models.audit_platform_models import TbLedger
from app.services.ledger_sampling_service import (
    LedgerQueryFilters,
    LedgerSamplingService,
    _escape_like_pattern,
)


async def _compile_sql(keyword: str) -> str:
    filters = LedgerQueryFilters(
        date_start=date(2025, 1, 1),
        date_end=date(2025, 12, 31),
        account_codes=["1122"],
        summary_keyword=keyword,
    )
    project_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_filter = sa.and_(
        TbLedger.project_id == project_id,
        TbLedger.year == 2025,
        TbLedger.is_deleted == sa.false(),
    )
    with patch(
        "app.services.ledger_sampling_service.get_active_filter",
        new=AsyncMock(return_value=mock_filter),
    ):
        query = await LedgerSamplingService.build_ledger_query(
            mock_db, project_id, 2025, filters
        )
    compiled = query.compile(
        compile_kwargs={"literal_binds": True},
        dialect=sa.dialects.postgresql.dialect(),
    )
    return str(compiled)


class TestEscapeLikePattern:
    """直接单测转义纯函数（不依赖 literal_binds 渲染）。"""

    def test_percent_escaped(self):
        assert _escape_like_pattern("50%") == "50\\%"

    def test_underscore_escaped(self):
        assert _escape_like_pattern("A_B") == "A\\_B"

    def test_backslash_escaped_first(self):
        # 先转义反斜杠自身，避免二次转义：'x\y' → 'x\\y'
        assert _escape_like_pattern("x\\y") == "x\\\\y"

    def test_combined(self):
        # '\_%' → 反斜杠先 → '\\_%' → 再 _ → '\\\_%' → 再 % → '\\\_\%'
        assert _escape_like_pattern("\\_%") == "\\\\\\_\\%"

    def test_plain_unchanged(self):
        assert _escape_like_pattern("采购付款") == "采购付款"


class TestKeywordQueryConstruction:
    @pytest.mark.asyncio
    async def test_keyword_adds_ilike_with_escape(self):
        sql = await _compile_sql("50%")
        assert "ilike" in sql.lower()
        assert "escape" in sql.lower()

    @pytest.mark.asyncio
    async def test_plain_keyword_appears(self):
        sql = await _compile_sql("采购付款")
        assert "采购付款" in sql
        assert "ilike" in sql.lower()

    @pytest.mark.asyncio
    async def test_empty_keyword_no_ilike(self):
        sql = await _compile_sql("")
        assert "ilike" not in sql.lower()
