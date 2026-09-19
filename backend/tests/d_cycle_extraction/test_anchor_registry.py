"""Wave 0 / Task 1.2 —— D-cycle 锚点登记表 + 合法性校验单测.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/  (Requirements 6.1, 6.2, 6.3)

核心 = **Property 8：未知锚点拒绝**（`is_known_anchor` 对不属于该 wp_code 已知锚点集的
item_id 返回 False → 调用方拒绝/告警，防止提取种子静默写到不存在字段而丢失）。

锚点来源真实性钉死（Task 1.2 最高风险点）：设计/characterization 里出现的**示例键**
`D6-1-block1-endUnadjusted` 并非 useD6Adjudication 真实持久化键（真实为
`D6-1-adj-block1-<rowKey>-currentUnadjusted`），故必须被 `is_known_anchor` 拒绝。
"""
from __future__ import annotations

from app.services.d_cycle_extraction.anchor_registry import (
    is_known_anchor,
    known_anchors,
    registered_wp_codes,
)


# ─── 覆盖登记 wp_code ────────────────────────────────────────────────────────


def test_registered_wp_codes_cover_d6_d2_and_skip_meta():
    codes = registered_wp_codes()
    assert "D6" in codes
    assert "D2" in codes
    # _meta 等元数据键不得当作 wp_code
    assert "_meta" not in codes
    assert not any(c.startswith("_") for c in codes)


# ─── 精确锚点被接受 ──────────────────────────────────────────────────────────


def test_d6_exact_anchors_accepted():
    for anchor in (
        "D6-1-tb-amount",
        "D6-1-note-explanation",
        "D6-1-note-conclusion",
        "D6-1-adj-block1-rowKeys",
        "D6-1-adj-block2-rowKeys",
        "D6-2-rows",
    ):
        assert is_known_anchor("D6", anchor), anchor


def test_d2_exact_anchors_accepted():
    for anchor in (
        "D2-adj-tb-amount",
        "D2-adj-total-aje",
        "D2-adj-total-rje",
        "D2-adj-confirm-summary",
        "D2-detail-rows",
    ):
        assert is_known_anchor("D2", anchor), anchor


# ─── 模式锚点（动态 rowKey per-field）被接受 ────────────────────────────────


def test_d6_dynamic_rowkey_pattern_anchors_accepted():
    # 生成 id rowKey（含连字符）
    assert is_known_anchor("D6", "D6-1-adj-block1-adj-171xyz-abc-currentUnadjusted")
    assert is_known_anchor("D6", "D6-1-adj-block1-adj-171xyz-abc-priorUnadjusted")
    # 合同类型名 rowKey
    assert is_known_anchor("D6", "D6-1-adj-block1-工程施工-currentUnadjusted")
    # 特殊 deduction 行
    assert is_known_anchor("D6", "D6-1-adj-block1-deduction-currentAje")
    # block2（坏账准备）同结构
    assert is_known_anchor("D6", "D6-1-adj-block2-cat-1-reasonAnalysis")


def test_d2_classification_pattern_anchors_accepted():
    for row_key in ("individual", "aging", "customer-type"):
        for field in (
            "prior-unadjusted",
            "prior-aje",
            "prior-rje",
            "current-unadjusted",
            "current-aje",
            "current-rje",
            "reason",
        ):
            anchor = f"D2-adj-{row_key}-{field}"
            assert is_known_anchor("D2", anchor), anchor


# ─── Property 8：未知锚点拒绝 ────────────────────────────────────────────────


def test_property8_illustrative_key_is_not_real_anchor_rejected():
    """设计/characterization 里的示例键 ≠ 真实 composable 锚点 → 必须拒绝。"""
    assert not is_known_anchor("D6", "D6-1-block1-endUnadjusted")


def test_property8_unknown_anchors_rejected():
    # 完全不存在的字段
    assert not is_known_anchor("D6", "D6-1-adj-block1-foo-nonexistentField")
    assert not is_known_anchor("D6", "D6-99-made-up")
    assert not is_known_anchor("D2", "D2-adj-individual-bogus-field")
    # rowKeys 追踪键不应被 per-field 模式误配
    assert not is_known_anchor("D6", "D6-1-adj-block3-x-currentUnadjusted")  # block3 computed 无持久化
    # D2 分类模式只认 individual/aging/customer-type，total 不在内
    assert not is_known_anchor("D2", "D2-adj-total-current-unadjusted")


def test_property8_cross_wp_code_rejected():
    """D6 锚点不属于 D2，反之亦然。"""
    assert not is_known_anchor("D2", "D6-1-tb-amount")
    assert not is_known_anchor("D6", "D2-adj-tb-amount")


def test_property8_unknown_wp_code_rejected():
    assert not is_known_anchor("D9", "anything")
    assert not is_known_anchor("D1", "D1-1-anything")  # D1 尚未登记（后续 Wave）


def test_property8_empty_inputs_rejected():
    assert not is_known_anchor("", "D6-1-tb-amount")
    assert not is_known_anchor("D6", "")
    assert not is_known_anchor("", "")


# ─── known_anchors 只返回精确集合（不含模式） ───────────────────────────────


def test_known_anchors_returns_exact_only():
    d6 = known_anchors("D6")
    assert "D6-1-tb-amount" in d6
    assert "D6-2-rows" in d6
    # 模式条目（re: 前缀）不在精确集合中
    assert not any(a.startswith("re:") for a in d6)
    # D1（Task 5.2 已登记）精确锚点集非空，且不含模式条目
    d1 = known_anchors("D1")
    assert "D1-adj-tb-amount" in d1
    assert not any(a.startswith("re:") for a in d1)
    # D7（Task 6 已登记）精确锚点集非空，且不含模式条目
    d7 = known_anchors("D7")
    assert "D7-1-adj-aging-trial-balance-currentAudited" in d7
    assert not any(a.startswith("re:") for a in d7)
    # 未登记 wp_code（D8+/其它循环尚未覆盖）→ 空集
    assert known_anchors("D8") == set()


def test_known_anchors_returns_copy_not_shared_reference():
    """返回副本，调用方修改不污染缓存。"""
    a = known_anchors("D6")
    a.add("__mutated__")
    b = known_anchors("D6")
    assert "__mutated__" not in b
