"""F6 文件名元信息利用测试（Sprint 10 Task 10.15）。

覆盖 ``_extract_filename_hints`` 纯函数 + ``identify()`` 对
filename_hint 的消费路径。
"""

from __future__ import annotations

import pytest

from app.services.ledger_import.detector import _extract_filename_hints
from app.services.ledger_import.detection_types import SheetDetection
from app.services.ledger_import.identifier import identify


class TestExtractFilenameHints:
    def test_balance_keyword(self):
        hints = _extract_filename_hints("辽宁卫生服务有限公司-科目余额表.xlsx")
        assert hints["table_type"] == "balance"
        assert hints["table_confidence"] >= 65
        assert "余额" in hints["matched_keyword"]

    def test_ledger_keyword(self):
        hints = _extract_filename_hints("辽宁卫生-序时账.xlsx")
        assert hints["table_type"] == "ledger"
        assert hints["table_confidence"] >= 65

    def test_voucher_detail_keyword(self):
        hints = _extract_filename_hints("公司凭证明细2024.xlsx")
        assert hints["table_type"] == "ledger"

    def test_aux_balance(self):
        hints = _extract_filename_hints("某公司辅助余额表.xlsx")
        assert hints["table_type"] == "aux_balance"

    def test_period_year_month_chinese(self):
        hints = _extract_filename_hints("序时账-陕西华氏-25年10月.xlsx")
        assert hints["year"] == 2025
        assert hints["month"] == 10

    def test_period_dotted_two_digit(self):
        hints = _extract_filename_hints("序时账-陕西华氏-24.1.xlsx")
        assert hints["year"] == 2024
        assert hints["month"] == 1

    def test_period_only_year(self):
        hints = _extract_filename_hints("XX公司2024余额表.xlsx")
        assert hints.get("year") == 2024
        assert hints["table_type"] == "balance"

    def test_no_match_returns_empty(self):
        hints = _extract_filename_hints("somerandomname.xlsx")
        # file_stem always present
        assert "file_stem" in hints
        # but no table_type
        assert "table_type" not in hints

    def test_empty_input(self):
        assert _extract_filename_hints("") == {}

    def test_english_keyword(self):
        hints = _extract_filename_hints("TB_2024.xlsx")
        assert hints.get("table_type") == "balance"

    def test_longest_keyword_wins(self):
        # "科目余额" (4 chars) should win over "余额表" (3 chars) when both match
        hints = _extract_filename_hints("某公司科目余额表2024.xlsx")
        assert hints["table_type"] == "balance"
        assert hints["table_confidence"] == 75  # longer keyword → higher conf


class TestIdentifyConsumesFilenameHint:
    def _make_sheet(
        self,
        sheet_name: str,
        file_name: str,
        headers: list[str],
        filename_hint_dict: dict | None = None,
    ) -> SheetDetection:
        """构造一个最简 SheetDetection，evidence 含 filename_hint。"""
        return SheetDetection(
            file_name=file_name,
            sheet_name=sheet_name,
            row_count_estimate=100,
            header_row_index=0,
            data_start_row=1,
            table_type="unknown",
            table_type_confidence=0,
            confidence_level="manual_required",
            preview_rows=[headers, ["1001", "现金", "100", "50", "150"]],
            detection_evidence={
                "header_cells": headers,
                "filename_hint": filename_hint_dict or {},
            },
        )

    def test_filename_hint_rescues_generic_sheet_name(self):
        """sheet 名 'sheet1' 无信号时，filename_hint 应补救为 balance。"""
        hints = {"table_type": "balance", "table_confidence": 70, "file_stem": "科目余额表"}
        sheet = self._make_sheet(
            sheet_name="sheet1",
            file_name="科目余额表.xlsx",
            headers=["科目编码", "科目名称", "期初余额", "本期发生额", "期末余额"],
            filename_hint_dict=hints,
        )
        out = identify(sheet)
        # L2 应该也识别出 balance（表头匹配），这里主要验证 evidence 记录了 filename_hint
        assert out.table_type == "balance"
        # evidence 保留了 filename_hint
        assert out.detection_evidence.get("filename_hint", {}).get("table_type") == "balance"

    def test_filename_hint_not_override_strong_sheet_name(self):
        """当 sheet 名强信号 ≥ 60 时，filename_hint 不应覆盖 L1。"""
        hints = {"table_type": "ledger", "table_confidence": 70}
        sheet = self._make_sheet(
            sheet_name="科目余额表",  # 强 L1 信号
            file_name="some_random.xlsx",
            headers=["科目编码", "科目名称", "期初余额", "本期发生额", "期末余额"],
            filename_hint_dict=hints,
        )
        out = identify(sheet)
        # L1 "科目余额表" score=90 > 60，不应被 filename hint (70) 覆盖
        assert out.table_type == "balance"
