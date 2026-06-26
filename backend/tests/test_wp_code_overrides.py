"""wp_code_overrides.json 配置完整性 PBT

Feature: a-cycle-docx-online, Property 1: Override 注册正确性

验证 JSON 包含全部 31 条新增映射（25 word-template + 6 非 docx），
并验证保护列表 (A16, A17-1, A17-7) 不变。

**Validates: Requirements 1.1, 1.3, 2.1-2.6**
"""

from __future__ import annotations

import json
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# ──────────────────────────────────────────────────────────────────────
# 期望映射集合
# ──────────────────────────────────────────────────────────────────────

# 25 个 word-template 新增映射
EXPECTED_WORD_TEMPLATE: dict[str, str] = {
    "A8-1": "word-template",
    "A8-2": "word-template",
    "A9-1": "word-template",
    "A9-2": "word-template",
    "A10-1": "word-template",
    "A11-1": "word-template",
    "A12-1": "word-template",
    "A16-1": "word-template",
    "A16-2": "word-template",
    "A16-3": "word-template",
    "A16-4": "word-template",
    "A16-5": "word-template",
    "A16-6": "word-template",
    "A16-7": "word-template",
    "A17-2-1": "word-template",
    "A17-3": "word-template",
    "A17-3-1": "word-template",
    "A17-4": "word-template",
    "A17-6": "word-template",
    "A18-1": "word-template",
    "A26-1": "word-template",
    "A26-2": "word-template",
    "A26-3": "word-template",
    "A26-4": "word-template",
    "A27-1": "word-template",
}

# 6 个非 docx 新增映射
EXPECTED_NON_DOCX: dict[str, str] = {
    "A30": "checklist-table",
    "A28": "d-form-table",
    "A4-1": "audit-sheet",
    "A7-1": "audit-sheet",
    "A10": "a-program-console",
    "A12": "a-program-console",
}

# 全部 31 条新增映射
ALL_EXPECTED: dict[str, str] = {**EXPECTED_WORD_TEMPLATE, **EXPECTED_NON_DOCX}

# 保护列表：这些条目必须存在且值不能被修改
PROTECTED_ENTRIES: dict[str, str] = {
    "A16": "word-template",
    "A17-1": "a17-summary",
    "A17-7": "independence-signing",
}

# ──────────────────────────────────────────────────────────────────────
# 加载 JSON
# ──────────────────────────────────────────────────────────────────────

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────────
# 确定性验证（每条映射必须存在）
# ──────────────────────────────────────────────────────────────────────


def test_all_31_new_mappings_exist():
    """验证 JSON 包含全部 31 条新增映射且值正确

    Validates: Requirements 1.1, 2.1-2.6
    """
    overrides = _load_overrides()
    missing = {}
    wrong_value = {}

    for wp_code, expected_type in ALL_EXPECTED.items():
        if wp_code not in overrides:
            missing[wp_code] = expected_type
        elif overrides[wp_code] != expected_type:
            wrong_value[wp_code] = (expected_type, overrides[wp_code])

    assert not missing, (
        f"以下 wp_code 缺失于 wp_code_overrides.json:\n"
        + "\n".join(f"  {code} -> 期望 {ctype}" for code, ctype in sorted(missing.items()))
    )
    assert not wrong_value, (
        f"以下 wp_code 映射值不正确:\n"
        + "\n".join(
            f"  {code}: 期望 {exp!r}, 实际 {act!r}"
            for code, (exp, act) in sorted(wrong_value.items())
        )
    )


def test_25_word_template_count():
    """验证恰好有 25 个 word-template 新增条目

    Validates: Requirements 1.1
    """
    overrides = _load_overrides()
    found = {k for k in EXPECTED_WORD_TEMPLATE if overrides.get(k) == "word-template"}
    assert len(found) == 25, f"期望 25 条 word-template，实际 {len(found)}: 缺 {set(EXPECTED_WORD_TEMPLATE) - found}"


def test_6_non_docx_count():
    """验证恰好有 6 个非 docx 新增条目

    Validates: Requirements 2.1-2.6
    """
    overrides = _load_overrides()
    found = {k for k, v in EXPECTED_NON_DOCX.items() if overrides.get(k) == v}
    assert len(found) == 6, f"期望 6 条非 docx，实际 {len(found)}: 缺 {set(EXPECTED_NON_DOCX) - found}"


def test_protected_entries_unchanged():
    """验证保护列表 (A16, A17-1, A17-7) 未被修改

    Validates: Requirements 1.3
    """
    overrides = _load_overrides()
    for wp_code, expected_type in PROTECTED_ENTRIES.items():
        assert wp_code in overrides, f"保护条目 {wp_code!r} 缺失"
        assert overrides[wp_code] == expected_type, (
            f"保护条目 {wp_code!r} 值被修改: 期望 {expected_type!r}, 实际 {overrides[wp_code]!r}"
        )


# ──────────────────────────────────────────────────────────────────────
# Property-Based Test: 随机选取 wp_code 验证映射正确
# ──────────────────────────────────────────────────────────────────────

_all_expected_codes = list(ALL_EXPECTED.keys())


@given(wp_code=st.sampled_from(_all_expected_codes))
@settings(max_examples=5, deadline=None)
def test_random_wp_code_exists_in_overrides(wp_code: str):
    """Property 1: 任意从期望集合中选取的 wp_code 在 JSON 中存在且值正确

    Feature: a-cycle-docx-online, Property 1: Override 注册正确性

    **Validates: Requirements 1.1, 1.3, 2.1-2.6**
    """
    overrides = _load_overrides()
    expected_type = ALL_EXPECTED[wp_code]
    assert wp_code in overrides, f"{wp_code!r} 不在 wp_code_overrides.json 中"
    assert overrides[wp_code] == expected_type, (
        f"{wp_code!r}: 期望 {expected_type!r}, 实际 {overrides[wp_code]!r}"
    )


@given(wp_code=st.sampled_from(list(PROTECTED_ENTRIES.keys())))
@settings(max_examples=5, deadline=None)
def test_random_protected_entry_intact(wp_code: str):
    """Property 1 (保护子集): 任意保护列表条目值不变

    **Validates: Requirements 1.3**
    """
    overrides = _load_overrides()
    expected_type = PROTECTED_ENTRIES[wp_code]
    assert overrides.get(wp_code) == expected_type, (
        f"保护条目 {wp_code!r} 期望 {expected_type!r}, 实际 {overrides.get(wp_code)!r}"
    )
