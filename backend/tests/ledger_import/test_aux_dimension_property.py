"""辅助维度解析 Hypothesis 属性测试 — Task 76。

属性：
1. parse_aux_dimension 永远不抛异常（任意字符串输入）
2. 返回值始终是 list[dict]，每个 dict 含 aux_type/aux_code/aux_name
3. 空输入返回空列表
4. JSON 格式输入的 key 数量 = 返回列表长度
5. 多维分隔后段数 ≥ 返回列表长度（JSON 段可能展开为多个）
6. detect_aux_columns 返回的索引都在 [0, len(headers)) 范围内
"""

from __future__ import annotations

import json
import string

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.ledger_import.aux_dimension import (
    detect_aux_columns,
    parse_aux_dimension,
)


# ---------------------------------------------------------------------------
# 属性 1: 永远不抛异常
# ---------------------------------------------------------------------------


@given(st.text(max_size=500))
@settings(max_examples=10)
def test_parse_never_raises(raw: str):
    """任意字符串输入都不抛异常。"""
    result = parse_aux_dimension(raw)
    assert isinstance(result, list)


@given(st.one_of(st.none(), st.text(max_size=0)))
def test_parse_empty_returns_empty(raw):
    """空/None 输入返回空列表。"""
    result = parse_aux_dimension(raw)
    assert result == []


# ---------------------------------------------------------------------------
# 属性 2: 返回值结构正确
# ---------------------------------------------------------------------------


@given(st.text(min_size=1, max_size=200))
@settings(max_examples=10)
def test_parse_returns_valid_structure(raw: str):
    """返回值每个元素都有 aux_type/aux_code/aux_name 三个 key。"""
    result = parse_aux_dimension(raw)
    for item in result:
        assert "aux_type" in item
        assert "aux_code" in item
        assert "aux_name" in item
        # 值要么是 str 要么是 None
        for v in item.values():
            assert v is None or isinstance(v, str)


# ---------------------------------------------------------------------------
# 属性 3: JSON 格式保持 key 数量
# ---------------------------------------------------------------------------


@given(st.dictionaries(
    keys=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1, max_size=10,
    ),
    values=st.text(min_size=1, max_size=20),
    min_size=1, max_size=5,
))
@settings(max_examples=5)
def test_json_format_preserves_key_count(d: dict):
    """JSON 格式输入的 key 数量 = 返回列表长度。"""
    raw = json.dumps(d, ensure_ascii=False)
    result = parse_aux_dimension(raw)
    assert len(result) == len(d)
    for item in result:
        assert item["aux_type"] in d


# ---------------------------------------------------------------------------
# 属性 4: 多维分隔
# ---------------------------------------------------------------------------


@given(st.lists(
    st.text(
        alphabet=st.characters(blacklist_characters=",;；"),
        min_size=1, max_size=30,
    ),
    min_size=1, max_size=5,
))
@settings(max_examples=10)
def test_multi_dimension_split(parts: list[str]):
    """用逗号分隔的多段，返回列表长度 ≤ 段数 + 1（整体不可解析时 fallback 1 条）。

    注意：S6-6 后 `_smart_comma_split` 只在"逗号后紧跟 `类型:`"时才切分，
    因此随机 parts 大概率不会被切，整体变成 1 条 unparseable。
    """
    raw = ",".join(parts)
    if not raw.strip():
        # 纯空白输入 → 返回空列表（满足不变式）
        result = parse_aux_dimension(raw)
        assert result == []
        return

    result = parse_aux_dimension(raw)
    non_empty_parts = [p for p in parts if p.strip()]
    # 上界：每段一条（强切分场景）或整体一条（弱切分场景）
    assert len(result) <= max(len(non_empty_parts), 1)


# ---------------------------------------------------------------------------
# 属性 5: detect_aux_columns 索引范围
# ---------------------------------------------------------------------------


@given(st.lists(st.text(min_size=0, max_size=30), min_size=0, max_size=20))
@settings(max_examples=10)
def test_detect_aux_columns_valid_indices(headers: list[str]):
    """返回的索引都在合法范围内。"""
    indices = detect_aux_columns(headers)
    for idx in indices:
        assert 0 <= idx < len(headers)


# ---------------------------------------------------------------------------
# 具体格式测试（补充 test_aux_dimension_verify.py 已有的）
# ---------------------------------------------------------------------------


class TestSpecificFormats:
    """6 种格式的边界情况。"""

    def test_colon_with_fullwidth(self):
        """全角冒号也能解析。"""
        result = parse_aux_dimension("客户：C001 甲公司")
        assert len(result) == 1
        assert result[0]["aux_type"] == "客户"
        assert result[0]["aux_code"] == "C001"
        assert result[0]["aux_name"] == "甲公司"

    def test_arrow_with_unicode(self):
        """Unicode 箭头 → 也能解析。"""
        result = parse_aux_dimension("部门 → 研发部")
        assert len(result) == 1
        assert result[0]["aux_type"] == "部门"
        assert result[0]["aux_name"] == "研发部"

    def test_mixed_separators(self):
        """混合分隔符（逗号+分号）。"""
        result = parse_aux_dimension("客户:C001 甲公司;项目:P01 研发项目")
        assert len(result) == 2

    def test_unparseable_preserved(self):
        """无法解析的段原样保留在 aux_name 中。"""
        result = parse_aux_dimension("一段无法解析的文本")
        assert len(result) == 1
        assert result[0]["aux_name"] == "一段无法解析的文本"
        assert result[0]["aux_type"] is None
        assert result[0]["aux_code"] is None

    def test_real_sample_yonyou_format(self):
        """用友真实格式：客户:C001 重庆医药集团。"""
        result = parse_aux_dimension("客户:C001 重庆医药集团四川物流有限公司")
        assert len(result) == 1
        assert result[0]["aux_type"] == "客户"
        assert result[0]["aux_code"] == "C001"
        assert "重庆医药" in result[0]["aux_name"]
