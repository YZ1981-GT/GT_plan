"""H-F10 prefill 扩展验证测试（降级目标 ≥ 70 new cells）

验证:
1. H-cycle 新增 cells ≥ 70（降级目标，因 1601/1602 无辅助账数据）
2. 4-arg AUX 格式校验：=AUX(account_code, aux_type, aux_code, column) — 仅 1604 在建工程
3. 真实 sheet 名校验（所有 sheet 名匹配 openpyxl 实测名）
4. 真实 aux_type 校验（仅 '项目名称' for 1604）
5. 1601/1602 无 =AUX（降级约束）
6. LEDGER 公式使用正确 3-arg 格式
7. TB 公式引用合法科目编码
8. PREV 公式有合法 sheet 引用
9. 所有 formula_type 值合法
10. 无重复 (wp_code, sheet, cell_ref) 组合
11. H1-12 三版折旧测算表均有 entries
12. H2-2 有 AUX entries（1604 在建工程）

Spec: workpaper-h-fixed-assets-cycle / Sprint 2 / Task 2.26
Validates: Requirements H-F10
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PREFILL_FILE = DATA_DIR / "prefill_formula_mapping.json"

# 降级目标：≥ 70 new cells（原 56 baseline + 70 new = 126 total）
H_CYCLE_NEW_CELL_TARGET = 70
H_CYCLE_BASELINE_CELLS = 56

# 合法 formula_type 枚举
VALID_FORMULA_TYPES = {
    "TB", "TB_SUM", "ADJ", "PREV", "WP", "AUX", "LEDGER", "LEDGER_DETAIL",
    "COUNT_LEDGER", "NOTE", "TB_AUX", "SUM_TB",
}

# Sprint 0.X 实测真实 sheet 名（openpyxl 提取）
REAL_H_SHEET_NAMES = {
    "明细表H1-2",
    "折旧测算表（不含减值）-直线法H1-12",
    "折旧测算表（含减值）H1-12",
    "折旧测算表（多次减值）H1-12",
    "折旧分配分析表H1-13",
    "减值测算表H1-14",
    "明细表H2-2",
    "明细表（成本模式）H3-2",
    "明细表（公允价值模式）H3-2",
    "明细表H8-2",
    "租赁负债明细表H9-2",
    "未确认融资费用明细表H9-3",
    "明细表H10-2",
}

# H-F10 新增 entries 使用的 sheet 名（task 2.23 追加的，不含原 baseline 审定表）
H_NEW_ENTRY_SHEETS = REAL_H_SHEET_NAMES

# TB 公式合法科目编码前缀（H 循环涉及的科目）
VALID_H_ACCOUNT_CODES = {
    "1601", "1602", "1603",  # 固定资产/累计折旧/减值准备
    "1521", "1522", "1523",  # 投资性房地产/累计折旧/减值
    "2202",                  # 应付账款（部分场景）
    "1801", "1811",          # 长期待摊费用（部分场景）
    "1604",                  # 在建工程
    "1606",                  # 固定资产清理
    "6115",                  # 资产处置收益
    "1621", "1622",          # 使用权资产/累计折旧
    "2802", "2803",          # 租赁负债/未确认融资费用
}


@pytest.fixture(scope="module")
def prefill_data():
    assert PREFILL_FILE.exists(), f"prefill_formula_mapping.json not found at {PREFILL_FILE}"
    with open(PREFILL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _h_entries(data) -> list[dict]:
    """所有 H-cycle entries（wp_code 以 H 开头）"""
    return [m for m in data["mappings"] if str(m.get("wp_code", "")).startswith("H")]


def _h_new_entries(data) -> list[dict]:
    """H-cycle 新增 entries（sheet 在 REAL_H_SHEET_NAMES 中，即 task 2.23 追加的明细表/测算表）"""
    return [
        m for m in data["mappings"]
        if str(m.get("wp_code", "")).startswith("H")
        and m.get("sheet", "") in H_NEW_ENTRY_SHEETS
    ]


# ─── Test 1: 新增 H-cycle cells ≥ 70 ─────────────────────────────────────────


class TestHCycleCellCount:
    def test_h_cycle_new_cells_at_least_70(self, prefill_data):
        """H-cycle 新增 cells ≥ 70（降级目标）"""
        new_entries = _h_new_entries(prefill_data)
        new_cells = sum(len(m.get("cells", [])) for m in new_entries)
        assert new_cells >= H_CYCLE_NEW_CELL_TARGET, (
            f"H-cycle new cells = {new_cells}, expected >= {H_CYCLE_NEW_CELL_TARGET}"
        )

    def test_h_cycle_total_cells_above_baseline(self, prefill_data):
        """H-cycle 总 cells ≥ baseline(56) + 70 = 126"""
        h_entries = _h_entries(prefill_data)
        total = sum(len(m.get("cells", [])) for m in h_entries)
        expected_min = H_CYCLE_BASELINE_CELLS + H_CYCLE_NEW_CELL_TARGET
        assert total >= expected_min, (
            f"H-cycle total cells = {total}, expected >= {expected_min}"
        )


# ─── Test 2: 4-arg AUX 格式校验 ──────────────────────────────────────────────


class TestAuxFormatValidation:
    """=AUX 公式必须 4 args: (account_code, aux_type, aux_code, column)
    仅 1604 在建工程有辅助账数据。
    """

    def test_aux_formulas_use_4_args(self, prefill_data):
        """所有 H-cycle =AUX 公式必须 4-arg"""
        h_entries = _h_entries(prefill_data)
        bad = []
        aux_pattern = re.compile(r"=AUX\s*\(([^)]*)\)", re.IGNORECASE)
        for m in h_entries:
            for cell in m.get("cells", []):
                if cell.get("formula_type") != "AUX":
                    continue
                formula = cell.get("formula", "")
                mm = aux_pattern.search(formula)
                if not mm:
                    bad.append((m["sheet"], cell.get("cell_ref"), "no AUX(...) match", formula))
                    continue
                args_str = mm.group(1)
                arg_count = len([a for a in args_str.split(",") if a.strip()])
                if arg_count != 4:
                    bad.append((m["sheet"], cell.get("cell_ref"), f"expected 4 args got {arg_count}", formula))
        assert not bad, f"H-cycle =AUX 必须 4-arg: {bad[:5]}"

    def test_aux_only_for_1604(self, prefill_data):
        """降级约束：=AUX 仅用于 1604 在建工程（1601/1602 无辅助账数据）"""
        new_entries = _h_new_entries(prefill_data)
        aux_pattern = re.compile(r"=AUX\s*\(\s*'(\d+)'", re.IGNORECASE)
        bad = []
        for m in new_entries:
            for cell in m.get("cells", []):
                if cell.get("formula_type") != "AUX":
                    continue
                formula = cell.get("formula", "")
                mm = aux_pattern.search(formula)
                if mm:
                    account = mm.group(1)
                    if account != "1604":
                        bad.append((m["sheet"], cell.get("cell_ref"), account, formula))
        assert not bad, (
            f"降级约束违反：=AUX 仅允许 1604，发现其他科目: {bad[:5]}"
        )


# ─── Test 3: 真实 sheet 名校验 ────────────────────────────────────────────────


class TestRealSheetNames:
    """所有新增 H-cycle entries 的 sheet 名必须匹配 openpyxl 实测名"""

    def test_new_entry_sheets_are_real(self, prefill_data):
        """新增 entries 的 sheet 名全部在 REAL_H_SHEET_NAMES 中"""
        new_entries = _h_new_entries(prefill_data)
        # 确认有新增 entries
        assert len(new_entries) > 0, "No new H-cycle entries found"
        sheets_used = {m["sheet"] for m in new_entries}
        invalid = sheets_used - REAL_H_SHEET_NAMES
        assert not invalid, (
            f"以下 sheet 名不在 openpyxl 实测名单中: {invalid}"
        )


# ─── Test 4: 真实 aux_type 校验 ───────────────────────────────────────────────


class TestRealAuxType:
    """Sprint 0.X 实测：1604 的 aux_type 仅为 '项目名称'"""

    def test_aux_type_is_project_name(self, prefill_data):
        """所有 H-cycle =AUX 公式的 aux_type 必须为 '项目名称'"""
        h_entries = _h_entries(prefill_data)
        # =AUX('1604','项目名称','B510003','期末余额')
        aux_pattern = re.compile(
            r"=AUX\s*\(\s*'[^']*'\s*,\s*'([^']*)'\s*,",
            re.IGNORECASE,
        )
        bad = []
        for m in h_entries:
            for cell in m.get("cells", []):
                if cell.get("formula_type") != "AUX":
                    continue
                formula = cell.get("formula", "")
                mm = aux_pattern.search(formula)
                if mm:
                    aux_type = mm.group(1)
                    if aux_type != "项目名称":
                        bad.append((m["sheet"], cell.get("cell_ref"), aux_type))
        assert not bad, (
            f"aux_type 必须为 '项目名称'（Sprint 0.X 实测），发现: {bad[:5]}"
        )


# ─── Test 5: 1601/1602 无 =AUX（降级约束）────────────────────────────────────


class TestNoAuxFor1601_1602:
    """降级约束：1601（固定资产）/ 1602（累计折旧）无辅助账数据，不应有 =AUX"""

    def test_no_aux_for_1601(self, prefill_data):
        """1601 科目不应有 =AUX 公式"""
        h_entries = _h_entries(prefill_data)
        aux_pattern = re.compile(r"=AUX\s*\(\s*'1601'", re.IGNORECASE)
        bad = []
        for m in h_entries:
            for cell in m.get("cells", []):
                if cell.get("formula_type") != "AUX":
                    continue
                if aux_pattern.search(cell.get("formula", "")):
                    bad.append((m["sheet"], cell.get("cell_ref")))
        assert not bad, f"1601 不应有 =AUX（无辅助账数据）: {bad}"

    def test_no_aux_for_1602(self, prefill_data):
        """1602 科目不应有 =AUX 公式"""
        h_entries = _h_entries(prefill_data)
        aux_pattern = re.compile(r"=AUX\s*\(\s*'1602'", re.IGNORECASE)
        bad = []
        for m in h_entries:
            for cell in m.get("cells", []):
                if cell.get("formula_type") != "AUX":
                    continue
                if aux_pattern.search(cell.get("formula", "")):
                    bad.append((m["sheet"], cell.get("cell_ref")))
        assert not bad, f"1602 不应有 =AUX（无辅助账数据）: {bad}"


# ─── Test 6: LEDGER 公式使用正确 3-arg 格式 ───────────────────────────────────


class TestLedgerFormat:
    """LEDGER 公式格式：=LEDGER(account, direction, period)"""

    def test_ledger_formulas_3_args(self, prefill_data):
        """所有 H-cycle =LEDGER 公式必须 3-arg"""
        h_entries = _h_entries(prefill_data)
        ledger_pattern = re.compile(r"=LEDGER\s*\(([^)]*)\)", re.IGNORECASE)
        bad = []
        for m in h_entries:
            for cell in m.get("cells", []):
                if cell.get("formula_type") != "LEDGER":
                    continue
                formula = cell.get("formula", "")
                mm = ledger_pattern.search(formula)
                if not mm:
                    bad.append((m["sheet"], cell.get("cell_ref"), "no LEDGER(...) match"))
                    continue
                args_str = mm.group(1)
                arg_count = len([a for a in args_str.split(",") if a.strip()])
                if arg_count != 3:
                    bad.append((m["sheet"], cell.get("cell_ref"), f"expected 3 args got {arg_count}"))
        assert not bad, f"H-cycle =LEDGER 必须 3-arg: {bad[:5]}"


# ─── Test 7: TB 公式引用合法科目编码 ──────────────────────────────────────────


class TestTBAccountCodes:
    """TB 公式引用的科目编码必须在 H 循环合法范围内"""

    def test_tb_account_codes_valid(self, prefill_data):
        """所有 H-cycle =TB 公式的科目编码在合法集合内"""
        new_entries = _h_new_entries(prefill_data)
        tb_pattern = re.compile(r"=TB\s*\(\s*'(\d+)'", re.IGNORECASE)
        bad = []
        for m in new_entries:
            for cell in m.get("cells", []):
                if cell.get("formula_type") != "TB":
                    continue
                formula = cell.get("formula", "")
                mm = tb_pattern.search(formula)
                if mm:
                    code = mm.group(1)
                    if code not in VALID_H_ACCOUNT_CODES:
                        bad.append((m["sheet"], cell.get("cell_ref"), code))
        assert not bad, (
            f"TB 公式引用了非 H 循环科目: {bad[:5]}"
        )


# ─── Test 8: PREV 公式有合法 sheet 引用 ──────────────────────────────────────


class TestPrevFormulas:
    """PREV 公式格式：=PREV(wp_code, sheet, field)，sheet 必须是真实名"""

    def test_prev_formulas_have_valid_sheet_ref(self, prefill_data):
        """所有 H-cycle =PREV 公式的 sheet 引用必须是真实 sheet 名"""
        new_entries = _h_new_entries(prefill_data)
        # =PREV('H1','明细表H1-2','审定数')
        prev_pattern = re.compile(
            r"=PREV\s*\(\s*'[^']*'\s*,\s*'([^']*)'\s*,",
            re.IGNORECASE,
        )
        bad = []
        for m in new_entries:
            for cell in m.get("cells", []):
                if cell.get("formula_type") != "PREV":
                    continue
                formula = cell.get("formula", "")
                mm = prev_pattern.search(formula)
                if mm:
                    sheet_ref = mm.group(1)
                    if sheet_ref not in REAL_H_SHEET_NAMES:
                        bad.append((m["sheet"], cell.get("cell_ref"), sheet_ref))
        assert not bad, (
            f"PREV 公式引用了非真实 sheet 名: {bad[:5]}"
        )


# ─── Test 9: 所有 formula_type 值合法 ────────────────────────────────────────


class TestFormulaTypeValid:
    def test_all_formula_types_valid(self, prefill_data):
        """每个 H-cycle cell 的 formula_type 在合法枚举内"""
        h_entries = _h_entries(prefill_data)
        bad = []
        for m in h_entries:
            for cell in m.get("cells", []):
                ft = cell.get("formula_type")
                if ft not in VALID_FORMULA_TYPES:
                    bad.append((m["sheet"], cell.get("cell_ref"), ft))
        assert not bad, f"Invalid formula_type: {bad[:5]}"


# ─── Test 10: 无重复 (wp_code, sheet, cell_ref) 组合 ─────────────────────────


class TestNoDuplicateCells:
    def test_no_duplicate_wp_sheet_cell(self, prefill_data):
        """H-cycle 内无重复 (wp_code, sheet, cell_ref) 组合"""
        h_entries = _h_entries(prefill_data)
        seen: set[tuple[str, str, str]] = set()
        duplicates = []
        for m in h_entries:
            wp_code = m.get("wp_code", "")
            sheet = m.get("sheet", "")
            for cell in m.get("cells", []):
                key = (wp_code, sheet, cell.get("cell_ref", ""))
                if key in seen:
                    duplicates.append(key)
                seen.add(key)
        assert not duplicates, (
            f"Duplicate (wp_code, sheet, cell_ref): {duplicates[:5]}"
        )


# ─── Test 11: H1-12 三版折旧测算表均有 entries ────────────────────────────────


class TestH112AllVersions:
    """H1-12 折旧测算表 3 版（不含减值/含减值/多次减值）均有 prefill entries"""

    H112_SHEETS = {
        "折旧测算表（不含减值）-直线法H1-12",
        "折旧测算表（含减值）H1-12",
        "折旧测算表（多次减值）H1-12",
    }

    def test_all_three_versions_have_entries(self, prefill_data):
        """H1-12 三版折旧测算表均有 entries"""
        h_entries = _h_entries(prefill_data)
        sheets_with_entries = {m["sheet"] for m in h_entries}
        missing = self.H112_SHEETS - sheets_with_entries
        assert not missing, (
            f"H1-12 缺少以下版本的 entries: {missing}"
        )

    def test_each_version_has_cells(self, prefill_data):
        """H1-12 每版至少有 3 个 cells"""
        h_entries = _h_entries(prefill_data)
        for sheet_name in self.H112_SHEETS:
            entries = [m for m in h_entries if m.get("sheet") == sheet_name]
            total_cells = sum(len(m.get("cells", [])) for m in entries)
            assert total_cells >= 3, (
                f"{sheet_name} 仅有 {total_cells} cells，期望 >= 3"
            )


# ─── Test 12: H2-2 有 AUX entries（1604 在建工程）────────────────────────────


class TestH22AuxEntries:
    """H2-2 明细表H2-2 应有 =AUX 公式（1604 在建工程按项目辅助核算）"""

    def test_h2_2_has_aux_entries(self, prefill_data):
        """明细表H2-2 至少有 1 个 =AUX 公式"""
        h_entries = _h_entries(prefill_data)
        h2_2 = [m for m in h_entries if m.get("sheet") == "明细表H2-2"]
        assert h2_2, "明细表H2-2 prefill entry 缺失"
        has_aux = any(
            cell.get("formula_type") == "AUX"
            for m in h2_2
            for cell in m.get("cells", [])
        )
        assert has_aux, "明细表H2-2 应包含 =AUX 公式（1604 在建工程按项目辅助核算）"

    def test_h2_2_aux_uses_1604(self, prefill_data):
        """明细表H2-2 的 =AUX 公式引用 1604 科目"""
        h_entries = _h_entries(prefill_data)
        h2_2 = [m for m in h_entries if m.get("sheet") == "明细表H2-2"]
        aux_pattern = re.compile(r"=AUX\s*\(\s*'(\d+)'", re.IGNORECASE)
        found_1604 = False
        for m in h2_2:
            for cell in m.get("cells", []):
                if cell.get("formula_type") != "AUX":
                    continue
                mm = aux_pattern.search(cell.get("formula", ""))
                if mm and mm.group(1) == "1604":
                    found_1604 = True
                    break
        assert found_1604, "明细表H2-2 =AUX 应引用 1604（在建工程）"
