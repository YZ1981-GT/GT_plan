"""F7 方括号 + 组合表头测试（Sprint 10 Task 10.20）。

覆盖 ``_normalize_header`` / ``_normalize_header_row`` 纯函数 + 和平物流样本
置信度 ≥85 端到端场景。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ledger_import.detector import (
    _normalize_header,
    _normalize_header_row,
    detect_file_from_path,
)
from app.services.ledger_import.identifier import identify


class TestNormalizeHeader:
    def test_plain_header(self):
        assert _normalize_header("科目编码") == ("科目编码", ["科目编码"])

    def test_half_width_brackets(self):
        assert _normalize_header("[凭证号码]") == ("凭证号码", ["凭证号码"])

    def test_full_width_brackets(self):
        assert _normalize_header("【凭证号码】") == ("凭证号码", ["凭证号码"])

    def test_bracket_with_compound(self):
        p, subs = _normalize_header("[凭证号码]#[日期]")
        assert p == "凭证号码#日期"
        assert subs == ["凭证号码", "日期"]

    def test_plain_compound(self):
        p, subs = _normalize_header("凭证号码#日期")
        assert p == "凭证号码#日期"
        assert subs == ["凭证号码", "日期"]

    def test_pipe_compound(self):
        p, subs = _normalize_header("科目|编码")
        assert p == "科目#编码"  # compound primary joined with #
        assert subs == ["科目", "编码"]

    def test_empty(self):
        assert _normalize_header("") == ("", [])
        assert _normalize_header(None) == ("", [])

    def test_whitespace_only(self):
        assert _normalize_header("  ") == ("", [])

    def test_no_bracket_no_compound(self):
        assert _normalize_header(" 借方金额 ") == ("借方金额", ["借方金额"])


class TestNormalizeHeaderRow:
    def test_mixed_row(self):
        cells = ["[科目编码]", "[凭证号码]#[日期]", "借方金额", "贷方金额"]
        normalized, compound = _normalize_header_row(cells)
        assert normalized == ["科目编码", "凭证号码#日期", "借方金额", "贷方金额"]
        assert compound == {1: ["凭证号码", "日期"]}

    def test_no_compound(self):
        cells = ["科目编码", "科目名称", "期末余额"]
        normalized, compound = _normalize_header_row(cells)
        assert normalized == cells
        assert compound == {}


# ---------------------------------------------------------------------------
# 端到端场景：和平物流样本 conf ≥ 85
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[3]
HEPING_LOGISTICS = (
    REPO_ROOT / "数据" / "和平物流25加工账-药品批发.xlsx"
)


@pytest.mark.skipif(
    not HEPING_LOGISTICS.exists(),
    reason="Real sample 和平物流25加工账-药品批发.xlsx not available",
)
def test_heping_logistics_compound_header_identified():
    """F7 验收：和平物流序时账 [凭证号码]#[日期] 等方括号表头识别后，
    关键列（voucher_no / voucher_date / account_code）能被 identifier 正确映射，
    表类型置信度 ≥ 85。
    """
    fd = detect_file_from_path(str(HEPING_LOGISTICS), HEPING_LOGISTICS.name)
    ledger_sheets = [s for s in fd.sheets if s.sheet_name == "序时账"]
    assert ledger_sheets, f"sheets={[s.sheet_name for s in fd.sheets]}"

    sheet = ledger_sheets[0]
    # detector 层已提取 compound_headers
    assert sheet.detection_evidence.get("compound_headers"), (
        "compound_headers 应存在（[凭证号码]#[日期] 至少 1 列）"
    )
    # header_cells 已剥方括号
    raw_cells = sheet.detection_evidence.get("header_cells_raw", [])
    normalized_cells = sheet.detection_evidence.get("header_cells", [])
    assert any("[" in c for c in raw_cells), "原始 header_cells_raw 应含方括号"
    assert not any("[" in c for c in normalized_cells if c), (
        f"normalized header_cells 不应含方括号，得到 {normalized_cells}"
    )

    identified = identify(sheet)
    assert identified.table_type == "ledger", (
        f"序时账应识别为 ledger，实际={identified.table_type}"
    )
    assert identified.table_type_confidence >= 85, (
        f"置信度应 ≥85，实际={identified.table_type_confidence}"
    )

    # 关键列至少命中 voucher_no + voucher_date + account_code
    matched_fields = {
        cm.standard_field for cm in identified.column_mappings if cm.standard_field
    }
    assert {"voucher_no", "voucher_date", "account_code"}.issubset(matched_fields), (
        f"关键列应覆盖 voucher_no/voucher_date/account_code，实际={matched_fields}"
    )
