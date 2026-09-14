# Feature: acnr, Property 6: 别名反查唯一性与冲突阻断
"""Property-Based Test: 别名反查唯一性与冲突阻断。

Validates: Requirements 3.1, 3.3, 3.5

Property 6 验证:
1. 经冲突过滤后的 catalog 中，无别名映射到多于一个 sheet_code（冲突已阻断）
2. 给定 catalog 中的任意别名，lookup 返回恰好唯一结果（不歧义）
3. _detect_alias_conflicts 正确识别一对多别名
4. 阻断优先于缺口标记（R3.5）：冲突别名不出现在任何 sheet 的 aliases 中
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# 确保 backend 在 sys.path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.acnr.generate_catalog import _detect_alias_conflicts


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 合法的 sheet_code 格式：大写字母 + 数字 + 可选后缀（如 D2-1, F3A）
_sheet_code_st = st.from_regex(r"[A-N]\d-\d{1,2}", fullmatch=True)

# 别名：非空中文/ASCII 字符串，长度 1~20
_alias_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),  # 字母 + 数字
        min_codepoint=0x30,
        max_codepoint=0x9FFF,  # 含中文
    ),
    min_size=1,
    max_size=20,
)

# 生成随机别名映射：{sheet_code → list[alias]}，2~6 个 sheet，每个 1~4 个别名
_alias_mapping_st = st.dictionaries(
    keys=_sheet_code_st,
    values=st.lists(_alias_st, min_size=1, max_size=4),
    min_size=2,
    max_size=6,
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(aliases=_alias_mapping_st)
def test_no_alias_maps_to_multiple_sheets_in_clean_output(
    aliases: dict[str, list[str]],
):
    """P6 不变量 1: clean_aliases 中任何别名至多映射一个 sheet_code。

    **Validates: Requirements 3.1, 3.3, 3.5**
    """
    clean, _conflicts = _detect_alias_conflicts(aliases)

    # 反转 clean_aliases：alias → set[sheet_codes]
    reverse: dict[str, set[str]] = {}
    for sheet_code, alias_list in clean.items():
        for alias in alias_list:
            if alias not in reverse:
                reverse[alias] = set()
            reverse[alias].add(sheet_code)

    # 不变量：每个别名至多对应 1 个 sheet_code
    for alias, sheet_codes in reverse.items():
        assert len(sheet_codes) == 1, (
            f"别名 '{alias}' 在 clean_aliases 中映射了多个 sheet_code: {sheet_codes}"
        )


@settings(max_examples=10)
@given(aliases=_alias_mapping_st)
def test_alias_lookup_returns_exactly_one_result(
    aliases: dict[str, list[str]],
):
    """P6 不变量 2: 给定 clean_aliases 中的任意别名，反查得到恰好一个 sheet_code。

    **Validates: Requirements 3.1, 3.3**
    """
    clean, _conflicts = _detect_alias_conflicts(aliases)

    # 构建反查索引（去重：同一 sheet_code 不重复计入）
    alias_to_sheet: dict[str, set[str]] = {}
    for sheet_code, alias_list in clean.items():
        for alias in alias_list:
            if alias not in alias_to_sheet:
                alias_to_sheet[alias] = set()
            alias_to_sheet[alias].add(sheet_code)

    # 不变量：每个别名恰好对应 1 个 sheet_code
    for alias, sheets in alias_to_sheet.items():
        assert len(sheets) == 1, (
            f"别名 '{alias}' 反查到 {len(sheets)} 个 sheet_code: {sheets}，应恰好为 1"
        )


@settings(max_examples=10)
@given(aliases=_alias_mapping_st)
def test_conflict_detection_identifies_one_to_many(
    aliases: dict[str, list[str]],
):
    """P6 不变量 3: _detect_alias_conflicts 正确识别一对多别名冲突。

    **Validates: Requirements 3.3**
    """
    clean, conflicts = _detect_alias_conflicts(aliases)

    # 计算预期冲突：同一别名出现在多个 sheet_code 的 alias_list 中
    alias_to_sheets: dict[str, set[str]] = {}
    for sheet_code, alias_list in aliases.items():
        for alias in alias_list:
            if alias not in alias_to_sheets:
                alias_to_sheets[alias] = set()
            alias_to_sheets[alias].add(sheet_code)

    expected_conflicting = {
        alias for alias, sheets in alias_to_sheets.items() if len(sheets) > 1
    }

    # 冲突报告中的别名集合
    reported_conflicting = {c["alias"] for c in conflicts}

    # 不变量：报告的冲突别名 == 实际一对多别名
    assert reported_conflicting == expected_conflicting, (
        f"冲突检测不一致：\n"
        f"  报告的: {reported_conflicting}\n"
        f"  预期的: {expected_conflicting}"
    )


@settings(max_examples=10)
@given(aliases=_alias_mapping_st)
def test_blocking_takes_priority_over_gap_marking(
    aliases: dict[str, list[str]],
):
    """P6 不变量 4: 阻断优先于缺口标记 — 冲突别名不出现在任何 sheet 的 clean aliases 中。

    **Validates: Requirements 3.5**
    """
    clean, conflicts = _detect_alias_conflicts(aliases)

    # 收集所有冲突别名
    conflicting_aliases = {c["alias"] for c in conflicts}

    # 不变量：冲突别名绝不出现在 clean_aliases 的任何 sheet 中
    for sheet_code, alias_list in clean.items():
        for alias in alias_list:
            assert alias not in conflicting_aliases, (
                f"冲突别名 '{alias}' 仍存在于 sheet '{sheet_code}' 的 clean_aliases 中，"
                f"违反 R3.5 阻断优先原则"
            )

    # 额外：所有冲突报告都标记了 action=blocked
    for conflict in conflicts:
        assert conflict["action"] == "blocked", (
            f"冲突记录 '{conflict['alias']}' 的 action 不是 'blocked'：{conflict['action']}"
        )
