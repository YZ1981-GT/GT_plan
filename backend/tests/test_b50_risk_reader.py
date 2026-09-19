"""B50 风险读取器纯函数测试 — 锁定 item_id 解析与循环匹配契约。

覆盖 b50_risk_reader 的核心纯逻辑（解析 checklist_responses item_id、
按循环首字母匹配），保证 B50 → D~N 认定层次风险联动不回归。
"""
from app.services.b50_risk_reader import _parse_matrix_item_id, cycle_matches


class TestParseMatrixItemId:
    def test_parses_rmm_cell(self):
        assert _parse_matrix_item_id("B50-T3-matrix-收入确认-existence-RMM") == (
            "收入确认", "existence", "RMM",
        )

    def test_parses_special_risk_cell(self):
        assert _parse_matrix_item_id("B50-T3-matrix-管理层凌驾控制-cutoff-SR") == (
            "管理层凌驾控制", "cutoff", "SR",
        )

    def test_account_with_hyphen_preserved(self):
        # 科目名含连字符时仍能正确切出末段 assertion + suffix
        assert _parse_matrix_item_id("B50-T3-matrix-应收-账款-completeness-IR") == (
            "应收-账款", "completeness", "IR",
        )

    def test_rejects_non_matrix_id(self):
        assert _parse_matrix_item_id("B50-T3-cycle-收入确认") is None
        assert _parse_matrix_item_id("B50-T1-factor-0-desc") is None

    def test_rejects_unknown_suffix(self):
        assert _parse_matrix_item_id("B50-T3-matrix-收入确认-existence-XYZ") is None

    def test_rejects_unknown_assertion(self):
        assert _parse_matrix_item_id("B50-T3-matrix-收入确认-foobar-RMM") is None


class TestCycleMatches:
    def test_exact_letter_match(self):
        assert cycle_matches("D", "D") is True
        assert cycle_matches("D", "E") is False

    def test_table_code_first_letter(self):
        # 目标传完整 table_code（如 'D2A'）→ 按首字母匹配
        assert cycle_matches("D", "D2A") is True
        assert cycle_matches("E", "D2A") is False

    def test_case_insensitive(self):
        assert cycle_matches("d", "D") is True

    def test_empty_target_matches_all(self):
        assert cycle_matches("D", "") is True
        assert cycle_matches(None, None) is True

    def test_empty_risk_cycle_no_match_when_target_set(self):
        assert cycle_matches(None, "D") is False
        assert cycle_matches("", "D") is False
