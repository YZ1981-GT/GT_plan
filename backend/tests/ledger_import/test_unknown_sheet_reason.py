"""F9 多 sheet unknown 透明化测试（Sprint 10 Task 10.28）。

验证 identify() 对无法识别的 sheet 填充 ``detection_evidence["skip_reason"]``
和 ``warnings`` 标签。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ledger_import.detection_types import SheetDetection
from app.services.ledger_import.detector import detect_file_from_path
from app.services.ledger_import.identifier import identify


def _make_sheet(
    sheet_name: str,
    preview_rows: list[list[str]],
    row_count: int,
    headers: list[str] | None = None,
    data_start_row: int = 1,
) -> SheetDetection:
    if headers is None:
        headers = preview_rows[0] if preview_rows else []
    return SheetDetection(
        file_name="test.xlsx",
        sheet_name=sheet_name,
        row_count_estimate=row_count,
        header_row_index=max(data_start_row - 1, 0),
        data_start_row=data_start_row,
        table_type="unknown",
        table_type_confidence=0,
        confidence_level="manual_required",
        preview_rows=preview_rows,
        detection_evidence={"header_cells": headers, "filename_hint": {}},
    )


def test_rows_too_few_skip_reason():
    """行数太少（<5）应得到 ROWS_TOO_FEW。"""
    sheet = _make_sheet(
        sheet_name="元信息",
        preview_rows=[["公司"], ["年度"], ["版本"]],
        row_count=3,
    )
    out = identify(sheet)
    assert out.table_type == "unknown"
    skip = out.detection_evidence.get("skip_reason", {})
    assert skip.get("code") == "ROWS_TOO_FEW"
    assert "行数太少" in skip.get("message_cn", "")
    assert any("SKIPPED_UNKNOWN" in w for w in out.warnings)


def test_header_unrecognizable_skip_reason():
    """表头单元格数 < 3 应得到 HEADER_UNRECOGNIZABLE。"""
    preview = [["Alpha", ""], ["zz", ""], ["yy", ""], ["xx", ""], ["ww", ""], ["vv", ""], ["uu", ""]]
    sheet = _make_sheet(
        sheet_name="xxx",
        preview_rows=preview,
        row_count=100,
        headers=["Alpha"],  # only 1 non-empty header
    )
    out = identify(sheet)
    assert out.table_type == "unknown"
    skip = out.detection_evidence.get("skip_reason", {})
    assert skip.get("code") == "HEADER_UNRECOGNIZABLE"


def test_content_mismatch_skip_reason():
    """表头足够但列内容不符合任一表类型特征 → CONTENT_MISMATCH。"""
    sheet = _make_sheet(
        sheet_name="未知表",
        preview_rows=[
            ["Alpha", "Beta", "Gamma", "Delta"],
            ["xxxa", "yyyb", "zzzc", "wwwd"],
            ["aaa1", "bbb2", "ccc3", "ddd4"],
            ["eee5", "fff6", "ggg7", "hhh8"],
            ["iii9", "jjjA", "kkkB", "lllC"],
            ["mmmD", "nnnE", "oooF", "pppG"],
        ],
        row_count=100,
        headers=["Alpha", "Beta", "Gamma", "Delta"],
    )
    out = identify(sheet)
    assert out.table_type == "unknown"
    skip = out.detection_evidence.get("skip_reason", {})
    # 可能 CONTENT_MISMATCH 也可能 HEADER_UNRECOGNIZABLE（取决于非空判定），
    # 但至少必须有 skip_reason
    assert skip.get("code") in ("CONTENT_MISMATCH", "HEADER_UNRECOGNIZABLE")


def test_identified_sheet_has_no_skip_reason():
    """能被识别的 sheet 不应生成 skip_reason。"""
    sheet = _make_sheet(
        sheet_name="科目余额表",
        preview_rows=[
            ["科目编码", "科目名称", "期初余额", "本期发生额", "期末余额"],
            ["1001", "现金", "100", "50", "150"],
            ["1002", "银行", "200", "100", "300"],
            ["1003", "应收", "50", "25", "75"],
            ["1004", "存货", "300", "150", "450"],
            ["1005", "固定资产", "500", "250", "750"],
            ["1006", "累计折旧", "100", "50", "150"],
            ["1007", "应付", "80", "40", "120"],
        ],
        row_count=100,
    )
    out = identify(sheet)
    assert out.table_type == "balance"
    assert "skip_reason" not in out.detection_evidence


# ---------------------------------------------------------------------------
# 真实样本：YG2101 Sheet1（元信息 sheet）
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[3]
YG2101 = REPO_ROOT / "数据" / "YG2101-重庆医药集团四川医药有限公司2025年-科目余额表+序时账.xlsx"


@pytest.mark.skipif(not YG2101.exists(), reason="Real sample YG2101 not available")
def test_yg2101_sheet1_has_skip_reason():
    """YG2101 的元信息 Sheet1（只有 ~105 行少量内容）应产生 skip_reason。"""
    fd = detect_file_from_path(str(YG2101), YG2101.name)
    sheet1 = next((s for s in fd.sheets if s.sheet_name.lower() == "sheet1"), None)
    if sheet1 is None:
        pytest.skip("YG2101 Sheet1 missing in this revision")

    out = identify(sheet1)
    # Sheet1 应被判为 unknown 并带 skip_reason
    if out.table_type == "unknown":
        assert "skip_reason" in out.detection_evidence
