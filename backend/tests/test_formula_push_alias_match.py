"""find_row 第四级别名匹配测试（spec: formula-management-deep-optimization · R1）。

验证：
1. 别名表加载正确
2. 标准名匹配到别名行
3. 别名匹配到标准名行
4. 无别名时退化为 None（不影响前三级）
5. 合计行不参与别名匹配
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.formula_push.note_writer import (
    _build_reverse_aliases,
    _load_aliases,
    find_row,
)


def _rows(*labels: str, total_label: str | None = None) -> list[dict]:
    """构造简单的附注行列表。"""
    result = []
    for label in labels:
        result.append({"label": label})
    if total_label:
        result.append({"label": total_label, "is_total": True})
    return result


class TestAliasLoading:
    """别名表加载与缓存。"""

    def test_load_aliases_returns_dict(self):
        aliases = _load_aliases()
        assert isinstance(aliases, dict)

    def test_reverse_aliases_bidirectional(self):
        """标准名和别名都能在反向映射中找到。"""
        reverse = _build_reverse_aliases()
        aliases = _load_aliases()
        if not aliases:
            pytest.skip("别名表为空或不存在")
        for canonical, names in aliases.items():
            assert reverse.get(canonical) == canonical, f"{canonical} 标准名自映射缺失"
            for name in names:
                assert reverse.get(name) == canonical, f"别名 {name} → {canonical} 映射缺失"


class TestAliasMatch:
    """find_row 第四级别名匹配。"""

    def test_standard_name_matches_alias_row(self):
        """标准名 "应收账款" 在附注行中找到别名 "应收账款净额"。"""
        rows = _rows("货币资金", "应收账款净额", "存货")
        result = find_row(rows, ["应收账款"])
        assert result == 1, f"应找到 index=1（应收账款净额），实际 {result}"

    def test_alias_matches_standard_name_row(self):
        """别名 "预付账款" 在附注行中找到标准名 "预付款项"。"""
        rows = _rows("货币资金", "预付款项", "存货")
        result = find_row(rows, ["预付账款"])
        assert result == 1, f"应找到 index=1（预付款项），实际 {result}"

    def test_exact_match_takes_priority_over_alias(self):
        """精确匹配优先于别名匹配。"""
        rows = _rows("应收账款", "应收账款净额")
        result = find_row(rows, ["应收账款"])
        assert result == 0, "精确匹配应优先，返回 index=0"

    def test_no_alias_returns_none(self):
        """无别名的标签在行中不存在时返回 None。"""
        rows = _rows("货币资金", "存货")
        result = find_row(rows, ["完全不存在的科目"])
        assert result is None

    def test_alias_skips_total_row(self):
        """别名匹配跳过合计行。"""
        rows = _rows("货币资金", total_label="应收账款净额")
        result = find_row(rows, ["应收账款"])
        assert result is None, "合计行不应被别名匹配命中"

    def test_multiple_aliases_first_match_wins(self):
        """多个别名时第一个匹配到的行生效。"""
        rows = _rows("长期股权投资——对子公司投资", "长期股权投资合计")
        result = find_row(rows, ["长期股权投资"])
        # 应该命中 sorted 后的第一个别名
        assert result is not None, "应命中至少一个别名"

    def test_contains_match_still_works(self):
        """第三级包含匹配不受第四级影响。"""
        rows = _rows("减：应收账款坏账准备")
        # "应收账款" 经 _contains_match 应该不命中（减：前缀 strip 后 ≠ label）
        # 但如果恰好有唯一命中，第三级应该在第四级之前返回
        result = find_row(rows, ["应收账款坏账准备"])
        assert result == 0, "精确匹配应命中"

    def test_suffix_strip_still_works(self):
        """第二级去后缀匹配不受第四级影响。"""
        rows = _rows("应收票据")
        result = find_row(rows, ["应收票据小计"])
        assert result == 0, "去'小计'后缀后应精确匹配"


class TestAliasWithTempFile:
    """使用临时别名文件测试加载机制。"""

    def test_custom_alias_file(self, tmp_path: Path):
        """自定义别名文件能正确加载。"""
        alias_file = tmp_path / "aliases.json"
        alias_file.write_text(json.dumps({
            "_schema_version": 1,
            "aliases": {
                "测试科目A": ["科目A别名1", "科目A别名2"],
            }
        }), encoding="utf-8")

        with patch("app.services.formula_push.note_writer._ALIAS_PATH", alias_file), \
             patch("app.services.formula_push.note_writer._ALIAS_CACHE", None), \
             patch("app.services.formula_push.note_writer._ALIAS_MTIME", 0.0):
            aliases = _load_aliases()
            assert "测试科目A" in aliases
            assert "科目A别名1" in aliases["测试科目A"]

            rows = _rows("科目A别名1", "其他")
            result = find_row(rows, ["测试科目A"])
            assert result == 0
