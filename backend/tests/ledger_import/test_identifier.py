"""Unit tests for backend.app.services.ledger_import.identifier.

Covers Sprint 1 Task 20 — identifier 基础用例（需求 1、2）：
- Level 1: sheet name recognition (3 tests)
- Level 2: header-based recognition (4 tests)
- Level 3: content-based recognition (2 tests)
- Aggregation: L1+L2 agree/disagree (2 tests)
"""

from __future__ import annotations

import pytest

from backend.app.services.ledger_import.detection_types import (
    SheetDetection,
)
from backend.app.services.ledger_import.identifier import identify


# ---------------------------------------------------------------------------
# Helper: build SheetDetection fixtures
# ---------------------------------------------------------------------------


def _make_sheet(
    sheet_name: str = "Sheet1",
    headers: list[str] | None = None,
    data_rows: list[list[str]] | None = None,
) -> SheetDetection:
    """Build a minimal SheetDetection for identifier tests."""
    preview: list[list[str]] = []
    if headers:
        preview.append(headers)
    if data_rows:
        preview.extend(data_rows)
    return SheetDetection(
        file_name="test.xlsx",
        sheet_name=sheet_name,
        row_count_estimate=len(preview),
        header_row_index=0,
        data_start_row=1,
        table_type="unknown",
        table_type_confidence=0,
        confidence_level="manual_required",
        preview_rows=preview,
        detection_evidence={"header_cells": headers or [], "merged_header": False},
    )


# ===========================================================================
# Level 1 — Sheet name recognition
# ===========================================================================


class TestLevel1SheetName:
    """Level 1 识别：sheet 名关键词匹配。"""

    def test_level1_balance_sheet_name(self):
        """sheet_name='科目余额表' → L1 detects balance, confidence≥90."""
        sheet = _make_sheet(
            sheet_name="科目余额表",
            headers=["列甲", "列乙", "列丙"],  # neutral headers that won't trigger L2
        )
        result = identify(sheet)

        # L1 should detect balance
        evidence = result.detection_evidence
        assert evidence["level1"]["table_type"] == "balance"
        assert evidence["level1"]["confidence"] >= 90
        # Final result should be balance (L1 wins when L2 is unknown)
        assert result.table_type == "balance"
        assert result.table_type_confidence >= 75

    def test_level1_ledger_month_sheet(self):
        """sheet_name='1月' → L1 detects ledger via fuzzy month pattern, confidence=75."""
        sheet = _make_sheet(
            sheet_name="1月",  # matches month pattern only (no "凭证" keyword)
            headers=["列甲", "列乙", "列丙"],  # neutral headers
        )
        result = identify(sheet)

        # L1 should detect ledger with fuzzy confidence
        evidence = result.detection_evidence
        assert evidence["level1"]["table_type"] == "ledger"
        assert evidence["level1"]["confidence"] == 75
        # Final result should be ledger
        assert result.table_type == "ledger"

    def test_level1_unknown_sheet_name(self):
        """sheet_name='员工通讯录' → stays 'unknown' from L1."""
        sheet = _make_sheet(
            sheet_name="员工通讯录",
            headers=["列甲", "列乙", "列丙"],  # neutral headers
        )
        result = identify(sheet)

        # L1 should not match
        evidence = result.detection_evidence
        assert evidence["level1"]["table_type"] == "unknown"


# ===========================================================================
# Level 2 — Header-based recognition
# ===========================================================================


