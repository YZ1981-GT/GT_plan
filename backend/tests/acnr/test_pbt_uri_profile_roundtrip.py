# Feature: acnr, Property 3: URI profile 往返保持
"""Property-based test: URI profile 往返保持（standard/custom_flat）.

**Validates: Requirements 9.1, 9.2, 9.4, 9.5**

验证规则:
- R9.1: standard profile URI (wp://{parent}/{sheet_name}#{cell}) 往返保持
- R9.2: custom_flat profile URI (wp://{wp_code}/{cell}) 往返保持
- R9.4: RuntimeCellEntry 自定义格使用 custom_flat profile
- R9.5: profile 类型在往返后保持不变（standard 仍为 standard，custom_flat 仍为 custom_flat）

往返路径：uri → uri_to_formula_ref() → formula_ref_to_uri() → 比较 URI 是否与原始一致。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis.strategies import (
    composite,
    from_regex,
    sampled_from,
    text,
)

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.grammar import formula_ref_to_uri, uri_to_formula_ref


# ---------------------------------------------------------------------------
# Strategies: 生成合法 URI
# ---------------------------------------------------------------------------

# 标准码父级：[A-S] 开头 + 数字 + 可选后缀
_STANDARD_PARENTS = [
    "D1", "D2", "D3", "D4", "D5", "D6", "D7",
    "E1", "F1", "F2", "F3", "G1", "G2", "G5",
    "H1", "H2", "I1", "J1", "K1", "L1", "M1", "N1", "S3",
]

# sheet_name 样本（含中文的真实 sheet 名称，不能匹配 A1 单元格模式）
_SHEET_NAMES = [
    "明细表D2-2", "审定表D1-1", "原值明细（按类）D1-2",
    "检查表D3-3", "往来款明细表", "账龄分析表",
    "减值测试表", "利息测算表", "期末余额表",
    "审定汇总", "折旧测算表F3-4", "借款明细L1-2",
]

# cell 地址（A1 格式：1~3 字母 + 数字）
_CELL_ADDRESSES = [
    "A1", "B7", "C10", "E100", "F50", "G30",
    "H15", "AA5", "AB200", "D99", "Z1",
]

# custom_flat wp_code（非标准码，用于自定义底稿）
_CUSTOM_WP_CODES = [
    "CUST-01", "CUST-02", "CUST-ABC", "MY-WP-1",
    "CUSTOM-X", "USR-001", "TEST-WP",
]


@composite
def standard_uri_strategy(draw):
    """生成 standard profile URI: wp://{parent}/{sheet_name}#{cell}"""
    parent = draw(sampled_from(_STANDARD_PARENTS))
    sheet_name = draw(sampled_from(_SHEET_NAMES))
    cell = draw(sampled_from(_CELL_ADDRESSES))
    return f"wp://{parent}/{sheet_name}#{cell}"


@composite
def custom_flat_uri_strategy(draw):
    """生成 custom_flat profile URI: wp://{wp_code}/{cell}"""
    wp_code = draw(sampled_from(_CUSTOM_WP_CODES))
    cell = draw(sampled_from(_CELL_ADDRESSES))
    return f"wp://{wp_code}/{cell}"


# ---------------------------------------------------------------------------
# Property Test: standard profile 往返保持
# ---------------------------------------------------------------------------


