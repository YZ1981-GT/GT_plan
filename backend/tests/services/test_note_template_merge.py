"""单测 — note_template_merge.merge_templates（Sprint 3 Task 3.3）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.3
Reqs:   R4.3 验收 36（自定义模板与基线 union 不冲突）
"""

from __future__ import annotations

from app.services.note_template_merge import merge_templates


# ===========================================================================
# 1. 覆盖：custom 覆盖 baseline 同 section_number
# ===========================================================================


def test_override_same_section_number_replaces_baseline():
    """custom 与 baseline 同 section_number → custom 整 dict 替换 baseline."""
    baseline = [
        {"section_number": "五、1", "section_title": "货币资金", "sort_order": 10, "tables": ["base"]},
    ]
    custom = [
        {"section_number": "五、1", "section_title": "货币资金（修订版）", "sort_order": 10, "tables": ["custom"]},
    ]
    out = merge_templates(baseline, custom)
    assert len(out) == 1
    assert out[0]["section_title"] == "货币资金（修订版）"
    assert out[0]["tables"] == ["custom"]


def test_override_does_not_force_custom_flag():
    """覆盖场景 custom 自身不带 _custom 时，不强加 _custom: True 标记."""
    baseline = [{"section_number": "五、1", "section_title": "货币资金", "sort_order": 10}]
    custom = [{"section_number": "五、1", "section_title": "货币资金 v2", "sort_order": 10}]
    out = merge_templates(baseline, custom)
    assert "_custom" not in out[0] or out[0].get("_custom") is False


# ===========================================================================
# 2. 新增：custom 独有章节 → 加 _custom: True 按 sort_order 插入
# ===========================================================================


def test_custom_only_section_marked_custom_true():
    """custom 独有 section_number → 输出标 _custom: True."""
    baseline = [{"section_number": "五、1", "section_title": "货币资金", "sort_order": 10}]
    custom = [{"section_number": "五、X1", "section_title": "递延收益", "sort_order": 8990}]
    out = merge_templates(baseline, custom)
    assert len(out) == 2
    custom_section = next(s for s in out if s["section_number"] == "五、X1")
    assert custom_section["_custom"] is True
    base_section = next(s for s in out if s["section_number"] == "五、1")
    assert "_custom" not in base_section or base_section.get("_custom") is False


def test_custom_only_section_inserted_by_sort_order():
    """custom 独有章节按 sort_order 插入正确位置（不是简单尾插）."""
    baseline = [
        {"section_number": "五、1", "section_title": "A", "sort_order": 10},
        {"section_number": "五、2", "section_title": "B", "sort_order": 30},
    ]
    custom = [{"section_number": "五、X1", "section_title": "X", "sort_order": 20}]
    out = merge_templates(baseline, custom)
    assert [s["section_number"] for s in out] == ["五、1", "五、X1", "五、2"]


# ===========================================================================
# 3. 排序：按 sort_order 升序输出
# ===========================================================================


def test_output_sorted_by_sort_order_ascending():
    baseline = [
        {"section_number": "五、3", "section_title": "C", "sort_order": 30},
        {"section_number": "五、1", "section_title": "A", "sort_order": 10},
        {"section_number": "五、2", "section_title": "B", "sort_order": 20},
    ]
    out = merge_templates(baseline, [])
    assert [s["section_number"] for s in out] == ["五、1", "五、2", "五、3"]


def test_output_sort_order_stable_for_ties():
    """sort_order 相同 → 保持插入顺序（baseline 在前，custom 在后）."""
    baseline = [
        {"section_number": "五、1", "section_title": "A", "sort_order": 10},
        {"section_number": "五、2", "section_title": "B", "sort_order": 10},
    ]
    custom = [{"section_number": "五、X1", "section_title": "X", "sort_order": 10}]
    out = merge_templates(baseline, custom)
    # baseline 顺序保留 + custom 追加
    assert [s["section_number"] for s in out] == ["五、1", "五、2", "五、X1"]


# ===========================================================================
# 4. 空集场景
# ===========================================================================


def test_empty_custom_returns_baseline_only():
    baseline = [{"section_number": "五、1", "section_title": "A", "sort_order": 10}]
    out = merge_templates(baseline, [])
    assert len(out) == 1
    assert out[0]["section_number"] == "五、1"
    assert "_custom" not in out[0] or out[0].get("_custom") is False


def test_none_custom_returns_baseline_only():
    baseline = [{"section_number": "五、1", "section_title": "A", "sort_order": 10}]
    out = merge_templates(baseline, None)
    assert len(out) == 1


def test_empty_baseline_returns_custom_all_marked_custom():
    custom = [
        {"section_number": "五、X1", "section_title": "X1", "sort_order": 10},
        {"section_number": "五、X2", "section_title": "X2", "sort_order": 20},
    ]
    out = merge_templates([], custom)
    assert len(out) == 2
    assert all(s.get("_custom") is True for s in out)


def test_both_empty_returns_empty_list():
    assert merge_templates([], []) == []
    assert merge_templates(None, None) == []


# ===========================================================================
# 5. sort_order 缺失视为 0
# ===========================================================================


def test_missing_sort_order_treated_as_zero():
    baseline = [
        {"section_number": "五、A", "section_title": "noSort"},
        {"section_number": "五、B", "section_title": "B", "sort_order": -5},
    ]
    out = merge_templates(baseline, [])
    # B 的 sort_order=-5 < 0；A 缺失视为 0；故输出 [B, A]
    assert [s["section_number"] for s in out] == ["五、B", "五、A"]


def test_non_numeric_sort_order_treated_as_zero():
    baseline = [
        {"section_number": "五、A", "section_title": "A", "sort_order": "abc"},  # 非法
        {"section_number": "五、B", "section_title": "B", "sort_order": 5},
    ]
    out = merge_templates(baseline, [])
    # A sort_order 非数字 → 视为 0；故 A < B
    assert [s["section_number"] for s in out] == ["五、A", "五、B"]


# ===========================================================================
# 6. 防脏数据
# ===========================================================================


def test_dict_without_section_number_is_skipped():
    baseline = [
        {"section_title": "缺 section_number"},  # 跳过
        {"section_number": "五、1", "section_title": "A", "sort_order": 10},
    ]
    out = merge_templates(baseline, [])
    assert len(out) == 1
    assert out[0]["section_number"] == "五、1"


def test_non_dict_entries_are_skipped():
    baseline = [
        "not a dict",  # 跳过
        {"section_number": "五、1", "section_title": "A", "sort_order": 10},
        None,  # 跳过
    ]
    out = merge_templates(baseline, [])
    assert len(out) == 1


def test_does_not_mutate_input_lists():
    """纯函数：不修改入参."""
    baseline = [{"section_number": "五、1", "section_title": "A", "sort_order": 10}]
    custom = [{"section_number": "五、X1", "section_title": "X", "sort_order": 20}]
    bs_snap = [dict(s) for s in baseline]
    cs_snap = [dict(s) for s in custom]
    _ = merge_templates(baseline, custom)
    assert baseline == bs_snap
    assert custom == cs_snap
