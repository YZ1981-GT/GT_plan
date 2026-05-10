"""F8 表类型鲁棒性测试（Sprint 10 Task 10.24）。

验证：
1. 通用 sheet 名（sheet1 / 列表数据）不影响 L2 表头识别（中性评分）
2. 同一 workbook 内含 aux_type 列的"余额表"被识别为 aux_balance
3. 不含 aux_type 的余额表被识别为 balance
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ledger_import.detection_types import SheetDetection
from app.services.ledger_import.detector import detect_file_from_path
from app.services.ledger_import.identifier import identify


def _make_sheet(sheet_name: str, headers: list[str]) -> SheetDetection:
    preview = [headers] + [
        [f"C{i}", "科目", "100", "50", "150", "类型A", "编码1"][: len(headers)]
        for i in range(8)
    ]
    return SheetDetection(
        file_name="test.xlsx",
        sheet_name=sheet_name,
        row_count_estimate=100,
        header_row_index=0,
        data_start_row=1,
        table_type="unknown",
        table_type_confidence=0,
        confidence_level="manual_required",
        preview_rows=preview,
        detection_evidence={"header_cells": headers, "filename_hint": {}},
    )


class TestGenericSheetNameNeutral:
    def test_sheet1_still_identifies_balance_by_headers(self):
        """sheet1 + 余额表表头 → 识别为 balance（不被通用名拖累）。"""
        sheet = _make_sheet(
            "sheet1",
            ["科目编码", "科目名称", "期初余额", "本期发生额", "期末余额"],
        )
        out = identify(sheet)
        assert out.table_type == "balance"

    def test_data_list_still_identifies_ledger(self):
        """列表数据 + 序时账表头 → 识别为 ledger。"""
        sheet = _make_sheet(
            "列表数据",
            ["凭证日期", "凭证号", "科目编码", "借方金额", "贷方金额"],
        )
        out = identify(sheet)
        assert out.table_type == "ledger"


class TestBalanceVariantDiscrimination:
    def test_plain_balance_without_aux(self):
        """不含 aux_type 列的余额表 → balance。"""
        sheet = _make_sheet(
            "科目余额表",
            ["科目编码", "科目名称", "期初余额", "本期发生额", "期末余额"],
        )
        out = identify(sheet)
        assert out.table_type == "balance"

    def test_aux_balance_with_aux_type_column(self):
        """含 aux_type + aux_code 列的余额表 → aux_balance。"""
        sheet = _make_sheet(
            "科目余额表有核算维度",
            [
                "科目编码",
                "科目名称",
                "期初余额",
                "本期发生额",
                "期末余额",
                "辅助核算类型",
                "核算项目编码",
            ],
        )
        out = identify(sheet)
        assert out.table_type == "aux_balance"


# ---------------------------------------------------------------------------
# 真实样本：安徽骨科（同 workbook 双余额表分流）
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[3]
ANHUI = REPO_ROOT / "数据" / "余额表+序时账-安徽-骨科.xlsx"


@pytest.mark.skipif(not ANHUI.exists(), reason="Real sample 安徽骨科 not available")
def test_anhui_dual_balance_split():
    """安徽骨科 workbook 若有两张余额表（有维度 + 无维度），应分别识别为
    aux_balance 和 balance。
    """
    fd = detect_file_from_path(str(ANHUI), ANHUI.name)
    # 找所有"余额表"相关 sheet
    balance_sheets = [
        s for s in fd.sheets if "余额" in s.sheet_name or "科目" in s.sheet_name
    ]
    if not balance_sheets:
        pytest.skip("安徽骨科 workbook 未含余额表 sheet")

    identified = [identify(s) for s in balance_sheets]
    types = {i.table_type for i in identified}
    # 至少应识别为 balance 或 aux_balance 之一（不该全是 unknown）
    assert types & {"balance", "aux_balance"}, (
        f"安徽骨科余额表识别失败：{[(i.sheet_name, i.table_type) for i in identified]}"
    )