class TestUriProfileRoundtripStandard:
    """Standard profile URI 往返保持验证。

    R9.1: standard profile (wp://{parent}/{sheet_name}#{cell}) 经
    uri_to_formula_ref → formula_ref_to_uri 后回到相同 URI。
    """

    @given(uri=standard_uri_strategy())
    @settings(max_examples=10)
    def test_standard_uri_roundtrip(self, uri: str):
        """Standard URI → formula_ref → URI 往返一致。"""
        # Step 1: URI → formula_ref
        formula_ref = uri_to_formula_ref(uri)
        assert formula_ref is not None, (
            f"uri_to_formula_ref 返回 None，输入 URI: {uri}"
        )

        # Step 2: formula_ref → URI
        roundtrip_uri = formula_ref_to_uri(formula_ref)
        assert roundtrip_uri is not None, (
            f"formula_ref_to_uri 返回 None，输入 formula_ref: {formula_ref}"
        )

        # Step 3: 验证往返一致
        assert roundtrip_uri == uri, (
            f"Standard URI 往返不一致:\n"
            f"  原始 URI:    {uri}\n"
            f"  formula_ref: {formula_ref}\n"
            f"  往返 URI:    {roundtrip_uri}"
        )

    @given(uri=standard_uri_strategy())
    @settings(max_examples=10)
    def test_standard_profile_preserved(self, uri: str):
        """R9.5: Standard profile 往返后 profile 类型保持为 standard。

        验证中间 formula_ref 是 3 参 WP() 格式（standard profile 特征）。
        """
        formula_ref = uri_to_formula_ref(uri)
        assert formula_ref is not None

        # Standard 3 参 WP: WP('parent','sheet_name','cell')
        # 验证 formula_ref 匹配 3 参格式
        pattern = re.compile(r"^WP\('[^']+','[^']+','[^']+'\)$")
        assert pattern.match(formula_ref), (
            f"Standard URI 应转为 3 参 WP() (standard profile)，"
            f"但得到: {formula_ref}"
        )


# ---------------------------------------------------------------------------
# Property Test: custom_flat profile 往返保持
# ---------------------------------------------------------------------------


class TestUriProfileRoundtripCustomFlat:
    """Custom_flat profile URI 往返保持验证。

    R9.2: custom_flat profile (wp://{wp_code}/{cell}) 经
    uri_to_formula_ref → formula_ref_to_uri 后回到相同 URI。
    """

    @given(uri=custom_flat_uri_strategy())
    @settings(max_examples=10)
    def test_custom_flat_uri_roundtrip(self, uri: str):
        """Custom_flat URI → formula_ref → URI 往返一致。"""
        # Step 1: URI → formula_ref
        formula_ref = uri_to_formula_ref(uri)
        assert formula_ref is not None, (
            f"uri_to_formula_ref 返回 None，输入 URI: {uri}"
        )

        # Step 2: formula_ref → URI
        roundtrip_uri = formula_ref_to_uri(formula_ref)
        assert roundtrip_uri is not None, (
            f"formula_ref_to_uri 返回 None，输入 formula_ref: {formula_ref}"
        )

        # Step 3: 验证往返一致
        assert roundtrip_uri == uri, (
            f"Custom_flat URI 往返不一致:\n"
            f"  原始 URI:    {uri}\n"
            f"  formula_ref: {formula_ref}\n"
            f"  往返 URI:    {roundtrip_uri}"
        )

    @given(uri=custom_flat_uri_strategy())
    @settings(max_examples=10)
    def test_custom_flat_profile_preserved(self, uri: str):
        """R9.5: Custom_flat profile 往返后 profile 类型保持为 custom_flat。

        验证中间 formula_ref 是 2 参 WP() 格式（custom_flat profile 特征）
        且第二参匹配 A1 坐标模式。
        """
        formula_ref = uri_to_formula_ref(uri)
        assert formula_ref is not None

        # Custom_flat 2 参 WP: WP('wp_code','cell')
        # 验证 formula_ref 匹配 2 参格式
        pattern = re.compile(r"^WP\('([^']+)','([^']+)'\)$")
        m = pattern.match(formula_ref)
        assert m is not None, (
            f"Custom_flat URI 应转为 2 参 WP() (custom_flat profile)，"
            f"但得到: {formula_ref}"
        )

        # 验证第二参是 A1 坐标格式（custom_flat 特征）
        second_arg = m.group(2)
        cell_pattern = re.compile(r"^[A-Za-z]{1,3}\d+$")
        assert cell_pattern.match(second_arg), (
            f"Custom_flat profile 第二参应为 A1 坐标，但得到: {second_arg}"
        )
