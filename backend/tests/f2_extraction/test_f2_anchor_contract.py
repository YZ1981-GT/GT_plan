"""F2 锚点注册表契约守卫测试."""
from app.services.f2_extraction.anchor_registry import F2_ANCHORS, is_known_anchor, seed_field


def test_anchor_count_is_39():
    """F2_ANCHORS = 12 原值类 × 3 字段 + 1 跌价类 × 3 字段 = 39."""
    assert len(F2_ANCHORS) == 39


def test_is_known_anchor_true_for_valid():
    """集合内锚点 → True."""
    assert is_known_anchor("F2-1-gross-raw-materials-opening") is True
    assert is_known_anchor("F2-1-gross-finished-goods-decrease") is True
    assert is_known_anchor("F2-1-impairment-impairment-provision-increase") is True


def test_is_known_anchor_false_for_invalid():
    """不存在的锚点 → False（adjustment 不是合法 field）."""
    assert is_known_anchor("F2-1-gross-raw-materials-adjustment") is False
    assert is_known_anchor("F2-1-gross-nonexistent-opening") is False
    assert is_known_anchor("") is False


def test_seed_field_returns_conclusion():
    """已知锚点 → 'conclusion'."""
    assert seed_field("F2-1-gross-raw-materials-opening") == "conclusion"
    assert seed_field("F2-1-impairment-impairment-provision-decrease") == "conclusion"


def test_seed_field_returns_none_for_unknown():
    """未知锚点 → None."""
    assert seed_field("F2-1-gross-raw-materials-adjustment") is None
    assert seed_field("INVALID") is None
    assert seed_field("") is None
