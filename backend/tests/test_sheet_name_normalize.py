"""后端 _sheet_name_matches 半/全角标点归一化匹配测试。"""
import pytest

from app.routers.wp_render_config import _sheet_name_matches


class TestSheetNameNormalize:
    """第四级半/全角标点归一化回退层。"""

    def test_full_width_parentheses_match(self):
        """全角括号匹配半角括号。"""
        assert _sheet_name_matches(
            '附注披露信息（上市公司）', '附注披露信息(上市公司)'
        )

    def test_d6_mixed_parentheses(self):
        """D6混合：半角左括号+全角右括号。"""
        assert _sheet_name_matches(
            '附注披露信息(上市公司）', '附注披露信息(上市公司)'
        )

    def test_no_false_positive_different_content(self):
        """不误伤不同字。"""
        assert not _sheet_name_matches(
            '附注披露信息(上市公司)', '附注披露信息(国企)'
        )

    def test_no_bracket_no_issue(self):
        """无括号场景不受影响。"""
        assert _sheet_name_matches('审定表K3-1', '审定表K3-1')

    def test_different_sheets_no_false_match(self):
        """不同底稿不误匹配。"""
        assert not _sheet_name_matches('审定表K3-1', '明细表K3-2')

    def test_full_width_comma_colon_semicolon(self):
        """全角逗号/冒号/分号折叠。"""
        assert _sheet_name_matches(
            '测试，数据：项目；结果', '测试,数据:项目;结果'
        )

    def test_whitespace_normalize(self):
        """多空白/全角空格归一。"""
        assert _sheet_name_matches(
            '审定表\u3000K3-1  审计', '审定表 K3-1 审计'
        )

    def test_exact_still_works(self):
        """精确匹配仍优先。"""
        assert _sheet_name_matches('审定表K3-1', '审定表K3-1')

    def test_none_input(self):
        """None 输入不崩溃。"""
        assert not _sheet_name_matches(None, '审定表K3-1')
        assert not _sheet_name_matches('审定表K3-1', None)
