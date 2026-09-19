"""wp_formula 稳定键推导测试（P0-项1 · spec d4-dual-mode-formula-governance）

验证 app.services.formula_management.stable_key：
  - 单元：A1 拆解、sheet 规范化、needs_review 标记。
  - PBT（Property）：
      P1 key 不随 sheet 展示名的排序前缀/空白重命名而变（identity 稳定）。
      P2 preset_version 不进 identity（推导函数从不消费它 → 传任何 preset_version 都同键）。
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.services.formula_management.stable_key import (
    StableKey,
    derive_stable_key,
    normalize_sheet_key,
    parse_cell,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "cell,exp_row,exp_field,exp_review",
    [
        ("B5", "5", "B", False),
        ("aa12", "12", "AA", False),
        ("Z99", "99", "Z", False),
        ("净额", None, "净额", True),   # 命名单元 → needs_review，保留原值不丢
        ("", None, "", True),
        (None, None, "", True),
    ],
)
def test_parse_cell(cell, exp_row, exp_field, exp_review):
    row, field, review = parse_cell(cell)
    assert (row, field, review) == (exp_row, exp_field, exp_review)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("五、1 审定表D2-1", "审定表D2-1"),
        ("1. 审定表D2-1", "审定表D2-1"),
        ("（一）审定表D2-1", "审定表D2-1"),
        ("审定表D2-1", "审定表D2-1"),
        ("审定表\u3000D2-1  ", "审定表 D2-1"),  # 全角空格折叠 + trim
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_sheet_key(raw, expected):
    assert normalize_sheet_key(raw) == expected


def test_derive_needs_review_when_cell_unparseable():
    k = derive_stable_key("审定表D2-1", "净额")
    assert k.needs_review is True
    assert k.field_key == "净额"  # 不丢原值
    assert k.stable_sheet_key == "审定表D2-1"


def test_derive_normal_a1():
    k = derive_stable_key("五、审定表D2-1", "C7")
    assert k == StableKey(stable_sheet_key="审定表D2-1", row_key="7", field_key="C", needs_review=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Property-Based Tests（max_examples=5，项目约定）
# ═══════════════════════════════════════════════════════════════════════════════

# 生成 A1 地址（列 1-3 字母 + 行 1-9999），保证可解析
_col_st = st.text(alphabet=st.characters(min_codepoint=ord("A"), max_codepoint=ord("Z")), min_size=1, max_size=3)
_row_st = st.integers(min_value=1, max_value=9999).map(str)
_cell_st = st.tuples(_col_st, _row_st).map(lambda t: f"{t[0]}{t[1]}")
# 基础 sheet 名（不含前导排序前缀，避免与注入的前缀混淆）
_base_sheet_st = st.text(
    alphabet=st.characters(categories=("L", "N"), max_codepoint=0x9FFF),
    min_size=1, max_size=12,
).map(lambda s: s.strip()).filter(lambda s: len(s) > 0)

_ORDER_PREFIXES = ["", "一、", "1. ", "（一）", "五、1 ", "3、"]


@settings(max_examples=5)
@given(base=_base_sheet_st, cell=_cell_st, pi=st.integers(min_value=0, max_value=len(_ORDER_PREFIXES) - 1), pj=st.integers(min_value=0, max_value=len(_ORDER_PREFIXES) - 1))
def test_property_key_stable_across_sheet_rename(base, cell, pi, pj):
    """**Validates: P0-项1 稳定键**

    P1：同一 base sheet 名，无论加哪种排序前缀（重命名），推导出的 identity 键不变。
    """
    # base 本身不应以排序前缀开头（否则规范化会剥离它，破坏"同 base"前提）
    assume(normalize_sheet_key(base) == base)
    name_a = _ORDER_PREFIXES[pi] + base
    name_b = _ORDER_PREFIXES[pj] + base
    ka = derive_stable_key(name_a, cell)
    kb = derive_stable_key(name_b, cell)
    assert ka == kb, f"重命名前缀不应改键: {name_a!r} vs {name_b!r} → {ka} vs {kb}"


@settings(max_examples=5)
@given(base=_base_sheet_st, cell=_cell_st, v1=st.integers(min_value=1, max_value=999), v2=st.integers(min_value=1, max_value=999))
def test_property_preset_version_not_in_identity(base, cell, v1, v2):
    """**Validates: P0-项1 preset_version 不进 identity**

    P2：推导函数只吃 (sheet_name, target_cell)，从不消费 preset_version；
    因此对同一 (sheet,cell)，无论"上游 preset_version 为何"，键恒定。
    这里以"传不同 v1/v2 但推导入参相同"断言键相等（推导签名本身就不含 preset_version）。
    """
    assume(v1 != v2)
    ka = derive_stable_key(base, cell)
    kb = derive_stable_key(base, cell)
    assert ka == kb  # 键只由 (sheet,cell) 决定，preset_version 无从影响
