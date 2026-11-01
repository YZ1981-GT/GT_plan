"""`fix_pushed_note_header_labels.reordered_columns` 的安全门判据。

spec: note-table-structure-formula-pull-closure R16

这道门拦的是「列序错位」：推送列名在模板里存在但位置不同 ⇒ 只改 label 会把一列的数据
贴上另一列的名字（实测反例是陕西华氏 八、57）。它不能拦过头 —— 纯措辞差异必须放过去，
否则存量修正就白做了。两个方向都要测。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fix" / "fix_pushed_note_header_labels.py"
_spec = importlib.util.spec_from_file_location("_fix_pushed_note_header_labels", _PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

reordered_columns = _mod.reordered_columns


class TestMustBlock:
    """这些必须拦住（改了就数据错位）。"""

    def test_真库反例_八57_其他非流动负债(self):
        """推送 [项目, 期末余额, 期初余额] vs 模板 [项目, 年初余额, 期末余额]：
        「期末余额」两边都有、位置不同 ⇒ 逐位改名会把期末数标成「年初余额」。"""
        assert reordered_columns(
            ["项目", "期末余额", "期初余额"],
            ["项目", "年初余额", "期末余额"],
        ) is True

    def test_整体两列对调(self):
        assert reordered_columns(["项目", "A", "B"], ["项目", "B", "A"]) is True

    def test_三列循环移位(self):
        assert reordered_columns(["项目", "A", "B", "C"], ["项目", "C", "A", "B"]) is True

    def test_只有一列挪位置(self):
        assert reordered_columns(["项目", "期末余额", "新列"], ["项目", "新列", "期末余额"]) is True


class TestMustPass:
    """这些必须放过去（纯措辞差异，正是要修的那类）。"""

    @pytest.mark.parametrize(("pushed", "template"), [
        # 和平药房 八、5：空白差异
        (["账龄", "期末数", "期初数"], ["账 龄", "期末数", "期初数"]),
        (["类别", "金额", "比例(%)"], ["类 别", "金额", "比例(%)"]),
        # 八、31：同义改名，模板里没有「年初余额」
        (["项目", "本期发生额", "年初余额"], ["项目", "本期发生额", "期初余额"]),
        # 八、14：口径措辞，模板里没有「期末余额」「期初余额」
        (["项目", "期末余额", "期初余额"], ["项目", "期末账面价值", "年初账面价值"]),
        # 八、49：补全期间，模板里没有「余额」
        (["项目", "余额", "利率", "余额"], ["借款类别", "期末余额", "利率", "期初余额"]),
        # 八、45：标签列措辞
        (["项目", "期末余额"], ["借款类别", "期末余额"]),
        # 比例列全称
        (["债务人名称", "账面余额", "比例(%)"], ["债务人名称", "账面余额", "占应收账款合计的比例（%）"]),
    ])
    def test_纯措辞差异不拦(self, pushed: list[str], template: list[str]):
        assert reordered_columns(pushed, template) is False

    def test_完全一致不拦(self):
        same = ["账 龄", "期末数", "期初数"]
        assert reordered_columns(same, list(same)) is False

    def test_同名重复列不误判(self):
        """多级表头下同名叶子列常见（两期各一个「金额」）：位置都对就不该拦。"""
        cols = ["类 别", "金额", "比例(%)", "金额", "预期信用损失率(%)"]
        assert reordered_columns(cols, list(cols)) is False

    def test_同名重复列只改其他列(self):
        assert reordered_columns(
            ["类别", "金额", "比例(%)", "金额", "损失率"],
            ["类 别", "金额", "比例(%)", "金额", "预期信用损失率(%)"],
        ) is False


class TestEdges:
    def test_空列表(self):
        assert reordered_columns([], []) is False

    def test_推送比模板短不越界(self):
        assert reordered_columns(["项目"], ["项目", "期末余额"]) is False

    def test_推送比模板长不越界(self):
        # 列数不同的表由调用方的 skip_column_count 先拦下，这里只保证不抛
        assert reordered_columns(["项目", "A", "B"], ["项目", "A"]) is False