class TestLevel2Headers:
    """Level 2 识别：表头特征匹配。"""

    def test_level2_balance_headers(self):
        """Balance headers → balance, confidence≥80."""
        headers = ["科目编码", "科目名称", "期初余额", "本期借方", "本期贷方", "期末余额"]
        sheet = _make_sheet(
            sheet_name="Sheet1",  # neutral name, no L1 match
            headers=headers,
        )
        result = identify(sheet)

        assert result.table_type == "balance"
        assert result.table_type_confidence >= 80

    def test_level2_ledger_headers(self):
        """Ledger headers → ledger, confidence≥80."""
        headers = ["日期", "凭证号", "摘要", "科目编码", "借方金额", "贷方金额"]
        sheet = _make_sheet(
            sheet_name="Sheet1",
            headers=headers,
        )
        result = identify(sheet)

        assert result.table_type == "ledger"
        assert result.table_type_confidence >= 80

    def test_level2_partial_headers(self):
        """Only 2 of 5 key columns → confidence < 80 (medium or low)."""
        # Only account_code and debit_amount — not enough for high confidence
        headers = ["科目编码", "借方金额", "备注", "其他"]
        sheet = _make_sheet(
            sheet_name="Sheet1",
            headers=headers,
        )
        result = identify(sheet)

        # With only 2/5 key columns matched, confidence should be below 80
        assert result.table_type_confidence < 80

    def test_level2_column_tier_assignment(self):
        """Verify key columns get tier='key', recommended get 'recommended', unknown get 'extra'."""
        headers = ["科目编码", "科目名称", "期初余额", "本期借方", "本期贷方", "期末余额", "自定义列"]
        sheet = _make_sheet(
            sheet_name="Sheet1",
            headers=headers,
        )
        result = identify(sheet)

        # Should be identified as balance
        assert result.table_type == "balance"

        # Check column tiers
        tier_map = {cm.column_header: cm.column_tier for cm in result.column_mappings}

        # Key columns for balance
        assert tier_map.get("科目编码") == "key"
        assert tier_map.get("期初余额") == "key"
        assert tier_map.get("本期借方") == "key"
        assert tier_map.get("本期贷方") == "key"
        assert tier_map.get("期末余额") == "key"

        # Recommended column
        assert tier_map.get("科目名称") == "recommended"

        # Unknown column → extra
        assert tier_map.get("自定义列") == "extra"


# ===========================================================================
# Level 3 — Content-based recognition
# ===========================================================================


class TestLevel3Content:
    """Level 3 识别：内容样本特征。"""

    def test_level3_date_column_nudge(self):
        """No L1/L2 match but data has date column → ledger with confidence 30-59."""
        # Use neutral headers that won't trigger L2
        headers = ["col_a", "col_b", "col_c", "col_d"]
        data_rows = [
            ["2025-01-15", "记-001", "购买办公用品", "500"],
            ["2025-02-20", "记-002", "支付房租", "3000"],
            ["2025-03-10", "记-003", "收到货款", "8000"],
        ]
        sheet = _make_sheet(
            sheet_name="数据",  # neutral name
            headers=headers,
            data_rows=data_rows,
        )
        result = identify(sheet)

        # L3 should detect date column and nudge toward ledger
        assert result.table_type == "ledger"
        assert 30 <= result.table_type_confidence <= 59

    def test_level3_numeric_columns_nudge(self):
        """No L1/L2 match but ≥4 numeric columns → balance with confidence 30-59."""
        # Use neutral headers that won't trigger L2
        headers = ["col_a", "col_b", "col_c", "col_d", "col_e"]
        data_rows = [
            ["item1", "10000", "5000", "3000", "12000"],
            ["item2", "20000", "8000", "6000", "22000"],
            ["item3", "30000", "12000", "9000", "33000"],
        ]
        sheet = _make_sheet(
            sheet_name="数据",
            headers=headers,
            data_rows=data_rows,
        )
        result = identify(sheet)

        # L3 should detect ≥4 numeric columns and nudge toward balance
        assert result.table_type == "balance"
        assert 30 <= result.table_type_confidence <= 59


# ===========================================================================
# Aggregation — L1 + L2 interaction
# ===========================================================================


class TestAggregation:
    """聚合逻辑：L1 + L2 一致/冲突。"""

    def test_aggregation_l1_l2_agree(self):
        """Both L1 and L2 say balance → confidence boosted, 'high'."""
        headers = ["科目编码", "科目名称", "期初余额", "本期借方", "本期贷方", "期末余额"]
        sheet = _make_sheet(
            sheet_name="科目余额表",  # L1 → balance
            headers=headers,          # L2 → balance
        )
        result = identify(sheet)

        assert result.table_type == "balance"
        assert result.confidence_level == "high"
        # Aggregated confidence should be ≥ 80
        assert result.table_type_confidence >= 80

    def test_aggregation_l1_l2_disagree(self):
        """L1 says balance, L2 says ledger → L2 wins, conflict=True in evidence."""
        # Sheet name suggests balance, but headers are clearly ledger
        headers = ["日期", "凭证号", "摘要", "科目编码", "借方金额", "贷方金额"]
        sheet = _make_sheet(
            sheet_name="余额表",  # L1 → balance
            headers=headers,      # L2 → ledger
        )
        result = identify(sheet)

        # L2 should win
        assert result.table_type == "ledger"
        # Evidence should record conflict
        evidence = result.detection_evidence
        assert evidence["final_choice"]["conflict"] is True
