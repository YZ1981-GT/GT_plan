"""Sprint 3 Task 3.5: D 循环 prefill 扩展 30 cell 验证测试

验证:
- 30 新 cell 存在于 prefill_formula_mapping.json
- 每个 cell 有合法 formula_type (AUX/LEDGER/LEDGER_DETAIL/PREV/TB)
- 总 cell 数从基线增加了 30
"""
import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PREFILL_FILE = DATA_DIR / "prefill_formula_mapping.json"

# Sprint 0 实测基线: 536 cells (122 mappings)
# D 循环新增 30 cells，后续 spec (F/H/I/G/J/K/L/M) 持续追加
# 使用 >= 阈值验证 D 循环贡献存在，而非硬编码总数
D_CYCLE_MINIMUM_CELLS = 566  # D 循环完成后最低 cells 数
EXPECTED_NEW_CELLS = 30

# 5 个新增 sheet 的标识
NEW_SHEET_NAMES = [
    "应收账款明细表D2-2",
    "坏账准备明细表D2-3",
    "主营业务收入明细表D4-2",
    "营业收入账面金额与ERP系统核对记录D4-13",
    "营业收入截止测试（账到单据）D4-17",
]

VALID_FORMULA_TYPES = {"TB", "TB_SUM", "ADJ", "PREV", "WP", "AUX", "LEDGER", "LEDGER_DETAIL"}


