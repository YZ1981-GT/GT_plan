"""Unit tests for backend.app.services.ledger_import.detector.

Covers Sprint 1 Task 20 — detector 基础用例（需求 1、2）：
- xlsx 基本探测
- xlsx 合并表头
- CSV UTF-8
- CSV GBK
- .xls 不支持
- 不支持的扩展名
- 损坏的 xlsx
- ZIP 内含 xlsx
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.services.ledger_import.detector import detect_file
from app.services.ledger_import.errors import ErrorCode


# ---------------------------------------------------------------------------
# Helpers: build in-memory xlsx fixtures using openpyxl
# ---------------------------------------------------------------------------


def _build_xlsx(sheets: dict[str, list[list[str]]]) -> bytes:
    """Build an in-memory xlsx file with given sheets and rows."""
    import openpyxl

    wb = openpyxl.Workbook()
    first = True
    for sheet_name, rows in sheets.items():
        if first:
            ws = wb.active
            ws.title = sheet_name
            first = False
        else:
            ws = wb.create_sheet(title=sheet_name)
        for row in rows:
            ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDetectXlsxBasic:
    """test_detect_xlsx_basic — simple xlsx with 1 sheet."""

    def test_detect_xlsx_basic(self):
        headers = ["科目编码", "科目名称", "期初余额", "本期借方", "本期贷方", "期末余额"]
        data = [
            ["1001", "库存现金", "10000", "5000", "3000", "12000"],
            ["1002", "银行存款", "50000", "20000", "15000", "55000"],
        ]
        content = _build_xlsx({"余额表": [headers] + data})

        result = detect_file(content, "test_balance.xlsx")

        assert result.file_type == "xlsx"
        assert result.file_name == "test_balance.xlsx"
        assert len(result.sheets) == 1
        assert len(result.errors) == 0

        sheet = result.sheets[0]
        assert sheet.sheet_name == "余额表"
        assert len(sheet.preview_rows) == 3  # 1 header + 2 data rows
        assert sheet.header_row_index == 0
        assert sheet.data_start_row == 1


class TestDetectXlsxMergedHeader:
    """test_detect_xlsx_merged_header — banner row + 2-row merged header + data."""

    def test_detect_xlsx_merged_header(self):
        # Row 0: banner (single cell spanning conceptually)
        # Row 1: top header (sparse — simulates merged cells)
        # Row 2: bottom header (dense)
        # Row 3+: data
        rows = [
            ["XX公司 2025年度 科目余额表", "", "", "", "", ""],
            ["期初余额", "", "", "本期发生额", "", ""],
            ["借方", "贷方", "余额", "借方", "贷方", "余额"],
            ["10000", "5000", "5000", "3000", "2000", "6000"],
            ["20000", "10000", "10000", "5000", "3000", "12000"],
        ]
        content = _build_xlsx({"余额表": rows})

        result = detect_file(content, "merged_header.xlsx")

        assert len(result.errors) == 0
        assert len(result.sheets) == 1

        sheet = result.sheets[0]
        # Banner row skipped, then 2-row merged header detected
        assert sheet.detection_evidence.get("merged_header") is True
        # data_start_row should be >= 3 (after banner + 2 header rows)
        assert sheet.data_start_row >= 3


class TestDetectCsvUtf8:
    """test_detect_csv_utf8 — CSV with utf-8 content."""

    def test_detect_csv_utf8(self):
        csv_content = "科目编码,科目名称,期初余额\n1001,库存现金,10000\n1002,银行存款,50000\n"
        content = csv_content.encode("utf-8")

        result = detect_file(content, "balance.csv")

        assert result.file_type == "csv"
        assert result.encoding is not None
        # encoding should be utf-8 or utf-8-sig
        assert "utf" in result.encoding.lower()
        assert len(result.sheets) == 1
        assert len(result.errors) == 0

        sheet = result.sheets[0]
        assert sheet.sheet_name == "balance"  # derived from filename without ext
        assert len(sheet.preview_rows) >= 2


class TestDetectCsvGbk:
    """test_detect_csv_gbk — CSV with gbk-encoded Chinese."""

    def test_detect_csv_gbk(self):
        csv_content = "科目编码,科目名称,期初余额\n1001,库存现金,10000\n"
        content = csv_content.encode("gbk")

        result = detect_file(content, "balance_gbk.csv")

        assert result.file_type == "csv"
        assert result.encoding is not None
        # Should detect as gbk or gb18030
        assert result.encoding.lower() in ("gbk", "gb18030", "gb2312")
        assert len(result.sheets) == 1
        assert len(result.errors) == 0


class TestDetectXlsUnsupported:
    """test_detect_xls_unsupported — .xls extension returns XLS_NOT_SUPPORTED."""

    def test_detect_xls_unsupported(self):
        # Content doesn't matter — extension triggers the error
        content = b"fake xls content"

        result = detect_file(content, "old_file.xls")

        assert result.file_type == "xls"
        assert len(result.errors) == 1
        assert result.errors[0].code == ErrorCode.XLS_NOT_SUPPORTED
        assert result.errors[0].severity == "fatal"


class TestDetectUnsupportedExtension:
    """test_detect_unsupported_extension — .docx returns UNSUPPORTED_FILE_TYPE."""

    def test_detect_unsupported_extension(self):
        content = b"fake docx content"

        result = detect_file(content, "document.docx")

        assert len(result.errors) == 1
        assert result.errors[0].code == ErrorCode.UNSUPPORTED_FILE_TYPE
        assert result.errors[0].severity == "fatal"


class TestDetectCorruptedXlsx:
    """test_detect_corrupted_xlsx — garbage bytes as .xlsx returns CORRUPTED_FILE."""

    def test_detect_corrupted_xlsx(self):
        content = b"this is not a valid xlsx file at all \x00\x01\x02\x03"

        result = detect_file(content, "corrupted.xlsx")

        assert result.file_type == "xlsx"
        assert len(result.errors) >= 1
        error_codes = [e.code for e in result.errors]
        assert ErrorCode.CORRUPTED_FILE in error_codes


class TestDetectZipWithXlsx:
    """test_detect_zip_with_xlsx — zip containing an xlsx extracts sheets with prefixed file_name."""

    def test_detect_zip_with_xlsx(self):
        # Build an xlsx first
        headers = ["科目编码", "科目名称", "期初余额"]
        data = [["1001", "库存现金", "10000"]]
        xlsx_content = _build_xlsx({"Sheet1": [headers] + data})

        # Pack it into a zip
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("inner_book.xlsx", xlsx_content)
        zip_content = zip_buf.getvalue()

        result = detect_file(zip_content, "archive.zip")

        assert result.file_type == "zip"
        assert len(result.errors) == 0
        assert len(result.sheets) >= 1

        # Sheets should have prefixed file_name
        sheet = result.sheets[0]
        assert "archive.zip!" in sheet.file_name
        assert "inner_book.xlsx" in sheet.file_name
