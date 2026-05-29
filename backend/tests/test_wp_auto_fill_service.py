"""Tests for wp_auto_fill_service — 底稿自动刷数

锚定 spec workpaper-editor-slimdown Task 16.2 + 16.3
Validates: US-15（HTML 底稿自动刷数）
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.wp_auto_fill_service import (
    _resolve_auto_fill_values,
    _fetch_source_value,
    _serialize_value,
    _TB_FIELD_MAP,
)


# ─── Unit Tests ───────────────────────────────────────────────────────────────


class TestSerializeValue:
    """Test _serialize_value helper."""

    def test_none_returns_none(self):
        assert _serialize_value(None) is None

    def test_decimal_returns_float(self):
        result = _serialize_value(Decimal("1234.56"))
        assert result == 1234.56
        assert isinstance(result, float)

    def test_string_returns_string(self):
        assert _serialize_value("hello") == "hello"

    def test_int_returns_int(self):
        assert _serialize_value(42) == 42


class TestTBFieldMap:
    """Test TB field mapping covers expected fields."""

    def test_chinese_fields_mapped(self):
        assert _TB_FIELD_MAP["期末"] == "closing_balance"
        assert _TB_FIELD_MAP["期初"] == "opening_balance"
        assert _TB_FIELD_MAP["借方"] == "debit_amount"
        assert _TB_FIELD_MAP["贷方"] == "credit_amount"
        assert _TB_FIELD_MAP["审定数"] == "audited_amount"

    def test_english_fields_mapped(self):
        assert _TB_FIELD_MAP["closing_balance"] == "closing_balance"
        assert _TB_FIELD_MAP["opening_balance"] == "opening_balance"


class TestFetchSourceValue:
    """Test _fetch_source_value parsing logic."""

    @pytest.mark.asyncio
    async def test_empty_source_returns_none(self):
        db = AsyncMock()
        result = await _fetch_source_value("", uuid4(), 2025, db)
        assert result is None

    @pytest.mark.asyncio
    async def test_single_part_returns_none(self):
        db = AsyncMock()
        result = await _fetch_source_value("TB", uuid4(), 2025, db)
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_source_type_returns_none(self):
        db = AsyncMock()
        result = await _fetch_source_value("UNKNOWN:foo:bar", uuid4(), 2025, db)
        assert result is None

    @pytest.mark.asyncio
    async def test_tb_source_insufficient_parts_returns_none(self):
        db = AsyncMock()
        result = await _fetch_source_value("TB:1001", uuid4(), 2025, db)
        assert result is None

    @pytest.mark.asyncio
    async def test_wp_source_insufficient_parts_returns_none(self):
        db = AsyncMock()
        result = await _fetch_source_value("WP:D2A", uuid4(), 2025, db)
        assert result is None


class TestResolveAutoFillValues:
    """Test _resolve_auto_fill_values batch resolution."""

    @pytest.mark.asyncio
    async def test_empty_schema_returns_empty(self):
        db = AsyncMock()
        result = await _resolve_auto_fill_values({}, uuid4(), 2025, db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_cross_refs_returns_empty(self):
        db = AsyncMock()
        schema = {"sheets": {"Sheet1": {"columns": []}}}
        result = await _resolve_auto_fill_values(schema, uuid4(), 2025, db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_cross_refs_with_unavailable_source(self):
        """When source value cannot be fetched, status should be 'unavailable'."""
        db = AsyncMock()
        # Mock execute to return no results
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        schema = {
            "sheets": {
                "程序表": {
                    "cross_refs": [
                        {
                            "cell": "B7",
                            "source": "TB:1122:期末",
                            "label": "应收账款期末余额",
                        }
                    ]
                }
            }
        }

        result = await _resolve_auto_fill_values(schema, uuid4(), 2025, db)
        assert "程序表!B7" in result
        assert result["程序表!B7"]["status"] == "unavailable"
        assert result["程序表!B7"]["value"] is None
        assert result["程序表!B7"]["source"] == "TB:1122:期末"
        assert result["程序表!B7"]["label"] == "应收账款期末余额"

    @pytest.mark.asyncio
    async def test_cross_refs_with_available_source(self):
        """When source value is found, status should be 'ok'."""
        db = AsyncMock()
        # Mock TB row with closing_balance and standard_account_code
        mock_row = MagicMock()
        mock_row.standard_account_code = "1001"
        mock_row.closing_balance = Decimal("42772704.06")
        # Batch query uses result.scalars() which returns an iterable of rows
        mock_scalars = MagicMock()
        mock_scalars.__iter__ = MagicMock(return_value=iter([mock_row]))
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        schema = {
            "sheets": {
                "程序表": {
                    "cross_refs": [
                        {
                            "cell": "C5",
                            "source": "TB:1001:期末",
                            "label": "货币资金期末",
                        }
                    ]
                }
            }
        }

        result = await _resolve_auto_fill_values(schema, uuid4(), 2025, db)
        assert "程序表!C5" in result
        assert result["程序表!C5"]["status"] == "ok"
        assert result["程序表!C5"]["value"] == 42772704.06
        assert result["程序表!C5"]["source"] == "TB:1001:期末"

    @pytest.mark.asyncio
    async def test_multiple_sheets_multiple_refs(self):
        """Multiple sheets with multiple cross_refs should all be resolved."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        schema = {
            "sheets": {
                "Sheet1": {
                    "cross_refs": [
                        {"cell": "A1", "source": "TB:1001:期末", "label": "L1"},
                        {"cell": "B2", "source": "TB:1002:期初", "label": "L2"},
                    ]
                },
                "Sheet2": {
                    "cross_refs": [
                        {"cell": "C3", "source": "REPORT:R001:amount", "label": "L3"},
                    ]
                },
            }
        }

        result = await _resolve_auto_fill_values(schema, uuid4(), 2025, db)
        assert len(result) == 3
        assert "Sheet1!A1" in result
        assert "Sheet1!B2" in result
        assert "Sheet2!C3" in result

    @pytest.mark.asyncio
    async def test_invalid_ref_skipped(self):
        """Refs without source or cell should be skipped."""
        db = AsyncMock()
        schema = {
            "sheets": {
                "Sheet1": {
                    "cross_refs": [
                        {"cell": "", "source": "TB:1001:期末"},  # empty cell
                        {"cell": "A1", "source": ""},  # empty source
                        {"cell": "B2", "source": "TB:1002:期末", "label": "OK"},
                    ]
                }
            }
        }

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await _resolve_auto_fill_values(schema, uuid4(), 2025, db)
        # Only the valid ref should be in results
        assert len(result) == 1
        assert "Sheet1!B2" in result
