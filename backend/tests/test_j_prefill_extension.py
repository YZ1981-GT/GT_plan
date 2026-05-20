"""
test_j_prefill_extension.py — J-F6 prefill 扩展 ≥ 40 cells 验证

验证内容：
1. 新增 cells ≥ 40
2. 4-arg AUX 格式校验（逗号数 == 3 即 4 args）
3. 真实 sheet 名校验（含末尾空格）
4. 幂等保护：(wp_code, sheet) 唯一
5. 公式类型分布合理
"""
import json
import re
from pathlib import Path

import pytest

DATA_FILE = Path(__file__).parent.parent / "data" / "prefill_formula_mapping.json"

# J 循环新增 sheet 列表（openpyxl 实测真实名称，含末尾空格）
J_NEW_SHEETS = {
    "明细表J1-2 ",          # 末尾带空格
    "月度分析表J1-4",
    "计提情况检查表J1-6",
    "分配情况检查表J1-7",
    "明细表J2-2",
    "股份支付检查表J3-2",
}

# 已有 J 循环 prefill sheets（不计入新增）
J_EXISTING_SHEETS = {
    "审定表J1-1",
    "审定表J1-1 ",
    "审定表J2-1",
    "审定表J3-1",
    "分析程序J1-3",
}


@pytest.fixture
def prefill_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def j_new_entries(prefill_data):
    """获取 J 循环新增 prefill entries（按 sheet 名过滤）"""
    entries = []
    for m in prefill_data["mappings"]:
        if m["sheet"] in J_NEW_SHEETS:
            entries.append(m)
    return entries


@pytest.fixture
def j_new_cells(j_new_entries):
    """获取所有新增 cells"""
    cells = []
    for entry in j_new_entries:
        for cell in entry["cells"]:
            cells.append({**cell, "_sheet": entry["sheet"], "_wp_code": entry["wp_code"]})
    return cells


class TestJPrefillCellCount:
    """验证新增 cells ≥ 40"""

    def test_total_new_cells_at_least_40(self, j_new_cells):
        assert len(j_new_cells) >= 40, (
            f"Expected ≥ 40 new J-cycle prefill cells, got {len(j_new_cells)}"
        )

    def test_j1_2_at_least_8_cells(self, j_new_entries):
        entry = next((e for e in j_new_entries if e["sheet"] == "明细表J1-2 "), None)
        assert entry is not None, "明细表J1-2  entry not found"
        assert len(entry["cells"]) >= 8, (
            f"Expected ≥ 8 cells for 明细表J1-2 , got {len(entry['cells'])}"
        )

    def test_j1_4_at_least_8_cells(self, j_new_entries):
        entry = next((e for e in j_new_entries if e["sheet"] == "月度分析表J1-4"), None)
        assert entry is not None, "月度分析表J1-4 entry not found"
        assert len(entry["cells"]) >= 8, (
            f"Expected ≥ 8 cells for 月度分析表J1-4, got {len(entry['cells'])}"
        )

    def test_j1_6_at_least_10_cells(self, j_new_entries):
        entry = next((e for e in j_new_entries if e["sheet"] == "计提情况检查表J1-6"), None)
        assert entry is not None, "计提情况检查表J1-6 entry not found"
        assert len(entry["cells"]) >= 10, (
            f"Expected ≥ 10 cells for 计提情况检查表J1-6, got {len(entry['cells'])}"
        )

    def test_j1_7_at_least_8_cells(self, j_new_entries):
        entry = next((e for e in j_new_entries if e["sheet"] == "分配情况检查表J1-7"), None)
        assert entry is not None, "分配情况检查表J1-7 entry not found"
        assert len(entry["cells"]) >= 8, (
            f"Expected ≥ 8 cells for 分配情况检查表J1-7, got {len(entry['cells'])}"
        )

    def test_j2_2_at_least_4_cells(self, j_new_entries):
        entry = next((e for e in j_new_entries if e["sheet"] == "明细表J2-2"), None)
        assert entry is not None, "明细表J2-2 entry not found"
        assert len(entry["cells"]) >= 4, (
            f"Expected ≥ 4 cells for 明细表J2-2, got {len(entry['cells'])}"
        )

    def test_j3_2_at_least_4_cells(self, j_new_entries):
        entry = next((e for e in j_new_entries if e["sheet"] == "股份支付检查表J3-2"), None)
        assert entry is not None, "股份支付检查表J3-2 entry not found"
        assert len(entry["cells"]) >= 4, (
            f"Expected ≥ 4 cells for 股份支付检查表J3-2, got {len(entry['cells'])}"
        )


