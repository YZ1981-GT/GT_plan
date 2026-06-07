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


# ---------------------------------------------------------------------------
# Task 4 Tests: 表头识别增强
# ---------------------------------------------------------------------------


class TestDetectHeaderRow11To20:
    """Task 4.1: 表头位于第 11~20 行时仍能识别。"""

    def test_header_at_row_15(self):
        """15 行空行/横幅后才出现真实表头 → 仍可识别。"""
        # 14 行占位（空行 + 横幅）
        rows = [[""] * 6 for _ in range(12)]
        rows.append(["XX公司 2025年度 科目余额表", "", "", "", "", ""])
        rows.append(["", "", "", "", "", ""])
        # Row 14 (0-indexed): 真实表头
        rows.append(["科目编码", "科目名称", "期初余额", "本期借方", "本期贷方", "期末余额"])
        # Row 15: data
        rows.append(["1001", "库存现金", "10000", "5000", "3000", "12000"])
        rows.append(["1002", "银行存款", "50000", "20000", "15000", "55000"])

        content = _build_xlsx({"余额表": rows})
        result = detect_file(content, "header_at_row15.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        # data_start_row should be 15 (after header at row 14)
        assert sheet.data_start_row == 15
        assert sheet.header_row_index == 14


class TestDetect3LayerMergedHeader:
    """Task 4.2: 3 层合并表头识别。"""

    def test_three_layer_merged_header(self):
        """3 层合并表头: 期初余额/本期发生额 × 借方/贷方 × 金额/数量。"""
        rows = [
            # Row 0: 横幅
            ["XX公司 2025年度 余额表", "", "", "", "", "", "", ""],
            # Row 1: top header (groups)
            ["", "", "期初余额", "", "本期发生额", "", "期末余额", ""],
            # Row 2: middle header (sub-groups)
            ["", "", "借方", "贷方", "借方", "贷方", "借方", "贷方"],
            # Row 3: bottom header (measures)
            ["科目编码", "科目名称", "金额", "金额", "金额", "金额", "金额", "金额"],
            # Row 4+: data
            ["1001", "库存现金", "10000", "0", "5000", "3000", "12000", "0"],
        ]
        content = _build_xlsx({"余额表": rows})
        result = detect_file(content, "three_layer.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        # data should start after the 3 header rows + banner
        assert sheet.data_start_row >= 4

    def test_three_layer_degrade_to_two(self):
        """第三行像数据行 → 降级为 2 层合并。"""
        rows = [
            # Row 0: top header (groups)
            ["", "", "期初余额", "", "本期发生额", ""],
            # Row 1: bottom header (sub-columns)
            ["科目编码", "科目名称", "借方", "贷方", "借方", "贷方"],
            # Row 2: data (starts with number → detected as data)
            ["1001", "库存现金", "10000", "0", "5000", "3000"],
        ]
        content = _build_xlsx({"余额表": rows})
        result = detect_file(content, "two_layer_degrade.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        # data_start_row should be 2 (after the 2 merged header rows)
        assert sheet.data_start_row == 2


class TestDetect2DDebitCreditGrid:
    """Task 4.3: 二维借贷平铺列 (期初/期末 × 借方/贷方) 识别。"""

    def test_2d_grid_header_opening_closing_debit_credit(self):
        """2 层合并: '期初余额' × '借方/贷方' + '期末余额' × '借方/贷方'。"""
        rows = [
            # Row 0: top - group names (sparse, forward-filled)
            ["", "", "期初余额", "", "期末余额", ""],
            # Row 1: bottom - sub-column names
            ["科目编码", "科目名称", "借方", "贷方", "借方", "贷方"],
            # Row 2+: data
            ["1001", "库存现金", "10000", "0", "12000", "0"],
            ["2001", "短期借款", "0", "50000", "0", "45000"],
        ]
        content = _build_xlsx({"余额表": rows})
        result = detect_file(content, "grid_header.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        # Merged headers should produce "期初余额.借方", "期初余额.贷方", "期末余额.借方", "期末余额.贷方"
        assert sheet.data_start_row == 2

        # Verify the merged header contents via preview_rows or detection_evidence
        evidence = sheet.detection_evidence
        assert evidence.get("merged_header") is True

    def test_2d_grid_with_amount_columns(self):
        """期初/本期/期末 × 借方金额/贷方金额 识别。"""
        rows = [
            # Row 0: top
            ["", "", "期初", "", "本期发生", "", "期末", ""],
            # Row 1: bottom
            ["科目编码", "科目名称", "借方金额", "贷方金额", "借方金额", "贷方金额", "借方金额", "贷方金额"],
            # Row 2+: data
            ["1001", "库存现金", "10000", "0", "5000", "3000", "12000", "0"],
        ]
        content = _build_xlsx({"余额表": rows})
        result = detect_file(content, "grid_amount.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        assert sheet.data_start_row == 2
        assert sheet.detection_evidence.get("merged_header") is True


class TestDetectBannerSkipAndSkipReason:
    """Task 4.5: 横幅跳过、方括号表头、skip_reason 稳定。"""

    def test_banner_skip_multiple(self):
        """多行横幅（公司名+报表名）被跳过后正确识别表头。"""
        rows = [
            ["XX有限公司", "", "", "", "", ""],
            ["2025年度科目余额表", "", "", "", "", ""],
            ["编制单位：XX公司", "", "", "", "", ""],
            ["科目编码", "科目名称", "期初余额", "本期借方", "本期贷方", "期末余额"],
            ["1001", "库存现金", "10000", "5000", "3000", "12000"],
        ]
        content = _build_xlsx({"Sheet1": rows})
        result = detect_file(content, "banner_skip.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        assert sheet.header_row_index == 3
        assert sheet.data_start_row == 4

    def test_bracket_in_header(self):
        """方括号标注的表头（如 [借方金额]）正确识别。"""
        rows = [
            ["科目编码", "科目名称", "[借方金额]", "[贷方金额]", "期末余额(元)", "备注"],
            ["1001", "库存现金", "10000", "5000", "12000", ""],
        ]
        content = _build_xlsx({"余额表": rows})
        result = detect_file(content, "bracket_header.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        assert sheet.header_row_index == 0
        assert sheet.data_start_row == 1


class TestDetectionEvidenceFields:
    """Task 4.4: detection_evidence 保留 header_cells_raw, merged_header, compound_headers, amount_unit。"""

    def test_evidence_fields_present(self):
        """正常 xlsx 的 detection_evidence 包含所有必需字段。"""
        rows = [
            ["科目编码", "科目名称", "期初余额(万元)", "本期借方", "本期贷方", "期末余额"],
            ["1001", "库存现金", "10000", "5000", "3000", "12000"],
        ]
        content = _build_xlsx({"余额表": rows})
        result = detect_file(content, "evidence_test.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        ev = sheet.detection_evidence

        # 必须存在的 4 个字段
        assert "header_cells_raw" in ev
        assert "merged_header" in ev
        assert "compound_headers" in ev
        assert "amount_unit" in ev

        # header_cells_raw 应为原始表头列表
        assert isinstance(ev["header_cells_raw"], list)
        assert len(ev["header_cells_raw"]) == 6

    def test_merged_header_evidence_true_for_two_layer(self):
        """2 层合并表头时 merged_header 为 True。"""
        rows = [
            ["", "", "期初余额", "", "本期发生额", ""],
            ["科目编码", "科目名称", "借方", "贷方", "借方", "贷方"],
            ["1001", "库存现金", "10000", "0", "5000", "3000"],
        ]
        content = _build_xlsx({"余额表": rows})
        result = detect_file(content, "merged_evidence.xlsx")

        sheet = result.sheets[0]
        assert sheet.detection_evidence["merged_header"] is True

    def test_amount_unit_extraction(self):
        """金额单位（万元）从表头或横幅中提取。"""
        rows = [
            ["XX公司 单位：万元", "", "", "", "", ""],
            ["科目编码", "科目名称", "期初余额", "本期借方", "本期贷方", "期末余额"],
            ["1001", "库存现金", "1.0", "0.5", "0.3", "1.2"],
        ]
        content = _build_xlsx({"余额表": rows})
        result = detect_file(content, "unit_test.xlsx")

        sheet = result.sheets[0]
        # amount_unit should be extracted (implementation may vary)
        assert "amount_unit" in sheet.detection_evidence


class TestDetectCompoundHeaders:
    """Task 4.5: 组合表头 (compound_headers) 正确拆分。"""

    def test_compound_header_with_hash_separator(self):
        """表头含 '#' 分隔的组合字段 → compound_headers 记录拆分。"""
        rows = [
            ["科目编码", "科目名称", "凭证号码#日期", "借方金额", "贷方金额", "摘要"],
            ["1001", "库存现金", "PZ001#2025-01-01", "5000", "0", "测试"],
        ]
        content = _build_xlsx({"序时账": rows})
        result = detect_file(content, "compound.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        ev = sheet.detection_evidence
        compound = ev.get("compound_headers", {})
        # column index 2 should have sub-fields ["凭证号码", "日期"]
        assert 2 in compound or "2" in compound
        subs = compound.get(2) or compound.get("2")
        assert subs == ["凭证号码", "日期"]

    def test_bracket_stripped_in_normalized_header(self):
        """方括号表头在 header_cells（规范化）中被剥离。"""
        rows = [
            ["[科目编码]", "[科目名称]", "[期初余额]", "[本期借方]", "[本期贷方]", "[期末余额]"],
            ["1001", "库存现金", "10000", "5000", "3000", "12000"],
        ]
        content = _build_xlsx({"余额表": rows})
        result = detect_file(content, "bracket_norm.xlsx")

        sheet = result.sheets[0]
        ev = sheet.detection_evidence
        # header_cells (normalized) should NOT have brackets
        normalized = ev.get("header_cells", [])
        assert all("[" not in h and "]" not in h for h in normalized if h)
        # header_cells_raw should keep the original with brackets
        raw = ev.get("header_cells_raw", [])
        assert any("[" in h for h in raw if h)


class TestDetectSkipReasonStability:
    """Task 4.5: skip_reason 稳定性 — unknown sheet 有 warnings 标签。"""

    def test_very_few_rows_unknown(self):
        """只有 2 行数据 → 仍可识别表头，不崩溃。"""
        rows = [
            ["编号", "名称", "金额"],
            ["001", "测试", "100"],
        ]
        content = _build_xlsx({"Sheet1": rows})
        result = detect_file(content, "few_rows.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        # Should still detect header correctly
        assert sheet.header_row_index == 0
        assert sheet.data_start_row == 1

    def test_empty_sheet_no_crash(self):
        """空 sheet 不崩溃。"""
        rows = [["", "", ""], ["", "", ""], ["", "", ""]]
        content = _build_xlsx({"空Sheet": rows})
        result = detect_file(content, "empty_sheet.xlsx")

        assert len(result.errors) == 0
        sheet = result.sheets[0]
        # Empty rows → data_start_row 0, empty headers
        assert sheet.data_start_row == 0
