"""I-F10 prefill 扩展验证测试（降级目标 ≥ 40 new cells）

验证：
1. I-cycle 新增 cells ≥ 40（降级目标，因 1701/1702/1703/1711/1801/1811/5601/6602
   均无辅助账数据，与 H 循环 1601/1602 同情况）
2. 真实 sheet 名校验（所有 sheet 名匹配 Sprint 0.X openpyxl 实测名）
3. 降级约束：I-cycle 新增 entries 不应有 =AUX 公式（仅 =TB / =LEDGER / =PREV）
4. LEDGER 公式使用正确 3-arg 格式
5. TB 公式引用合法 I 循环科目
6. PREV 公式有合法 sheet 引用
7. 所有 formula_type 值合法
8. 无重复 (wp_code, sheet, cell_ref) 组合
9. I1-10 / I1-11 两版摊销测算均有 entries
10. I4-6 / I4-7 两版摊销测算均有 entries
11. 5 张明细表（I1-2 / I2-2 / I3-2 / I4-2 / I6-2）全部覆盖

Spec: workpaper-i-intangible-assets-cycle / Sprint 2 / Task 2.26
Validates: Requirements I-F10
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PREFILL_FILE = DATA_DIR / "prefill_formula_mapping.json"

# 降级目标：≥ 40 new cells（baseline 34 + new 40 = 74 total min）
I_CYCLE_NEW_CELL_TARGET = 40
I_CYCLE_BASELINE_CELLS = 34

# 合法 formula_type 枚举（沿用 H test 同款）
VALID_FORMULA_TYPES = {
    "TB", "TB_SUM", "ADJ", "PREV", "WP", "AUX", "LEDGER", "LEDGER_DETAIL",
    "COUNT_LEDGER", "NOTE", "TB_AUX", "SUM_TB", "CROSS_SHEET",
}

# Sprint 0.X 实测真实 sheet 名（openpyxl 提取，design.md ADR-I5 已落地）
REAL_I_SHEET_NAMES = {
    # 5 张明细表
    "明细表I1-2",
    "明细表I2-2",
    "明细表I3-2",
    "明细表I4-2",
    "明细表I6-2",
    # 4 张摊销测算（含括号修饰词）
    "摊销测算表（不含减值）I1-10（剩余年限法）",
    "摊销测算表（含减值）I1-11",
    "摊销测算I4-6",
    "摊销测算表I4-7（工作量法）",
}

# I-F10 新增 entries 使用的 sheet 名（task 2.23/2.24 追加的 9 张，不含 baseline 审定表）
I_NEW_ENTRY_SHEETS = REAL_I_SHEET_NAMES

# I 循环涉及的合法 TB 科目编码（Sprint 0.X 实测 + 设计文档明确的科目）
VALID_I_ACCOUNT_CODES = {
    "1701",  # 无形资产原值
    "1702",  # 累计摊销
    "1703",  # 无形资产减值准备
    "1711",  # 商誉
    "1712",  # 商誉减值准备
    "1801",  # 长期待摊费用 / 开发支出（取决于科目表版本）
    "1811",  # 其他非流动资产
    "5601",  # 研发支出（部分企业用此编码）
    "6602",  # 研发费用（损益类，标准编码）
}

# 1701 / 1702 / 1703 / 1711 / 1801 / 1811 / 5601 / 6602 全部无 aux_balance 数据
# 故新增 entries 不应有 =AUX 公式（降级约束）
NO_AUX_ACCOUNTS = {"1701", "1702", "1703", "1711", "1712", "1801", "1811", "5601", "6602"}


@pytest.fixture(scope="module")
def prefill_data():
    assert PREFILL_FILE.exists(), f"prefill_formula_mapping.json not found at {PREFILL_FILE}"
    with open(PREFILL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _i_entries(data) -> list[dict]:
    """所有 I-cycle entries（wp_code 以 I 开头）"""
    return [m for m in data["mappings"] if str(m.get("wp_code", "")).startswith("I")]


def _i_new_entries(data) -> list[dict]:
    """I-cycle 新增 entries（sheet 在 REAL_I_SHEET_NAMES 中，即 task 2.23/2.24 追加的）"""
    return [
        m for m in data["mappings"]
        if str(m.get("wp_code", "")).startswith("I")
        and m.get("sheet", "") in I_NEW_ENTRY_SHEETS
    ]


# ─── Test 1: 新增 I-cycle cells ≥ 40 ─────────────────────────────────────────


class TestICycleCellCount:
    def test_i_cycle_new_cells_at_least_40(self, prefill_data):
        """I-cycle 新增 cells ≥ 40（降级目标）"""
        new_entries = _i_new_entries(prefill_data)
        new_cells = sum(len(m.get("cells", [])) for m in new_entries)
        assert new_cells >= I_CYCLE_NEW_CELL_TARGET, (
            f"I-cycle new cells = {new_cells}, expected >= {I_CYCLE_NEW_CELL_TARGET}"
        )

    def test_i_cycle_total_cells_above_baseline(self, prefill_data):
        """I-cycle 总 cells ≥ baseline(34) + 40 = 74"""
        i_entries = _i_entries(prefill_data)
        total = sum(len(m.get("cells", [])) for m in i_entries)
        expected_min = I_CYCLE_BASELINE_CELLS + I_CYCLE_NEW_CELL_TARGET
        assert total >= expected_min, (
            f"I-cycle total cells = {total}, expected >= {expected_min}"
        )


# ─── Test 2: 真实 sheet 名校验 ────────────────────────────────────────────────


class TestRealSheetNames:
    """所有新增 I-cycle entries 的 sheet 名必须匹配 Sprint 0.X openpyxl 实测名"""

    def test_new_entry_sheets_are_real(self, prefill_data):
        """新增 entries 的 sheet 名全部在 REAL_I_SHEET_NAMES 中"""
        new_entries = _i_new_entries(prefill_data)
        # 确认有新增 entries
        assert len(new_entries) > 0, "No new I-cycle entries found"
        sheets_used = {m["sheet"] for m in new_entries}
        invalid = sheets_used - REAL_I_SHEET_NAMES
        assert not invalid, (
            f"以下 sheet 名不在 openpyxl 实测名单中: {invalid}"
        )


# ─── Test 3: 降级约束 — 新增 entries 无 =AUX ─────────────────────────────────


class TestDegradedNoAux:
    """降级约束：1701/1702/1703/1711/1801/1811/5601/6602 全无辅助账数据
    → I-cycle 新增 entries 不应有 =AUX 公式
    """

    def test_no_aux_in_new_entries(self, prefill_data):
        """新增 I-cycle entries 不应有 formula_type=AUX 的 cell"""
        new_entries = _i_new_entries(prefill_data)
        bad = []
        for m in new_entries:
            for cell in m.get("cells", []):
                if cell.get("formula_type") == "AUX":
                    bad.append((m["sheet"], cell.get("cell_ref"), cell.get("formula")))
        assert not bad, (
            f"降级约束违反：I-cycle 新增 entries 不应有 =AUX 公式，发现: {bad[:5]}"
        )

    def test_no_aux_for_degraded_accounts(self, prefill_data):
        """所有 NO_AUX_ACCOUNTS 中的科目均不应被 =AUX 公式引用（I-cycle 范围内）"""
        i_entries = _i_entries(prefill_data)
        aux_pattern = re.compile(r"=AUX\s*\(\s*'(\d+)'", re.IGNORECASE)
        bad = []
        for m in i_entries:
            for cell in m.get("cells", []):
                if cell.get("formula_type") != "AUX":
                    continue
                formula = cell.get("formula", "")
                mm = aux_pattern.search(formula)
                if mm and mm.group(1) in NO_AUX_ACCOUNTS:
                    bad.append((m["sheet"], cell.get("cell_ref"), mm.group(1)))
        assert not bad, (
            f"降级约束违反：以下科目无 aux 数据但被 =AUX 公式引用: {bad[:5]}"
        )


# ─── Test 4: LEDGER 公式 3-arg 格式 ──────────────────────────────────────────


class TestLedgerFormat:
    """LEDGER 公式格式：=LEDGER(account, direction, period)"""

    def test_ledger_formulas_3_args(self, prefill_data):
        """所有 I-cycle =LEDGER 公式必须 3-arg"""
        i_entries = _i_entries(prefill_data)
        ledger_pattern = re.compile(r"=LEDGER\s*\(([^)]*)\)", re.IGNORECASE)
        bad = []
        for m in i_entries:
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
        assert not bad, f"I-cycle =LEDGER 必须 3-arg: {bad[:5]}"


# ─── Test 5: TB 公式引用合法科目编码 ──────────────────────────────────────────


class TestTBAccountCodes:
    """TB 公式引用的科目编码必须在 I 循环合法范围内（针对新增 entries）"""

    def test_tb_account_codes_valid(self, prefill_data):
        """所有 I-cycle 新增 =TB 公式的科目编码在合法集合内"""
        new_entries = _i_new_entries(prefill_data)
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
                    if code not in VALID_I_ACCOUNT_CODES:
                        bad.append((m["sheet"], cell.get("cell_ref"), code))
        assert not bad, (
            f"TB 公式引用了非 I 循环科目: {bad[:5]}"
        )


# ─── Test 6: PREV 公式有合法 sheet 引用 ──────────────────────────────────────


class TestPrevFormulas:
    """PREV 公式格式：=PREV(wp_code, sheet, field)，sheet 必须是真实名"""

    def test_prev_formulas_have_valid_sheet_ref(self, prefill_data):
        """所有 I-cycle 新增 =PREV 公式的 sheet 引用必须是真实 sheet 名"""
        new_entries = _i_new_entries(prefill_data)
        # =PREV('I1','明细表I1-2','审定数')
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
                    if sheet_ref not in REAL_I_SHEET_NAMES:
                        bad.append((m["sheet"], cell.get("cell_ref"), sheet_ref))
        assert not bad, (
            f"PREV 公式引用了非真实 sheet 名: {bad[:5]}"
        )


# ─── Test 7: 所有 formula_type 值合法 ────────────────────────────────────────


class TestFormulaTypeValid:
    def test_all_formula_types_valid(self, prefill_data):
        """每个 I-cycle cell 的 formula_type 在合法枚举内"""
        i_entries = _i_entries(prefill_data)
        bad = []
        for m in i_entries:
            for cell in m.get("cells", []):
                ft = cell.get("formula_type")
                if ft not in VALID_FORMULA_TYPES:
                    bad.append((m["sheet"], cell.get("cell_ref"), ft))
        assert not bad, f"Invalid formula_type: {bad[:5]}"


# ─── Test 8: 无重复 (wp_code, sheet, cell_ref) 组合 ─────────────────────────


class TestNoDuplicateCells:
    def test_no_duplicate_wp_sheet_cell(self, prefill_data):
        """I-cycle 内无重复 (wp_code, sheet, cell_ref) 组合"""
        i_entries = _i_entries(prefill_data)
        seen: set[tuple[str, str, str]] = set()
        duplicates = []
        for m in i_entries:
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


# ─── Test 9: I1-10 / I1-11 两版摊销测算均有 entries ───────────────────────────


class TestI110AndI111Both:
    """I1-10（不含减值）+ I1-11（含减值）2 版摊销测算均有 prefill entries"""

    AMORT_SHEETS = {
        "摊销测算表（不含减值）I1-10（剩余年限法）",
        "摊销测算表（含减值）I1-11",
    }

    def test_both_versions_have_entries(self, prefill_data):
        """I1 两版摊销测算均有 entries"""
        i_entries = _i_entries(prefill_data)
        sheets_with_entries = {m["sheet"] for m in i_entries}
        missing = self.AMORT_SHEETS - sheets_with_entries
        assert not missing, (
            f"I1 摊销测算缺少版本: {missing}"
        )

    def test_each_version_has_cells(self, prefill_data):
        """I1 两版摊销测算每版至少 3 cells"""
        i_entries = _i_entries(prefill_data)
        for sheet_name in self.AMORT_SHEETS:
            entries = [m for m in i_entries if m.get("sheet") == sheet_name]
            total_cells = sum(len(m.get("cells", [])) for m in entries)
            assert total_cells >= 3, (
                f"{sheet_name} 仅有 {total_cells} cells，期望 >= 3"
            )


# ─── Test 10: I4-6 / I4-7 两版摊销测算均有 entries ────────────────────────────


class TestI46AndI47Both:
    """I4-6（直线法）+ I4-7（工作量法）2 版摊销测算均有 prefill entries"""

    AMORT_SHEETS = {
        "摊销测算I4-6",
        "摊销测算表I4-7（工作量法）",
    }

    def test_both_versions_have_entries(self, prefill_data):
        """I4 两版摊销测算均有 entries"""
        i_entries = _i_entries(prefill_data)
        sheets_with_entries = {m["sheet"] for m in i_entries}
        missing = self.AMORT_SHEETS - sheets_with_entries
        assert not missing, (
            f"I4 摊销测算缺少版本: {missing}"
        )


# ─── Test 11: 5 张明细表全部覆盖 ──────────────────────────────────────────────


class TestAllDetailSheetsCovered:
    """I 循环 5 张主明细表（I1-2/I2-2/I3-2/I4-2/I6-2）全部有 entries"""

    DETAIL_SHEETS = {
        "明细表I1-2",
        "明细表I2-2",
        "明细表I3-2",
        "明细表I4-2",
        "明细表I6-2",
    }

    def test_all_detail_sheets_have_entries(self, prefill_data):
        """5 张主明细表全部有 prefill entries"""
        i_entries = _i_entries(prefill_data)
        sheets_with_entries = {m["sheet"] for m in i_entries}
        missing = self.DETAIL_SHEETS - sheets_with_entries
        assert not missing, (
            f"以下主明细表缺少 prefill entries: {missing}"
        )

    def test_i1_2_has_at_least_8_cells(self, prefill_data):
        """明细表I1-2 至少 8 cells（=TB 1701/1702/1703 期初/期末/借/贷）"""
        i_entries = _i_entries(prefill_data)
        i1_2 = [m for m in i_entries if m.get("sheet") == "明细表I1-2"]
        total = sum(len(m.get("cells", [])) for m in i1_2)
        assert total >= 8, f"明细表I1-2 仅 {total} cells，期望 >= 8"

    def test_i6_2_has_ledger_entries(self, prefill_data):
        """明细表I6-2 至少有 1 个 =LEDGER 公式（研发费用月度抽样）"""
        i_entries = _i_entries(prefill_data)
        i6_2 = [m for m in i_entries if m.get("sheet") == "明细表I6-2"]
        has_ledger = any(
            cell.get("formula_type") == "LEDGER"
            for m in i6_2
            for cell in m.get("cells", [])
        )
        assert has_ledger, "明细表I6-2 应包含 =LEDGER 公式（研发费用月度抽样）"