class TestJPrefillAuxFormat:
    """验证 4-arg AUX 格式"""

    def test_all_aux_formulas_have_4_args(self, j_new_cells):
        """=AUX 公式必须有 4 个参数（逗号数 == 3）"""
        aux_cells = [c for c in j_new_cells if c["formula"].startswith("=AUX(")]
        assert len(aux_cells) > 0, "No AUX formulas found in new J cells"

        for cell in aux_cells:
            formula = cell["formula"]
            # Extract content between =AUX( and )
            inner = formula[5:-1]
            parts = inner.split(",")
            assert len(parts) == 4, (
                f"AUX formula not 4-arg in {cell['_sheet']}/{cell['cell_ref']}: "
                f"{formula} has {len(parts)} args"
            )

    def test_aux_format_pattern(self, j_new_cells):
        """=AUX 格式：=AUX('account_code','aux_type','aux_code','column')"""
        pattern = re.compile(r"^=AUX\('[^']+','[^']+','[^']+','[^']+'\)$")
        aux_cells = [c for c in j_new_cells if c["formula"].startswith("=AUX(")]

        for cell in aux_cells:
            assert pattern.match(cell["formula"]), (
                f"AUX formula format invalid in {cell['_sheet']}/{cell['cell_ref']}: "
                f"{cell['formula']}"
            )

    def test_aux_account_codes_valid(self, j_new_cells):
        """AUX 公式的 account_code 应为 2211（应付职工薪酬）"""
        aux_cells = [c for c in j_new_cells if c["formula"].startswith("=AUX(")]
        valid_accounts = {"2211", "4001", "4002"}

        for cell in aux_cells:
            inner = cell["formula"][5:-1]
            account = inner.split(",")[0].strip("'")
            assert account in valid_accounts, (
                f"Unexpected account_code in AUX: {account} "
                f"(expected one of {valid_accounts})"
            )


class TestJPrefillSheetNames:
    """验证真实 sheet 名（含末尾空格）"""

    def test_j1_2_has_trailing_space(self, j_new_entries):
        """明细表J1-2 末尾必须带空格"""
        entry = next((e for e in j_new_entries if "J1-2" in e["sheet"]), None)
        assert entry is not None, "J1-2 entry not found"
        assert entry["sheet"].endswith(" "), (
            f"明细表J1-2 sheet name missing trailing space: {entry['sheet']!r}"
        )

    def test_all_sheet_names_match_expected(self, j_new_entries):
        """所有新增 sheet 名必须在预期列表中"""
        for entry in j_new_entries:
            assert entry["sheet"] in J_NEW_SHEETS, (
                f"Unexpected sheet name: {entry['sheet']!r}"
            )

    def test_no_duplicate_wp_sheet_keys(self, prefill_data):
        """(wp_code, sheet) 组合必须唯一（幂等保护）"""
        keys = [(m["wp_code"], m["sheet"]) for m in prefill_data["mappings"]]
        duplicates = [k for k in keys if keys.count(k) > 1]
        assert not duplicates, (
            f"Duplicate (wp_code, sheet) keys found: {set(duplicates)}"
        )


class TestJPrefillFormulaTypes:
    """验证公式类型分布"""

    def test_formula_types_valid(self, j_new_cells):
        """所有公式类型必须是已知类型"""
        valid_types = {"TB", "TB_SUM", "ADJ", "PREV", "WP", "AUX", "LEDGER"}
        for cell in j_new_cells:
            assert cell["formula_type"] in valid_types, (
                f"Invalid formula_type in {cell['_sheet']}/{cell['cell_ref']}: "
                f"{cell['formula_type']}"
            )

    def test_has_aux_formulas(self, j_new_cells):
        """新增 cells 中应包含 AUX 类型公式"""
        aux_count = sum(1 for c in j_new_cells if c["formula_type"] == "AUX")
        assert aux_count >= 10, (
            f"Expected ≥ 10 AUX formula cells, got {aux_count}"
        )

    def test_has_ledger_formulas(self, j_new_cells):
        """新增 cells 中应包含 LEDGER 类型公式"""
        ledger_count = sum(1 for c in j_new_cells if c["formula_type"] == "LEDGER")
        assert ledger_count >= 5, (
            f"Expected ≥ 5 LEDGER formula cells, got {ledger_count}"
        )

    def test_has_tb_formulas(self, j_new_cells):
        """新增 cells 中应包含 TB 类型公式"""
        tb_count = sum(1 for c in j_new_cells if c["formula_type"] == "TB")
        assert tb_count >= 5, (
            f"Expected ≥ 5 TB formula cells, got {tb_count}"
        )

    def test_has_prev_formulas(self, j_new_cells):
        """新增 cells 中应包含 PREV 类型公式"""
        prev_count = sum(1 for c in j_new_cells if c["formula_type"] == "PREV")
        assert prev_count >= 2, (
            f"Expected ≥ 2 PREV formula cells, got {prev_count}"
        )


class TestJPrefillJ3AccountCorrection:
    """验证 J3 股份支付科目修正为 4001/4002"""

    def test_j3_uses_correct_accounts(self, j_new_entries):
        """J3-2 应使用 4001/4002 而非 2211"""
        entry = next((e for e in j_new_entries if e["sheet"] == "股份支付检查表J3-2"), None)
        assert entry is not None, "股份支付检查表J3-2 entry not found"
        assert "4001" in entry["account_codes"] or "4002" in entry["account_codes"], (
            f"J3-2 should use 4001/4002, got {entry['account_codes']}"
        )
        assert "2211" not in entry["account_codes"], (
            f"J3-2 should NOT use 2211 (old incorrect mapping)"
        )