@pytest.fixture
def prefill_data():
    """加载 prefill_formula_mapping.json"""
    assert PREFILL_FILE.exists(), f"prefill_formula_mapping.json not found at {PREFILL_FILE}"
    with open(PREFILL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_prefill_file_exists():
    """prefill_formula_mapping.json 文件存在"""
    assert PREFILL_FILE.exists()


def test_total_cell_count_increased(prefill_data):
    """总 cell 数 >= D 循环完成后最低阈值（后续 spec 只增不减）"""
    mappings = prefill_data["mappings"]
    total_cells = sum(len(m.get("cells", [])) for m in mappings)
    assert total_cells >= D_CYCLE_MINIMUM_CELLS, (
        f"Expected >= {D_CYCLE_MINIMUM_CELLS} cells, got {total_cells}"
    )


def test_new_sheets_exist(prefill_data):
    """5 个新增 sheet 都存在于 mappings 中"""
    mappings = prefill_data["mappings"]
    all_sheets = [m["sheet"] for m in mappings]
    for sheet_name in NEW_SHEET_NAMES:
        assert sheet_name in all_sheets, f"Sheet '{sheet_name}' not found in mappings"


def test_d2_2_has_10_aux_cells(prefill_data):
    """D2-2 明细表有 10 个 AUX 类型 cell"""
    mappings = prefill_data["mappings"]
    d2_2 = [m for m in mappings if m["sheet"] == "应收账款明细表D2-2"]
    assert len(d2_2) == 1, f"Expected 1 D2-2 mapping, got {len(d2_2)}"
    cells = d2_2[0]["cells"]
    assert len(cells) == 10, f"Expected 10 cells for D2-2, got {len(cells)}"
    for cell in cells:
        assert cell["formula_type"] == "AUX", (
            f"D2-2 cell '{cell['cell_ref']}' has type '{cell['formula_type']}', expected AUX"
        )


def test_d2_3_has_5_cells(prefill_data):
    """D2-3 坏账明细有 5 个 cell（LEDGER + PREV + TB）"""
    mappings = prefill_data["mappings"]
    d2_3 = [m for m in mappings if m["sheet"] == "坏账准备明细表D2-3"]
    assert len(d2_3) == 1, f"Expected 1 D2-3 mapping, got {len(d2_3)}"
    cells = d2_3[0]["cells"]
    assert len(cells) == 5, f"Expected 5 cells for D2-3, got {len(cells)}"
    types = {c["formula_type"] for c in cells}
    assert types.issubset({"LEDGER", "PREV", "TB"}), f"Unexpected formula types in D2-3: {types}"


def test_d4_2_has_8_cells(prefill_data):
    """D4-2 主营业务收入明细有 8 个 cell（LEDGER + PREV）"""
    mappings = prefill_data["mappings"]
    d4_2 = [m for m in mappings if m["sheet"] == "主营业务收入明细表D4-2"]
    assert len(d4_2) == 1, f"Expected 1 D4-2 mapping, got {len(d4_2)}"
    cells = d4_2[0]["cells"]
    assert len(cells) == 8, f"Expected 8 cells for D4-2, got {len(cells)}"
    types = {c["formula_type"] for c in cells}
    assert types.issubset({"LEDGER", "PREV"}), f"Unexpected formula types in D4-2: {types}"


def test_d4_13_has_3_ledger_cells(prefill_data):
    """D4-13 ERP 核对有 3 个 LEDGER 类型 cell"""
    mappings = prefill_data["mappings"]
    d4_13 = [m for m in mappings if m["sheet"] == "营业收入账面金额与ERP系统核对记录D4-13"]
    assert len(d4_13) == 1, f"Expected 1 D4-13 mapping, got {len(d4_13)}"
    cells = d4_13[0]["cells"]
    assert len(cells) == 3, f"Expected 3 cells for D4-13, got {len(cells)}"
    for cell in cells:
        assert cell["formula_type"] == "LEDGER", (
            f"D4-13 cell '{cell['cell_ref']}' has type '{cell['formula_type']}', expected LEDGER"
        )


def test_d4_17_has_4_ledger_detail_cells(prefill_data):
    """D4-17/18 截止测试有 4 个 LEDGER_DETAIL 类型 cell"""
    mappings = prefill_data["mappings"]
    d4_17 = [m for m in mappings if m["sheet"] == "营业收入截止测试（账到单据）D4-17"]
    assert len(d4_17) == 1, f"Expected 1 D4-17 mapping, got {len(d4_17)}"
    cells = d4_17[0]["cells"]
    assert len(cells) == 4, f"Expected 4 cells for D4-17, got {len(cells)}"
    for cell in cells:
        assert cell["formula_type"] == "LEDGER_DETAIL", (
            f"D4-17 cell '{cell['cell_ref']}' has type '{cell['formula_type']}', expected LEDGER_DETAIL"
        )


def test_all_new_cells_have_valid_formula_type(prefill_data):
    """所有新增 cell 的 formula_type 都是合法值"""
    mappings = prefill_data["mappings"]
    for m in mappings:
        if m["sheet"] in NEW_SHEET_NAMES:
            for cell in m.get("cells", []):
                assert cell["formula_type"] in VALID_FORMULA_TYPES, (
                    f"Invalid formula_type '{cell['formula_type']}' in sheet '{m['sheet']}' "
                    f"cell '{cell['cell_ref']}'"
                )


def test_all_new_cells_have_required_fields(prefill_data):
    """所有新增 cell 都有 cell_ref, formula, formula_type, description 字段"""
    mappings = prefill_data["mappings"]
    required_fields = {"cell_ref", "formula", "formula_type", "description"}
    for m in mappings:
        if m["sheet"] in NEW_SHEET_NAMES:
            for cell in m.get("cells", []):
                missing = required_fields - set(cell.keys())
                assert not missing, (
                    f"Cell '{cell.get('cell_ref', '?')}' in sheet '{m['sheet']}' "
                    f"missing fields: {missing}"
                )


def test_new_mappings_have_account_codes(prefill_data):
    """所有新增 mapping 都有 account_codes 字段"""
    mappings = prefill_data["mappings"]
    for m in mappings:
        if m["sheet"] in NEW_SHEET_NAMES:
            assert "account_codes" in m, f"Sheet '{m['sheet']}' missing account_codes"
            assert len(m["account_codes"]) > 0, f"Sheet '{m['sheet']}' has empty account_codes"
